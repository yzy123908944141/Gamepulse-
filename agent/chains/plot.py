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


PLOT_AGENT_SYSTEM_PROMPT = _load_prompt("plot_prompt.txt")

_FALLBACK_PLOT_PROMPT = """
你是 GamerPulse 的剧情审查 Agent。
你专门处理剧情结构、剧情推进、桥段设计、章节安排、伏笔铺垫与回收等问题。
请结合已有角色审查结果，给出面向策划落地的剧情建议，避免脱离已知角色设定。
""".strip()

_PLOT_HUMAN_TEMPLATE = """
以下是当前对话的历史摘要：
{chat_history}

当前共享上下文：
{shared_context}

用户本轮问题：
{user_input}

请从剧情审查角度回答，并尽量与已给出的角色判断保持一致。
""".strip()


def _get_plot_chain():
    system_prompt = PLOT_AGENT_SYSTEM_PROMPT or _FALLBACK_PLOT_PROMPT
    return build_text_chain(system_prompt, _PLOT_HUMAN_TEMPLATE, temperature=0.2)


def _normalize_shared_context(shared_context: dict[str, Any] | None) -> str:
    if not shared_context:
        return "暂无"
    lines = []
    for key, value in shared_context.items():
        lines.append(f"- {key}: {value}")
    return "\n".join(lines)


def run_plot_chain(
    *,
    user_input: str,
    chat_history: str,
    shared_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    chain = _get_plot_chain()
    answer = chain.invoke(
        {
            "chat_history": chat_history or "暂无",
            "shared_context": _normalize_shared_context(shared_context),
            "user_input": user_input,
        }
    )
    return {
        "agent": "plot",
        "answer": answer,
        "plot_context": answer,
    }
