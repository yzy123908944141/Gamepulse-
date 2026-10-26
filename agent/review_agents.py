from __future__ import annotations

from contextvars import ContextVar
from copy import copy
from typing import Any, Callable

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.tools import BaseTool, tool
from langgraph.prebuilt import create_react_agent

from agent.chains.character import CHARACTER_AGENT_SYSTEM_PROMPT
from agent.chains.common import get_chat_model
from agent.chains.plot import PLOT_AGENT_SYSTEM_PROMPT
from agent.langchain_memory import build_history_text, get_memory
from tools.query_tools import (
    get_character_profiles,
    get_world_lore_tool,
    rag_search_story,
    rewrite_script,
    search_risk_cards,
)
from tools.generate_sentiment_report_md import generate_global_sentiment_report_md
from tools.sentiment_report_tool import (
    generate_sentiment_report_tool,
    get_red_lines_tool,
    get_sentiment_trend_tool,
    get_top_complaints_tool,
)


ToolEventSink = Callable[[dict[str, Any]], None]
_CURRENT_TOOL_EVENT_SINK: ContextVar[ToolEventSink | None] = ContextVar("gamepulse_tool_event_sink", default=None)


def set_tool_event_sink(sink: ToolEventSink | None):
    return _CURRENT_TOOL_EVENT_SINK.set(sink)


def reset_tool_event_sink(token) -> None:
    _CURRENT_TOOL_EVENT_SINK.reset(token)


def _emit_call_event(event_type: str, name: str, *, kind: str = "tool", detail: str = "") -> None:
    sink = _CURRENT_TOOL_EVENT_SINK.get()
    if sink is None:
        return
    sink({"type": event_type, "kind": kind, "name": name, "detail": detail})

@tool("generate_sentiment_report_md")
def generate_sentiment_report_md_tool() -> dict[str, Any]:
    """生成全局舆情 Markdown 报告文件，返回文件路径和基础统计信息。"""
    return generate_global_sentiment_report_md()




def _track_tool_calls(tools: list[BaseTool], called_tools: list[str]) -> list[BaseTool]:
    tracked_tools: list[BaseTool] = []
    for original_tool in tools:
        tracked_tool = copy(original_tool)
        tool_name = getattr(tracked_tool, "name", tracked_tool.__class__.__name__)
        original_func = getattr(tracked_tool, "func", None)
        original_coroutine = getattr(tracked_tool, "coroutine", None)

        if original_func is not None:
            def tracked_func(*args: Any, _func=original_func, _name=tool_name, **kwargs: Any) -> Any:
                called_tools.append(_name)
                _emit_call_event("tool_start", _name)
                try:
                    result = _func(*args, **kwargs)
                except Exception as exc:
                    _emit_call_event("tool_error", _name, detail=exc.__class__.__name__)
                    raise
                _emit_call_event("tool_end", _name)
                return result

            tracked_tool.func = tracked_func

        if original_coroutine is not None:
            async def tracked_coroutine(*args: Any, _coroutine=original_coroutine, _name=tool_name, **kwargs: Any) -> Any:
                called_tools.append(_name)
                _emit_call_event("tool_start", _name)
                try:
                    result = await _coroutine(*args, **kwargs)
                except Exception as exc:
                    _emit_call_event("tool_error", _name, detail=exc.__class__.__name__)
                    raise
                _emit_call_event("tool_end", _name)
                return result

            tracked_tool.coroutine = tracked_coroutine

        tracked_tools.append(tracked_tool)
    return tracked_tools
def _load_history(session_id: int) -> str:
    memory = get_memory(session_id)
    return build_history_text(memory)


def _normalize_shared_context(shared_context: dict[str, Any] | None) -> str:
    if not shared_context:
        return "暂无"
    return "\n".join(f"- {key}: {value}" for key, value in shared_context.items())


def _build_agent_input(
    *,
    user_input: str,
    chat_history: str,
    shared_context: dict[str, Any] | None,
) -> list[BaseMessage]:
    content = (
        f"历史对话摘要：\n{chat_history or '暂无'}\n\n"
        f"当前共享上下文：\n{_normalize_shared_context(shared_context)}\n\n"
        f"当前请求：\n{user_input}"
    )
    return [HumanMessage(content=content)]


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


def _get_character_system_prompt() -> str:
    return CHARACTER_AGENT_SYSTEM_PROMPT or (
        "你是 GamerPulse 的角色审查 Agent。"
        "你专门处理角色人设、角色动机、角色台词、OOC 风险、角色差异化、角色舆情风险等问题。"
        "必要时你可以调用 plot_review_tool，请剧情 Agent 协同处理剧情结构、桥段推进、章节安排和伏笔回收问题。"
        "你要优先回答角色问题，并整合工具结果给出具体建议。"
    )


def _get_plot_system_prompt() -> str:
    return PLOT_AGENT_SYSTEM_PROMPT or (
        "你是 GamerPulse 的剧情审查 Agent。"
        "你专门处理剧情结构、章节安排、桥段设计、伏笔铺垫与回收、主支线编排等问题。"
        "回答时应尊重已有角色设定和共享上下文。"
    )


def build_plot_agent(
    *,
    session_id: int,
    shared_context: dict[str, Any],
    called_agents: list[str],
    called_tools: list[str],
):
    plot_tools: list[BaseTool] = [
        rag_search_story,
        get_world_lore_tool,
        get_character_profiles,
        search_risk_cards,
        rewrite_script,
    ]
    return create_react_agent(
        model=get_chat_model(temperature=0.2),
        tools=_track_tool_calls(plot_tools, called_tools),
        prompt=_get_plot_system_prompt(),
    )


def build_plot_review_tool(
    *,
    session_id: int,
    shared_context: dict[str, Any],
    called_agents: list[str],
    called_tools: list[str],
) -> BaseTool:
    @tool("plot_review_tool")
    def plot_review_tool(user_input: str) -> str:
        """调用剧情审查 Agent，处理剧情结构、章节安排、桥段推进和伏笔回收等问题。"""
        called_agents.append("plot")
        _emit_call_event("agent_start", "plot", kind="agent")
        agent = build_plot_agent(
            session_id=session_id,
            shared_context=shared_context,
            called_agents=called_agents,
            called_tools=called_tools,
        )
        result = agent.invoke(
            {
                "messages": _build_agent_input(
                    user_input=user_input,
                    chat_history=_load_history(session_id),
                    shared_context=shared_context,
                )
            }
        )
        answer = _extract_text(result)
        shared_context["plot"] = answer
        return answer

    return plot_review_tool


def build_character_agent(
    *,
    session_id: int,
    shared_context: dict[str, Any],
    called_agents: list[str],
    called_tools: list[str],
):
    plot_tool = build_plot_review_tool(
        session_id=session_id,
        shared_context=shared_context,
        called_agents=called_agents,
        called_tools=called_tools,
    )
    character_tools: list[BaseTool] = [
        get_character_profiles,
        get_world_lore_tool,
        search_risk_cards,
        rag_search_story,
        rewrite_script,
        plot_tool,
    ]
    return create_react_agent(
        model=get_chat_model(temperature=0.2),
        tools=_track_tool_calls(character_tools, called_tools),
        prompt=_get_character_system_prompt(),
    )


def build_character_review_tool(
    *,
    session_id: int,
    shared_context: dict[str, Any],
    called_agents: list[str],
    called_tools: list[str],
) -> BaseTool:
    @tool("character_review_tool")
    def character_review_tool(user_input: str) -> str:
        """调用角色审查 Agent，处理角色人设、OOC、角色差异化与角色舆情风险等问题。"""
        called_agents.append("character")
        _emit_call_event("agent_start", "character", kind="agent")
        agent = build_character_agent(
            session_id=session_id,
            shared_context=shared_context,
            called_agents=called_agents,
            called_tools=called_tools,
        )
        result = agent.invoke(
            {
                "messages": _build_agent_input(
                    user_input=user_input,
                    chat_history=_load_history(session_id),
                    shared_context=shared_context,
                )
            }
        )
        answer = _extract_text(result)
        shared_context["character"] = answer
        return answer

    return character_review_tool


def build_supervisor_tools(
    *,
    session_id: int,
    shared_context: dict[str, Any],
    called_agents: list[str],
    called_tools: list[str],
) -> list[BaseTool]:
    supervisor_tools = [
        generate_sentiment_report_tool,
        generate_sentiment_report_md_tool,
        get_red_lines_tool,
        get_top_complaints_tool,
        get_sentiment_trend_tool,
        build_character_review_tool(
            session_id=session_id,
            shared_context=shared_context,
            called_agents=called_agents,
            called_tools=called_tools,
        ),
        build_plot_review_tool(
            session_id=session_id,
            shared_context=shared_context,
            called_agents=called_agents,
            called_tools=called_tools,
        ),
    ]
    return _track_tool_calls(supervisor_tools, called_tools)






