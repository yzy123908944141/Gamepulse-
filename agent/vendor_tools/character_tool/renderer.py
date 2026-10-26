from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from character_tool.io_utils import atomic_write_text


MAX_LINE_CHARS = 200
PLACEHOLDER = "-"


def render_markdown_document(summaries: list[dict[str, Any]], output_path: str | Path) -> None:
    lines = [
        "# 角色档案",
        "",
        "格式：角色名 → basic → traits → background → motivation → relations",
        "每个角色固定六行，角色之间空一行；缺失字段使用“-”占位。",
        "",
    ]
    for index, summary in enumerate(
        sorted(summaries, key=lambda item: item["metadata"]["character_id"])
    ):
        if index > 0:
            lines.append("")
        lines.extend(_render_character(summary))
    atomic_write_text(Path(output_path), "\n".join(lines).rstrip() + "\n")


def _render_character(data: dict[str, Any]) -> list[str]:
    metadata = data["metadata"]
    return [
        f"## {_clean(metadata.get('name')) or PLACEHOLDER}",
        _basic(data),
        _traits(data),
        _background(data),
        _motivation(data),
        _relations(data.get("relationships") or []),
    ]


def _basic(data: dict[str, Any]) -> str:
    basic = data.get("basic_info", {})
    values = [
        basic.get("occupation"),
        basic.get("identity"),
        basic.get("faction"),
    ]

    origin = basic.get("origin") if isinstance(basic.get("origin"), dict) else {}
    values.extend(
        [
            origin.get("birthplace"),
            origin.get("family_background"),
            origin.get("social_background"),
        ]
    )

    return _line("；".join(_clean(value) for value in values if _has_value(value)))


def _traits(data: dict[str, Any]) -> str:
    if _has_value(data.get("personality")):
        return _line(_dedupe_phrases(_clean(data["personality"])))

    personality = data.get("personality_traits") or {}
    if not isinstance(personality, dict):
        return PLACEHOLDER

    values: list[Any] = []
    for key in [
        "core_traits",
        "behavioral_patterns",
        "values",
        "strengths",
        "weaknesses",
        "internal_conflicts",
    ]:
        values.extend(_as_list(personality.get(key)))
    return _line(_dedupe_phrases("；".join(_clean(value) for value in values if _has_value(value))))


def _background(data: dict[str, Any]) -> str:
    if _has_value(data.get("background")) and not isinstance(data.get("background"), dict):
        return _line(_clean(data["background"]))

    background = data.get("background_summary") or {}
    if isinstance(background, dict):
        parts = [background.get("summary"), *(_as_list(background.get("key_events"))[:2])]
        return _line("；".join(_clean(part) for part in parts if _has_value(part)))
    return _line(background)


def _motivation(data: dict[str, Any]) -> str:
    if _has_value(data.get("motivation")) and not isinstance(data.get("motivation"), dict):
        return _line(_dedupe_phrases(_clean(data["motivation"])))

    motivation = data.get("goals_motivations") or {}
    if not isinstance(motivation, dict):
        return PLACEHOLDER

    values: list[Any] = []
    for key in [
        "core_goal",
        "short_term_goals",
        "long_term_goals",
        "behavior_drivers",
        "fears",
    ]:
        values.extend(_as_list(motivation.get(key)))
    return _line(_dedupe_phrases("；".join(_clean(value) for value in values if _has_value(value))))


def _relations(values: list[dict[str, Any]]) -> str:
    parts = []
    for item in values:
        if not isinstance(item, dict):
            continue
        name = item.get("name") or item.get("target_name")
        relation = item.get("relation") or item.get("relationship_type")
        detail = item.get("description")
        if not _has_value(name):
            continue
        relation_text = "、".join(
            _clean(value) for value in [relation, detail] if _has_value(value)
        )
        parts.append(f"{_clean(name)}={relation_text}" if relation_text else _clean(name))
    return _line("；".join(parts))


def _line(value: Any) -> str:
    text = _clean(value) if _has_value(value) else PLACEHOLDER
    if not text:
        return PLACEHOLDER
    return text if len(text) <= MAX_LINE_CHARS else text[:MAX_LINE_CHARS].rstrip("；,，、。") + "..."


def _has_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip()) and value.strip() not in {"null", "none", "未明确", PLACEHOLDER}
    if isinstance(value, list):
        return bool(value)
    return True


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _clean(value: Any) -> str:
    text = str(value).strip()
    text = re.sub(r"\s+", "", text)
    text = text.strip("；;，,。 ")
    return text


def _dedupe_phrases(text: str) -> str:
    phrases = re.split(r"[；;，,、。]+", text)
    result: list[str] = []
    seen: set[str] = set()
    for phrase in phrases:
        item = _clean(phrase)
        if not item or item in seen:
            continue
        seen.add(item)
        result.append(item)
    return "；".join(result)
