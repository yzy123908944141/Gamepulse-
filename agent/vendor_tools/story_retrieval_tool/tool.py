from __future__ import annotations

import logging
from typing import Any

from story_retrieval_tool.index import build_or_load_index
from story_retrieval_tool.rag_adapter import ChromaRagStoryRetriever
from story_retrieval_tool.retriever import KeywordStoryRetriever
from story_retrieval_tool.schemas import (
    STORY_CONTEXT_INPUT_SCHEMA,
    STORY_CONTEXT_OUTPUT_SCHEMA,
    StoryContextResult,
)
from story_retrieval_tool.summarizer import MockStorySummarizer, StorySummarizer
from story_retrieval_tool.validator import (
    ValidationError,
    ensure_source_refs,
    validate_story_context,
)


LOGGER = logging.getLogger(__name__)


STORY_CONTEXT_TOOL_SPEC = {
    "name": "query_story_context",
    "description": (
        "从剧情资料库中检索相关章节、任务或场景片段，再调用模型生成结构化剧情概括。"
        "只用于剧情事实检索与概括，不负责角色评分、剧情评分或舆情分析。"
        "不会把整个剧情库发送给模型，source_refs 由程序根据实际检索结果生成或校验。"
    ),
    "input_schema": STORY_CONTEXT_INPUT_SCHEMA,
    "output_schema": STORY_CONTEXT_OUTPUT_SCHEMA,
}


def query_story_context(
    query: str,
    story_library_path: str = "./story_library",
    top_k: int = 8,
    force_reindex: bool = False,
    retriever: str = "keyword",
    rag_script_path: str | None = None,
    chroma_dir: str | None = None,
    embedding_model_path: str | None = None,
    character_id: int | None = None,
    chapter: str | None = None,
    *,
    summarizer: StorySummarizer | None = None,
    max_retries: int = 2,
) -> dict[str, Any]:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
    normalized_query = (query or "").strip()
    if not normalized_query:
        return _failure(query, ["query 不能为空。"])
    if top_k < 1:
        return _failure(normalized_query, ["top_k 必须大于 0。"])

    warnings: list[str] = []
    try:
        if retriever == "keyword":
            chunks, warnings = build_or_load_index(story_library_path, force_reindex)
            story_retriever = KeywordStoryRetriever(chunks)
        elif retriever == "chroma-rag":
            if not rag_script_path:
                return _failure(normalized_query, ["使用 chroma-rag 时必须提供 rag_script_path。"])
            story_retriever = ChromaRagStoryRetriever(
                rag_script_path=rag_script_path,
                chroma_dir=chroma_dir,
                embedding_model_path=embedding_model_path,
                character_id=character_id,
                chapter=chapter,
            )
        else:
            return _failure(normalized_query, [f"不支持的 retriever：{retriever}"])
        retrieved = story_retriever.retrieve(normalized_query, top_k)
    except Exception as exc:
        return _failure(normalized_query, [str(exc)])

    if not retrieved:
        return StoryContextResult(
            success=False,
            query=normalized_query,
            characters=[],
            story={"summary": "", "key_events": [], "main_conflict": "", "result": ""},
            background_setting={
                "locations": [],
                "factions": [],
                "world_rules": [],
                "historical_context": [],
            },
            source_refs=[],
            information_gaps=["未检索到相关剧情片段。"],
            confidence="low",
            warnings=warnings,
        ).to_dict()

    retrieved_payload = [
        {
            **item.chunk.to_dict(),
            "relevance": item.relevance,
        }
        for item in retrieved
    ]
    summarizer = summarizer or MockStorySummarizer()

    try:
        result = _summarize_with_retries(
            normalized_query,
            retrieved_payload,
            summarizer,
            max_retries,
        )
    except Exception as exc:
        return StoryContextResult(
            success=False,
            query=normalized_query,
            characters=[],
            story={"summary": "", "key_events": [], "main_conflict": "", "result": ""},
            background_setting={
                "locations": [],
                "factions": [],
                "world_rules": [],
                "historical_context": [],
            },
            source_refs=[
                {
                    "chunk_id": item["chunk_id"],
                    "source": item["source_file"],
                    "relevance": item["relevance"],
                }
                for item in retrieved_payload
            ],
            information_gaps=[f"模型总结失败：{exc}"],
            confidence="low",
            warnings=warnings,
        ).to_dict()

    result["success"] = True
    result["warnings"] = warnings
    return result


def _summarize_with_retries(
    query: str,
    retrieved_chunks: list[dict[str, Any]],
    summarizer: StorySummarizer,
    max_retries: int,
) -> dict[str, Any]:
    last_error: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            result = summarizer.summarize_story_context(query, retrieved_chunks)
            result["query"] = query
            result = ensure_source_refs(result, retrieved_chunks)
            validate_story_context(result)
            return result
        except (ValidationError, ValueError, TypeError, KeyError) as exc:
            last_error = exc
            LOGGER.warning("剧情总结校验失败，第 %s 次：%s", attempt + 1, exc)
    raise RuntimeError(f"多次总结或校验失败：{last_error}")


def _failure(query: str, warnings: list[str]) -> dict[str, Any]:
    return StoryContextResult(
        success=False,
        query=query,
        characters=[],
        story={"summary": "", "key_events": [], "main_conflict": "", "result": ""},
        background_setting={
            "locations": [],
            "factions": [],
            "world_rules": [],
            "historical_context": [],
        },
        source_refs=[],
        information_gaps=[],
        confidence="low",
        warnings=warnings,
    ).to_dict()
