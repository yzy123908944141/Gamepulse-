from __future__ import annotations

import re
from pathlib import Path

from story_retrieval_tool.io_utils import sha256_text
from story_retrieval_tool.schemas import StoryChunk


CHUNK_TARGET_CHARS = 1200
CHUNK_OVERLAP_CHARS = 180


def chunk_story_file(path: Path, root: Path) -> list[StoryChunk]:
    content = path.read_text(encoding="utf-8-sig")
    source_hash = sha256_text(content)
    relative_source = path.relative_to(root).as_posix()
    titled = _chunks_by_headings(content, relative_source, source_hash)
    if titled:
        return titled
    return _chunks_by_length(content, relative_source, source_hash)


def _chunks_by_headings(
    content: str,
    source_file: str,
    source_hash: str,
) -> list[StoryChunk]:
    chunks: list[StoryChunk] = []
    current_chapter = ""
    current_scene = ""
    current_title = ""
    current_body: list[str] = []
    counter = 0

    def flush() -> None:
        nonlocal counter, current_body
        body = "\n".join(current_body).strip()
        if not current_title or not body:
            return
        counter += 1
        chunks.append(
            StoryChunk(
                chunk_id=_chunk_id(source_file, counter, current_title, body),
                source_file=source_file,
                chapter=current_chapter,
                scene=current_scene or current_title,
                characters=_extract_characters(body),
                content=body,
                source_hash=source_hash,
            )
        )

    for raw_line in content.splitlines():
        match = re.match(r"^(#{1,3})\s+(.+?)\s*$", raw_line)
        if match:
            flush()
            level = len(match.group(1))
            title = match.group(2).strip()
            if level == 1:
                current_chapter = title
                current_scene = ""
            elif level == 2:
                current_chapter = current_chapter or title
                current_scene = title
            else:
                current_scene = title
            current_title = title
            current_body = []
            continue
        current_body.append(raw_line)

    flush()
    return chunks


def _chunks_by_length(
    content: str,
    source_file: str,
    source_hash: str,
) -> list[StoryChunk]:
    normalized = content.strip()
    if not normalized:
        return []

    chunks: list[StoryChunk] = []
    start = 0
    counter = 0
    while start < len(normalized):
        end = min(len(normalized), start + CHUNK_TARGET_CHARS)
        if end < len(normalized):
            sentence_end = max(normalized.rfind("。", start, end), normalized.rfind("\n", start, end))
            if sentence_end > start + CHUNK_TARGET_CHARS // 2:
                end = sentence_end + 1
        body = normalized[start:end].strip()
        if body:
            counter += 1
            scene = f"片段{counter}"
            chunks.append(
                StoryChunk(
                    chunk_id=_chunk_id(source_file, counter, scene, body),
                    source_file=source_file,
                    chapter="",
                    scene=scene,
                    characters=_extract_characters(body),
                    content=body,
                    source_hash=source_hash,
                )
            )
        if end >= len(normalized):
            break
        start = max(0, end - CHUNK_OVERLAP_CHARS)
    return chunks


def _extract_characters(text: str) -> list[str]:
    names: list[str] = []
    for match in re.finditer(r"(?:角色|人物|登场人物)[:：]\s*([^\n]+)", text):
        for part in re.split(r"[、,，；;]\s*", match.group(1)):
            name = part.strip()
            if name and name not in names:
                names.append(name)
    return names[:12]


def _chunk_id(source_file: str, counter: int, title: str, content: str) -> str:
    digest = sha256_text(f"{source_file}:{counter}:{title}:{content}")[:12]
    return f"story_{digest}"
