from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from story_retrieval_tool.chunker import chunk_story_file
from story_retrieval_tool.io_utils import atomic_write_json, read_json, sha256_text
from story_retrieval_tool.schemas import StoryChunk


LOGGER = logging.getLogger(__name__)
INDEX_DIRNAME = ".story_index"
INDEX_FILENAME = "story_index.json"


@dataclass(frozen=True)
class SourceIndexItem:
    source_file: str
    source_hash: str
    chunk_ids: list[str]
    error: str = ""


def build_or_load_index(
    story_library_path: str | Path,
    force_reindex: bool = False,
) -> tuple[list[StoryChunk], list[str]]:
    root = Path(story_library_path)
    warnings: list[str] = []
    if not root.exists():
        raise FileNotFoundError(f"剧情资料目录不存在：{root}")
    if not root.is_dir():
        raise NotADirectoryError(f"剧情资料路径不是目录：{root}")

    index_path = root / INDEX_DIRNAME / INDEX_FILENAME
    old_sources, old_chunks = _load_index(index_path)
    new_sources: dict[str, SourceIndexItem] = {}
    new_chunks: dict[str, StoryChunk] = {}

    files = [
        path
        for path in sorted(root.rglob("*"))
        if path.is_file()
        and path.suffix.lower() in {".txt", ".md"}
        and INDEX_DIRNAME not in path.parts
    ]

    for path in files:
        relative_source = path.relative_to(root).as_posix()
        try:
            content = path.read_text(encoding="utf-8-sig")
            source_hash = sha256_text(content)
            old_item = old_sources.get(relative_source)
            if (
                not force_reindex
                and old_item
                and old_item.source_hash == source_hash
                and all(chunk_id in old_chunks for chunk_id in old_item.chunk_ids)
            ):
                chunk_ids = old_item.chunk_ids
                for chunk_id in chunk_ids:
                    new_chunks[chunk_id] = old_chunks[chunk_id]
                new_sources[relative_source] = old_item
                continue

            chunks = chunk_story_file(path, root)
            chunk_ids = []
            for chunk in chunks:
                chunk_ids.append(chunk.chunk_id)
                new_chunks[chunk.chunk_id] = chunk
            new_sources[relative_source] = SourceIndexItem(
                source_file=relative_source,
                source_hash=source_hash,
                chunk_ids=chunk_ids,
            )
            LOGGER.info("已索引剧情文件：%s，片段数：%s", relative_source, len(chunks))
        except Exception as exc:
            warning = f"解析剧情文件失败：{relative_source}：{exc}"
            warnings.append(warning)
            LOGGER.exception(warning)

    _save_index(index_path, new_sources, new_chunks)
    return list(new_chunks.values()), warnings


def _load_index(index_path: Path) -> tuple[dict[str, SourceIndexItem], dict[str, StoryChunk]]:
    if not index_path.exists():
        return {}, {}
    try:
        raw = read_json(index_path)
    except Exception:
        return {}, {}

    sources = {
        source_file: SourceIndexItem(
            source_file=source_file,
            source_hash=str(item.get("source_hash", "")),
            chunk_ids=list(item.get("chunk_ids", [])),
            error=str(item.get("error", "")),
        )
        for source_file, item in raw.get("sources", {}).items()
    }
    chunks = {
        chunk["chunk_id"]: StoryChunk(
            chunk_id=chunk["chunk_id"],
            source_file=chunk["source_file"],
            chapter=chunk.get("chapter", ""),
            scene=chunk.get("scene", ""),
            characters=list(chunk.get("characters", [])),
            content=chunk.get("content", ""),
            source_hash=chunk.get("source_hash", ""),
        )
        for chunk in raw.get("chunks", [])
        if chunk.get("chunk_id")
    }
    return sources, chunks


def _save_index(
    index_path: Path,
    sources: dict[str, SourceIndexItem],
    chunks: dict[str, StoryChunk],
) -> None:
    payload: dict[str, Any] = {
        "sources": {
            key: asdict(value) for key, value in sorted(sources.items(), key=lambda item: item[0])
        },
        "chunks": [
            chunk.to_dict()
            for chunk in sorted(chunks.values(), key=lambda item: item.chunk_id)
        ],
    }
    atomic_write_json(index_path, payload)
