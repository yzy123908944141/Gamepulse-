from __future__ import annotations

from pathlib import Path
import re
from typing import Any, Callable, TypedDict

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import create_react_agent

from agent.langchain_memory import append_turn, build_history_text, get_memory
from agent.review_agents import build_supervisor_tools, reset_tool_event_sink, set_tool_event_sink
from agent.chains.common import get_chat_model


def _load_prompt(filename: str) -> str:
    path = Path(__file__).resolve().parent / "prompts" / filename
    try:
        return path.read_text(encoding="utf-8-sig").strip()
    except OSError:
        return ""


class AgentState(TypedDict, total=False):
    session_id: int
    user_input: str
    chat_history: str
    messages: list[BaseMessage]
    called_agents: list[str]
    called_tools: list[str]
    shared_context: dict[str, Any]
    supervisor_answer: str
    final_answer: str
    active_agent: str


SUPERVISOR_SYSTEM_PROMPT = """
你是 GamerPulse 集成 Agent 工作台的总控 Agent（supervisor）。
你的职责是理解用户当前问题，并自主决定是否调用：
- character_review_tool：处理角色人设、OOC、角色差异化、角色舆情风险等问题
- plot_review_tool：处理剧情结构、桥段推进、章节安排、伏笔铺垫与回收等问题

规则：
1. 如果问题主要是角色问题，优先调用角色审查 Agent。
2. 如果问题主要是剧情问题，优先调用剧情审查 Agent。
3. 如果问题同时涉及两者，你可以调用一个或两个工具，并整合结果统一回复。
4. 不要把用户“转走”；始终在同一个对话中完成协调与整合。
5. 输出给用户的是自然语言结果，不要暴露内部路由细节。
""".strip()

SUPERVISOR_SYSTEM_PROMPT = _load_prompt("control_agent.txt") or SUPERVISOR_SYSTEM_PROMPT


def _default_state() -> dict[str, Any]:
    return {
        "called_agents": [],
        "called_tools": [],
        "shared_context": {},
        "messages": [],
    }


def _normalize_shared_context(shared_context: dict[str, Any] | None) -> str:
    if not shared_context:
        return "暂无"
    return "\n".join(f"- {key}: {value}" for key, value in shared_context.items())


def _extract_text(result: Any) -> str:
    if isinstance(result, str):
        return result.strip()
    if isinstance(result, dict):
        messages = result.get("messages", [])
        for message in reversed(messages):
            if isinstance(message, AIMessage) and getattr(message, "content", None):
                return str(message.content).strip()
        return str(result).strip()
    return str(result).strip()

def _sanitize_plain_text(text: str) -> str:
    """Remove common Markdown artifacts from final user-facing answers."""
    cleaned_lines: list[str] = []
    for raw_line in str(text or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line in {"---", "***", "___"}:
            continue
        line = re.sub(r"^#{1,6}\s*", "", line)
        line = re.sub(r"^[-*+]\s+", "", line)
        line = line.replace("**", "").replace("__", "").replace("`", "")
        line = re.sub(r"[\U0001F300-\U0001FAFF\u2600-\u27BF]", "", line)
        if re.fullmatch(r"\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?", line):
            continue
        if "|" in line and line.count("|") >= 2:
            cells = [cell.strip() for cell in line.strip("|").split("|") if cell.strip()]
            if cells:
                line = "；".join(cells)
        cleaned_lines.append(line)
    return "\n".join(cleaned_lines).strip()


def load_context(state: AgentState) -> AgentState:
    memory = get_memory(state["session_id"])
    chat_history = build_history_text(memory)
    next_state = _default_state()
    next_state.update(state)
    next_state["chat_history"] = chat_history
    next_state["messages"] = [
        HumanMessage(
            content=(
                f"历史对话摘要：\n{chat_history or '暂无'}\n\n"
                f"当前共享上下文：\n{_normalize_shared_context(state.get('shared_context'))}\n\n"
                f"用户当前问题：\n{state['user_input']}"
            )
        )
    ]
    next_state["called_agents"] = []
    next_state["called_tools"] = []
    next_state.setdefault("shared_context", {})
    return next_state


def supervisor_node(state: AgentState) -> AgentState:
    shared_context = dict(state.get("shared_context", {}))
    called_agents = list(state.get("called_agents", []))
    called_tools = list(state.get("called_tools", []))
    supervisor_tools = build_supervisor_tools(
        session_id=state["session_id"],
        shared_context=shared_context,
        called_agents=called_agents,
        called_tools=called_tools,
    )
    supervisor_agent = create_react_agent(
        model=get_chat_model(temperature=0),
        tools=supervisor_tools,
        prompt=SUPERVISOR_SYSTEM_PROMPT,
    )
    result = supervisor_agent.invoke({"messages": state["messages"]})
    answer = _extract_text(result)
    return {
        "active_agent": "orchestrator",
        "supervisor_answer": answer,
        "called_agents": called_agents,
        "called_tools": called_tools,
        "shared_context": shared_context,
    }


def finalize_node(state: AgentState) -> AgentState:
    final_answer = _sanitize_plain_text(state.get("supervisor_answer", "")) or "暂时没有生成可用结果。"
    return {
        "active_agent": "orchestrator",
        "final_answer": final_answer,
    }


def build_orchestrator():
    graph = StateGraph(AgentState)
    graph.add_node("load_context", load_context)
    graph.add_node("supervisor", supervisor_node)
    graph.add_node("finalize", finalize_node)

    graph.add_edge(START, "load_context")
    graph.add_edge("load_context", "supervisor")
    graph.add_edge("supervisor", "finalize")
    graph.add_edge("finalize", END)

    return graph.compile(checkpointer=MemorySaver())


ORCHESTRATOR_APP = build_orchestrator()


def invoke_orchestrator(
    *,
    session_id: int,
    user_input: str,
    shared_context: dict[str, Any] | None = None,
    event_sink: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    initial_state: AgentState = {
        "session_id": session_id,
        "user_input": user_input,
        "shared_context": shared_context or {},
    }
    token = set_tool_event_sink(event_sink)
    try:
        if event_sink:
            event_sink({"type": "agent_start", "kind": "agent", "name": "orchestrator", "detail": "总控 Agent 正在判断调用路径"})
        result = ORCHESTRATOR_APP.invoke(
            initial_state,
            config={"configurable": {"thread_id": str(session_id)}},
        )
        if event_sink:
            event_sink({"type": "agent_end", "kind": "agent", "name": "orchestrator", "detail": "总控 Agent 已完成整合"})
    finally:
        reset_tool_event_sink(token)
    append_turn(session_id, user_input, result["final_answer"])
    return {
        "session_id": session_id,
        "answer": result["final_answer"],
        "called_agents": result.get("called_agents", []),
        "called_tools": result.get("called_tools", []),
        "shared_context": result.get("shared_context", {}),
        "active_agent": result.get("active_agent", "orchestrator"),
    }








