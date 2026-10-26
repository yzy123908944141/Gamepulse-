from __future__ import annotations

from typing import Any

from story_retrieval_tool.schemas import CONFIDENCE_VALUES


class ValidationError(ValueError):
    pass


def validate_story_context(data: dict[str, Any]) -> None:
    _require_keys(
        data,
        [
            "query",
            "characters",
            "story",
            "background_setting",
            "source_refs",
            "information_gaps",
            "confidence",
        ],
        "root",
    )
    if data["confidence"] not in CONFIDENCE_VALUES:
        raise ValidationError("confidence 只能是 low、medium 或 high")
    if not isinstance(data["characters"], list):
        raise ValidationError("characters 必须是数组")
    if not isinstance(data["source_refs"], list):
        raise ValidationError("source_refs 必须是数组")
    if not isinstance(data["information_gaps"], list):
        raise ValidationError("information_gaps 必须是数组")
    _require_keys(data["story"], ["summary", "key_events", "main_conflict", "result"], "story")
    _require_keys(
        data["background_setting"],
        ["locations", "factions", "world_rules", "historical_context"],
        "background_setting",
    )
    for index, character in enumerate(data["characters"]):
        _require_keys(
            character,
            ["name", "personality", "motivation", "role_in_story"],
            f"characters[{index}]",
        )
        if not isinstance(character["personality"], list):
            raise ValidationError(f"characters[{index}].personality 必须是数组")
        if not isinstance(character["motivation"], list):
            raise ValidationError(f"characters[{index}].motivation 必须是数组")
    for index, event in enumerate(data["story"]["key_events"]):
        _require_keys(event, ["order", "event", "participants"], f"story.key_events[{index}]")
        if not isinstance(event["participants"], list):
            raise ValidationError(f"story.key_events[{index}].participants 必须是数组")


def ensure_source_refs(data: dict[str, Any], retrieved_chunks: list[dict[str, Any]]) -> dict[str, Any]:
    allowed = {chunk["chunk_id"]: chunk for chunk in retrieved_chunks}
    refs = []
    for ref in data.get("source_refs", []):
        chunk_id = str(ref.get("chunk_id", ""))
        if chunk_id in allowed:
            refs.append(
                {
                    "chunk_id": chunk_id,
                    "source": allowed[chunk_id]["source_file"],
                    "relevance": str(ref.get("relevance", "")) or "模型认为相关",
                }
            )
    if not refs:
        refs = [
            {
                "chunk_id": chunk["chunk_id"],
                "source": chunk["source_file"],
                "relevance": "检索命中",
            }
            for chunk in retrieved_chunks
        ]
    data["source_refs"] = refs
    return data


def _require_keys(data: Any, keys: list[str], path: str) -> None:
    if not isinstance(data, dict):
        raise ValidationError(f"{path} 必须是对象")
    for key in keys:
        if key not in data:
            raise ValidationError(f"{path} 缺少字段：{key}")
