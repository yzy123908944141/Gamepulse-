from __future__ import annotations

from pathlib import Path

from worldview_tool.loader import DEFAULT_WORLD_PATH, WorldLoreLoader
from worldview_tool.retriever import WorldLoreRetriever
from worldview_tool.schemas import (
    INPUT_SCHEMA,
    OUTPUT_SCHEMA,
    SUPPORTED_SECTIONS,
    WorldLoreResult,
)


_loader = WorldLoreLoader(DEFAULT_WORLD_PATH)
_retriever_cache: dict[Path, tuple[str, WorldLoreRetriever]] = {}


WORLD_LORE_TOOL_SPEC = {
    "name": "get_world_lore",
    "description": (
        "查询《鸣潮》的基础世界观、灾害体系、共鸣者、文明级存在、地区组织和漂泊者相关设定。"
        "只用于世界观事实查询，不负责评价剧情或分析角色。"
        "不得根据 world.txt 之外的信息补充设定；找不到答案时必须返回未找到。"
        "索诺拉中的内容不一定等同于客观事实；岁主不能简单等同于全知神明；"
        "鸣式与普通残象不是同一层级；漂泊者真实身份属于主线谜团，不能擅自下定论。"
        "回答中应尽可能保留原文术语，并注明内容来自 data/world.txt。"
    ),
    "input_schema": INPUT_SCHEMA,
    "output_schema": OUTPUT_SCHEMA,
    "supported_sections": SUPPORTED_SECTIONS,
}


def get_world_lore(
    query: str,
    section: str | None = None,
    max_chars: int = 3000,
    *,
    world_path: str | Path | None = None,
) -> dict:
    normalized_query = (query or "").strip()
    if not normalized_query:
        return WorldLoreResult(
            success=False,
            query=query,
            matched_sections=[],
            content="",
            warnings=["query 不能为空"],
        ).to_dict()

    if max_chars < 1:
        return WorldLoreResult(
            success=False,
            query=normalized_query,
            matched_sections=[],
            content="",
            warnings=["max_chars 必须大于 0"],
        ).to_dict()

    loader = _loader if world_path is None else WorldLoreLoader(world_path)
    load_result = loader.load()
    if load_result.warnings:
        return WorldLoreResult(
            success=False,
            query=normalized_query,
            matched_sections=[],
            content="",
            warnings=load_result.warnings,
        ).to_dict()

    retriever = _get_retriever(load_result.source, load_result.content, world_path is None)
    retrieval = retriever.search(normalized_query, section=section, max_chars=max_chars)
    if retrieval.warnings:
        return WorldLoreResult(
            success=False,
            query=normalized_query,
            matched_sections=[],
            content="",
            warnings=retrieval.warnings,
        ).to_dict()

    content = "\n\n".join(chunk.text for chunk in retrieval.chunks)
    truncated = len(content) > max_chars
    if truncated:
        content = content[:max_chars]

    return WorldLoreResult(
        success=bool(content),
        query=normalized_query,
        matched_sections=[chunk.label for chunk in retrieval.chunks],
        content=content,
        truncated=truncated,
        warnings=[] if content else ["未找到相关世界观内容"],
    ).to_dict()


def _get_retriever(path: Path, content: str, use_cache: bool) -> WorldLoreRetriever:
    if not use_cache:
        return WorldLoreRetriever(content)

    cached = _retriever_cache.get(path)
    if cached and cached[0] == content:
        return cached[1]

    retriever = WorldLoreRetriever(content)
    _retriever_cache[path] = (content, retriever)
    return retriever
