from __future__ import annotations

from pathlib import Path
from typing import Any

from agent.chains.common import build_text_chain


def _load_prompt(filename: str) -> str:
    path = Path(__file__).resolve().parents[1] / "prompts" / filename
    try:
        return path.read_text(encoding="utf-8-sig").strip()
    except OSError:
        return ""


CHARACTER_AGENT_SYSTEM_PROMPT = _load_prompt("character_prompt.txt")

_FALLBACK_CHARACTER_PROMPT = """
你是 GamerPulse 的角色审查 Agent。
你专门回答角色人设相关问题，帮助策划判断角色设定是否成立、是否 OOC、是否撞人设、是否存在舆情风险。
如果问题开始明显涉及剧情结构、桥段推进、章节安排、伏笔回收，请先完成角色层判断，再明确指出需要剧情 Agent 继续协同。
回答要具体、可执行、面向策划落地。
""".strip()

_CHARACTER_HUMAN_TEMPLATE = """
以下是当前对话的历史摘要：
{chat_history}

当前共享上下文：
{shared_context}

用户本轮问题：
{user_input}

请只从角色审查角度回答。如果你认为这个问题还需要剧情 Agent 协同，请在回答结尾单独加一行：
NEED_PLOT_AGENT: yes
否则加：
NEED_PLOT_AGENT: no
""".strip()


def _get_character_chain():
    system_prompt = CHARACTER_AGENT_SYSTEM_PROMPT or _FALLBACK_CHARACTER_PROMPT
    return build_text_chain(system_prompt, _CHARACTER_HUMAN_TEMPLATE, temperature=0.2)


def _normalize_shared_context(shared_context: dict[str, Any] | None) -> str:
    if not shared_context:
        return "暂无"
    lines = []
    for key, value in shared_context.items():
        lines.append(f"- {key}: {value}")
    return "\n".join(lines)


def needs_plot_agent(user_input: str, answer: str) -> bool:
    keywords = [
        "剧情",
        "桥段",
        "章节",
        "登场时机",
        "伏笔",
        "回收",
        "主线",
        "支线",
        "节奏",
    ]
    if "NEED_PLOT_AGENT: yes" in answer:
        return True
    return any(keyword in user_input for keyword in keywords)


def strip_route_marker(answer: str) -> str:
    return (
        answer.replace("NEED_PLOT_AGENT: yes", "")
        .replace("NEED_PLOT_AGENT: no", "")
        .strip()
    )


def run_character_chain(
    *,
    user_input: str,
    chat_history: str,
    shared_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    chain = _get_character_chain()
    raw_answer = chain.invoke(
        {
            "chat_history": chat_history or "暂无",
            "shared_context": _normalize_shared_context(shared_context),
            "user_input": user_input,
        }
    )
    answer = strip_route_marker(raw_answer)
    return {
        "agent": "character",
        "answer": answer,
        "need_plot_agent": needs_plot_agent(user_input, raw_answer),
        "character_context": answer,
    }
