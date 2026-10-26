from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


SUPPORTED_SECTIONS = {
    "world_overview": "世界总览",
    "world_rules": "世界运行的核心逻辑",
    "disaster_system": "灾害体系",
    "echo_and_sonoro": "回音、残响与索诺拉",
    "resonators": "共鸣者",
    "civilization_entities": "文明级存在",
    "regions_and_factions": "主要组织与地区",
    "rover": "漂泊者",
}


@dataclass(frozen=True)
class WorldLoreRequest:
    query: str
    section: str | None = None
    max_chars: int = 3000


@dataclass(frozen=True)
class WorldLoreResult:
    success: bool
    query: str
    matched_sections: list[str]
    content: str
    source: str = "data/world.txt"
    truncated: bool = False
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "query": {
            "type": "string",
            "description": "Agent 想查询的《鸣潮》世界观问题或主题。",
            "minLength": 1,
        },
        "section": {
            "type": ["string", "null"],
            "description": "可选检索范围。为空时检索全部世界观文档。",
            "enum": [None, *SUPPORTED_SECTIONS.keys()],
            "default": None,
        },
        "max_chars": {
            "type": "integer",
            "description": "返回 content 的最大字符数。",
            "minimum": 1,
            "maximum": 12000,
            "default": 3000,
        },
    },
    "required": ["query"],
    "additionalProperties": False,
}


OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "success": {"type": "boolean"},
        "query": {"type": "string"},
        "matched_sections": {"type": "array", "items": {"type": "string"}},
        "content": {"type": "string"},
        "source": {"type": "string", "const": "data/world.txt"},
        "truncated": {"type": "boolean"},
        "warnings": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "success",
        "query",
        "matched_sections",
        "content",
        "source",
        "truncated",
        "warnings",
    ],
    "additionalProperties": False,
}
