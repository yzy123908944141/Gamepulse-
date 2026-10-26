from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


CONFIDENCE_VALUES = {"low", "medium", "high"}


@dataclass(frozen=True)
class StoryQueryRequest:
    query: str
    story_library_path: str = "./story_library"
    top_k: int = 8
    force_reindex: bool = False
    retriever: str = "keyword"
    rag_script_path: str | None = None
    chroma_dir: str | None = None
    embedding_model_path: str | None = None
    character_id: int | None = None
    chapter: str | None = None


@dataclass(frozen=True)
class StoryChunk:
    chunk_id: str
    source_file: str
    chapter: str
    scene: str
    characters: list[str]
    content: str
    source_hash: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class StoryContextResult:
    query: str
    characters: list[dict[str, Any]]
    story: dict[str, Any]
    background_setting: dict[str, Any]
    source_refs: list[dict[str, str]]
    information_gaps: list[str]
    confidence: str
    success: bool = True
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


STORY_CONTEXT_INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "query": {"type": "string", "minLength": 1},
        "story_library_path": {"type": "string", "default": "./story_library"},
        "top_k": {"type": "integer", "minimum": 1, "maximum": 20, "default": 8},
        "force_reindex": {"type": "boolean", "default": False},
        "retriever": {
            "type": "string",
            "enum": ["keyword", "chroma-rag"],
            "default": "keyword",
        },
        "rag_script_path": {
            "type": ["string", "null"],
            "default": None,
        },
        "chroma_dir": {
            "type": ["string", "null"],
            "default": None,
        },
        "embedding_model_path": {
            "type": ["string", "null"],
            "default": None,
        },
        "character_id": {
            "type": ["integer", "null"],
            "default": None,
        },
        "chapter": {
            "type": ["string", "null"],
            "default": None,
        },
    },
    "required": ["query"],
    "additionalProperties": False,
}


STORY_CONTEXT_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "query": {"type": "string"},
        "characters": {"type": "array"},
        "story": {"type": "object"},
        "background_setting": {"type": "object"},
        "source_refs": {"type": "array"},
        "information_gaps": {"type": "array"},
        "confidence": {"type": "string", "enum": sorted(CONFIDENCE_VALUES)},
    },
    "required": [
        "query",
        "characters",
        "story",
        "background_setting",
        "source_refs",
        "information_gaps",
        "confidence",
    ],
    "additionalProperties": True,
}


STORY_CHUNK_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": [
        "chunk_id",
        "source_file",
        "chapter",
        "scene",
        "characters",
        "content",
        "source_hash",
    ],
}
