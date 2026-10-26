from __future__ import annotations

from typing import Any

from character_tool.schemas import CHARACTER_JSON_SCHEMA, SCHEMA_VERSION


class ValidationError(ValueError):
    pass


def validate_character_summary(data: dict[str, Any]) -> None:
    _validate_object(data, CHARACTER_JSON_SCHEMA, "root")
    _require_keys(
        data["metadata"],
        [
            "character_id",
            "name",
            "aliases",
            "player_controllable",
            "summarized",
            "source_hash",
            "schema_version",
        ],
        "metadata",
    )
    _require_keys(data["basic_info"], ["occupation", "identity", "faction"], "basic_info")

    for path in ["personality", "background", "motivation"]:
        if not isinstance(data[path], str):
            raise ValidationError(f"{path} 必须是字符串")

    if not isinstance(data["relationships"], list):
        raise ValidationError("relationships 必须是数组")
    for index, relationship in enumerate(data["relationships"]):
        if not isinstance(relationship, dict):
            raise ValidationError(f"relationships[{index}] 必须是对象")
        _require_keys(relationship, ["name", "relation"], f"relationships[{index}]")

    if data["metadata"]["schema_version"] != SCHEMA_VERSION:
        raise ValidationError("metadata.schema_version 不匹配")


def prepare_validated_summary(
    data: dict[str, Any],
    character_id: str,
    name: str,
    aliases: list[str],
    player_controllable: bool,
    source_hash: str,
) -> dict[str, Any]:
    metadata = data.setdefault("metadata", {})
    metadata["character_id"] = character_id
    metadata["name"] = name
    metadata["aliases"] = aliases
    metadata["player_controllable"] = player_controllable
    metadata["summarized"] = 1
    metadata["source_hash"] = source_hash
    metadata["schema_version"] = SCHEMA_VERSION
    validate_character_summary(data)
    return data


def _validate_object(data: Any, schema: dict[str, Any], path: str) -> None:
    if schema.get("type") == "object" and not isinstance(data, dict):
        raise ValidationError(f"{path} 必须是对象")
    for key in schema.get("required", []):
        if key not in data:
            raise ValidationError(f"{path} 缺少字段：{key}")
    allowed = set(schema.get("properties", {}).keys())
    if schema.get("additionalProperties") is False:
        extra = sorted(set(data.keys()) - allowed)
        if extra:
            raise ValidationError(f"{path} 包含不允许的字段：{', '.join(extra)}")


def _require_keys(data: dict[str, Any], keys: list[str], path: str) -> None:
    if not isinstance(data, dict):
        raise ValidationError(f"{path} 必须是对象")
    for key in keys:
        if key not in data:
            raise ValidationError(f"{path} 缺少字段：{key}")
