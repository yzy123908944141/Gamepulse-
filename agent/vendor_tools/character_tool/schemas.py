from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


SCHEMA_VERSION = "1.2"


@dataclass(frozen=True)
class CharacterSource:
    character_id: str
    name: str
    background_story: str
    personal_profile: str
    aliases: list[str] = field(default_factory=list)
    player_controllable: bool = True
    source_path: str = ""
    source_updated_at: str = ""
    status: str = "active"

    @property
    def combined_source(self) -> str:
        return f"{self.background_story}\n\n{self.personal_profile}"


@dataclass(frozen=True)
class CharacterIndexItem:
    character_id: str
    name: str
    summarized: int
    source_hash: str
    source_updated_at: str
    summary_updated_at: str
    status: str = "active"
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CharacterScanResult:
    success: bool
    total_characters: int
    new_characters: int
    updated_characters: int
    skipped_characters: int
    failed_characters: int
    processed_character_ids: list[str]
    failed_items: list[dict[str, str]]
    document_path: str
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


CHARACTER_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": [
        "metadata",
        "basic_info",
        "personality",
        "background",
        "motivation",
        "relationships",
    ],
    "properties": {
        "metadata": {"type": "object"},
        "basic_info": {"type": "object"},
        "personality": {"type": "string"},
        "background": {"type": "string"},
        "motivation": {"type": "string"},
        "relationships": {"type": "array"},
    },
    "additionalProperties": False,
}


CHARACTER_SCAN_INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "character_library_path": {
            "type": "string",
            "description": "角色库目录或 SQLite 数据库路径。",
            "default": "./characters",
        },
        "output_json_path": {
            "type": "string",
            "description": "结构化角色 JSON 输出目录。",
            "default": "./outputs/character_json",
        },
        "output_document_path": {
            "type": "string",
            "description": "Markdown 角色档案汇总输出路径。",
            "default": "./outputs/角色档案汇总.md",
        },
        "force_rescan": {
            "type": "boolean",
            "description": "是否忽略索引状态并重新总结全部角色。",
            "default": False,
        },
        "limit": {
            "type": ["integer", "null"],
            "description": "仅处理前 N 个角色，用于小样本测试。为空时处理全部角色。",
            "minimum": 1,
            "default": None,
        },
    },
    "required": ["character_library_path"],
    "additionalProperties": False,
}


CHARACTER_SCAN_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "success": {"type": "boolean"},
        "total_characters": {"type": "integer"},
        "new_characters": {"type": "integer"},
        "updated_characters": {"type": "integer"},
        "skipped_characters": {"type": "integer"},
        "failed_characters": {"type": "integer"},
        "processed_character_ids": {"type": "array", "items": {"type": "string"}},
        "failed_items": {"type": "array", "items": {"type": "object"}},
        "document_path": {"type": "string"},
        "warnings": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "success",
        "total_characters",
        "new_characters",
        "updated_characters",
        "skipped_characters",
        "failed_characters",
        "processed_character_ids",
        "failed_items",
        "document_path",
        "warnings",
    ],
    "additionalProperties": False,
}
