from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from character_tool.index import load_index, save_index
from character_tool.io_utils import atomic_write_json, read_json, sha256_text
from character_tool.renderer import render_markdown_document
from character_tool.scanner import scan_sources
from character_tool.schemas import (
    CHARACTER_SCAN_INPUT_SCHEMA,
    CHARACTER_SCAN_OUTPUT_SCHEMA,
    SCHEMA_VERSION,
    CharacterIndexItem,
    CharacterScanResult,
)
from character_tool.summarizer import CharacterSummarizer, MockCharacterSummarizer
from character_tool.validator import ValidationError, prepare_validated_summary


LOGGER = logging.getLogger(__name__)


CHARACTER_SCAN_TOOL_SPEC = {
    "name": "scan_character_library",
    "description": (
        "扫描角色库，对新增或原文变化的角色调用总结器，生成只包含基本信息、性格特征、"
        "背景概括、目标动机和主要关系的结构化 JSON，并渲染完整 Markdown 汇总。"
        "本工具只负责角色资料结构化与增量状态管理，不负责角色评价、剧情质量评价、舆情总结或总控 Agent 编排。"
    ),
    "input_schema": CHARACTER_SCAN_INPUT_SCHEMA,
    "output_schema": CHARACTER_SCAN_OUTPUT_SCHEMA,
}


def scan_character_library(
    character_library_path: str = "./characters",
    output_json_path: str = "./outputs/character_json",
    output_document_path: str = "./outputs/角色档案汇总.md",
    force_rescan: bool = False,
    limit: int | None = None,
    *,
    summarizer: CharacterSummarizer | None = None,
    max_retries: int = 2,
) -> dict[str, Any]:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
    summarizer = summarizer or MockCharacterSummarizer()
    output_json_dir = Path(output_json_path)
    output_json_dir.mkdir(parents=True, exist_ok=True)

    try:
        all_sources = scan_sources(character_library_path)
    except Exception as exc:
        return CharacterScanResult(
            success=False,
            total_characters=0,
            new_characters=0,
            updated_characters=0,
            skipped_characters=0,
            failed_characters=0,
            processed_character_ids=[],
            failed_items=[{"character_id": "", "name": "", "error": str(exc)}],
            document_path=output_document_path,
            warnings=[str(exc)],
        ).to_dict()

    if limit is not None and limit < 1:
        return CharacterScanResult(
            success=False,
            total_characters=0,
            new_characters=0,
            updated_characters=0,
            skipped_characters=0,
            failed_characters=0,
            processed_character_ids=[],
            failed_items=[],
            document_path=output_document_path,
            warnings=["limit 必须大于 0。"],
        ).to_dict()

    sources = all_sources[:limit] if limit is not None else all_sources
    index = load_index(output_json_dir)
    if limit is None:
        known_source_ids = {source.character_id for source in all_sources}
        for character_id, item in list(index.items()):
            if character_id not in known_source_ids:
                index[character_id] = CharacterIndexItem(
                    character_id=item.character_id,
                    name=item.name,
                    summarized=0,
                    source_hash=item.source_hash,
                    source_updated_at=item.source_updated_at,
                    summary_updated_at=item.summary_updated_at,
                    status="missing",
                    error="角色源文件已不存在。",
                )

    new_count = 0
    updated_count = 0
    skipped_count = 0
    failed_items: list[dict[str, str]] = []
    processed_ids: list[str] = []

    for source in sources:
        source_hash = sha256_text(source.combined_source)
        previous = index.get(source.character_id)
        is_new = previous is None
        needs_summary = (
            force_rescan
            or is_new
            or previous.summarized != 1
            or previous.source_hash != source_hash
            or not _has_current_summary(output_json_dir, source.character_id)
        )

        if not needs_summary:
            skipped_count += 1
            index[source.character_id] = CharacterIndexItem(
                character_id=source.character_id,
                name=source.name,
                summarized=1,
                source_hash=source_hash,
                source_updated_at=source.source_updated_at,
                summary_updated_at=previous.summary_updated_at,
                status=source.status,
            )
            continue

        if is_new:
            new_count += 1
        else:
            updated_count += 1

        try:
            summary = _summarize_with_retries(source, source_hash, summarizer, max_retries)
            atomic_write_json(_summary_json_path(output_json_dir, source.character_id), summary)
            now = _now_iso()
            index[source.character_id] = CharacterIndexItem(
                character_id=source.character_id,
                name=source.name,
                summarized=1,
                source_hash=source_hash,
                source_updated_at=source.source_updated_at,
                summary_updated_at=now,
                status=source.status,
            )
            processed_ids.append(source.character_id)
            LOGGER.info("已总结角色：%s %s", source.character_id, source.name)
        except Exception as exc:
            error = str(exc)
            failed_items.append(
                {"character_id": source.character_id, "name": source.name, "error": error}
            )
            index[source.character_id] = CharacterIndexItem(
                character_id=source.character_id,
                name=source.name,
                summarized=0,
                source_hash=source_hash,
                source_updated_at=source.source_updated_at,
                summary_updated_at=previous.summary_updated_at if previous else "",
                status=source.status,
                error=error,
            )
            LOGGER.exception("角色总结失败：%s %s", source.character_id, source.name)

    save_index(output_json_dir, index)
    summaries = _load_active_summaries(output_json_dir, index)
    render_markdown_document(summaries, output_document_path)

    failed_count = len(failed_items)
    return CharacterScanResult(
        success=failed_count == 0,
        total_characters=len(sources),
        new_characters=new_count,
        updated_characters=updated_count,
        skipped_characters=skipped_count,
        failed_characters=failed_count,
        processed_character_ids=processed_ids,
        failed_items=failed_items,
        document_path=str(output_document_path),
        warnings=[],
    ).to_dict()


def _summarize_with_retries(
    source,
    source_hash: str,
    summarizer: CharacterSummarizer,
    max_retries: int,
) -> dict[str, Any]:
    last_error: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            raw = summarizer.summarize_character(
                source.character_id,
                source.name,
                source.background_story,
                source.personal_profile,
            )
            return prepare_validated_summary(
                raw,
                source.character_id,
                source.name,
                source.aliases,
                source.player_controllable,
                source_hash,
            )
        except (ValidationError, ValueError, TypeError) as exc:
            last_error = exc
            LOGGER.warning(
                "角色 %s 校验失败，第 %s 次：%s",
                source.character_id,
                attempt + 1,
                exc,
            )
    raise RuntimeError(f"多次总结或校验失败：{last_error}")


def _summary_json_path(output_json_dir: Path, character_id: str) -> Path:
    return output_json_dir / f"{character_id}.json"


def _has_current_summary(output_json_dir: Path, character_id: str) -> bool:
    path = _summary_json_path(output_json_dir, character_id)
    if not path.exists():
        return False
    try:
        data = read_json(path)
    except Exception:
        return False
    return data.get("metadata", {}).get("schema_version") == SCHEMA_VERSION


def _load_active_summaries(
    output_json_dir: Path,
    index: dict[str, CharacterIndexItem],
) -> list[dict[str, Any]]:
    summaries = []
    for item in index.values():
        if item.status != "active" or item.summarized != 1:
            continue
        path = _summary_json_path(output_json_dir, item.character_id)
        if not path.exists():
            continue
        data = read_json(path)
        if data.get("metadata", {}).get("schema_version") == SCHEMA_VERSION:
            summaries.append(data)
    return summaries


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
