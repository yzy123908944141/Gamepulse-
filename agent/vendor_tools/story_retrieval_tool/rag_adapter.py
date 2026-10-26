from __future__ import annotations

import importlib.util
from pathlib import Path

from story_retrieval_tool.io_utils import sha256_text
from story_retrieval_tool.retriever import RetrievedChunk, StoryRetriever
from story_retrieval_tool.schemas import StoryChunk


class ChromaRagStoryRetriever(StoryRetriever):
    """Adapter for an external rag_query.py compatible module."""

    def __init__(
        self,
        rag_script_path: str | Path,
        chroma_dir: str | Path | None = None,
        embedding_model_path: str | Path | None = None,
        character_id: int | None = None,
        chapter: str | None = None,
    ) -> None:
        self.rag_script_path = Path(rag_script_path)
        self.chroma_dir = _resolve_chroma_dir(Path(chroma_dir)) if chroma_dir else None
        self.embedding_model_path = Path(embedding_model_path) if embedding_model_path else None
        self.character_id = character_id
        self.chapter = chapter
        self.module = self._load_module()

    def retrieve(self, query: str, top_k: int) -> list[RetrievedChunk]:
        raw_results = self.module.search_lore(
            query,
            character_id=self.character_id,
            chapter=self.chapter,
            top_k=top_k,
        )
        retrieved: list[RetrievedChunk] = []
        for index, item in enumerate(raw_results, 1):
            text = str(item.get("text", ""))
            source = str(item.get("source", "")) or "rag_query"
            event = str(item.get("event", ""))
            chapter = str(item.get("chapter", ""))
            chunk = StoryChunk(
                chunk_id=_chunk_id(item, text, index),
                source_file=source,
                chapter=chapter,
                scene=event,
                characters=[str(value) for value in item.get("character_ids", [])],
                content=text,
                source_hash=sha256_text(text),
            )
            distance = item.get("distance")
            score = 1.0 / (1.0 + float(distance)) if isinstance(distance, (int, float)) else 1.0
            retrieved.append(
                RetrievedChunk(
                    chunk=chunk,
                    score=score,
                    relevance=_relevance_from_distance(distance),
                )
            )
        return retrieved

    def _load_module(self):
        if not self.rag_script_path.exists():
            raise FileNotFoundError(f"找不到 RAG 脚本：{self.rag_script_path}")
        spec = importlib.util.spec_from_file_location(
            "external_rag_query",
            self.rag_script_path,
        )
        if spec is None or spec.loader is None:
            raise ImportError(f"无法加载 RAG 脚本：{self.rag_script_path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        if self.chroma_dir is not None:
            module.CHROMA_DIR = self.chroma_dir
        if self.embedding_model_path is not None:
            module.EMBEDDING_MODEL_PATH = str(self.embedding_model_path)
        if not hasattr(module, "search_lore"):
            raise AttributeError("RAG 脚本必须提供 search_lore(...) 函数")
        return module


def _chunk_id(item: dict, text: str, index: int) -> str:
    raw = "|".join(
        [
            str(item.get("source", "")),
            str(item.get("chapter", "")),
            str(item.get("event", "")),
            str(index),
            text,
        ]
    )
    return f"rag_{sha256_text(raw)[:12]}"


def _relevance_from_distance(distance) -> str:
    if not isinstance(distance, (int, float)):
        return "medium"
    if distance <= 0.25:
        return "high"
    if distance <= 0.55:
        return "medium"
    return "low"


def _resolve_chroma_dir(path: Path) -> Path:
    """Accept either the Chroma persist dir or its parent wrapper dir."""
    if (path / "chroma.sqlite3").exists():
        return path
    nested = path / "chroma_db"
    if (nested / "chroma.sqlite3").exists():
        return nested
    return path
