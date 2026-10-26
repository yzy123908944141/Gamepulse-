from __future__ import annotations

import argparse
import json
import sys

from story_retrieval_tool.summarizer import build_summarizer
from story_retrieval_tool.tool import query_story_context


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(prog="python -m story_retrieval_tool")
    subparsers = parser.add_subparsers(dest="command", required=True)

    query_parser = subparsers.add_parser("query", help="检索并概括剧情资料")
    query_parser.add_argument("--library", default="./story_library", help="剧情资料目录")
    query_parser.add_argument("--query", required=True, help="剧情查询")
    query_parser.add_argument("--top-k", type=int, default=8, help="检索片段数量")
    query_parser.add_argument("--force-reindex", action="store_true", help="强制重建索引")
    query_parser.add_argument(
        "--retriever",
        choices=["keyword", "chroma-rag"],
        default="keyword",
        help="检索后端",
    )
    query_parser.add_argument("--rag-script", default=None, help="rag_query.py 路径")
    query_parser.add_argument("--chroma-dir", default=None, help="Chroma DB 目录")
    query_parser.add_argument("--embedding-model", default=None, help="本地 embedding 模型目录")
    query_parser.add_argument("--character-id", type=int, default=None, help="RAG 角色 ID 过滤")
    query_parser.add_argument("--chapter", default=None, help="RAG 章节/版本过滤")
    query_parser.add_argument(
        "--summarizer",
        choices=["mock", "openai-compatible"],
        default="mock",
        help="模型总结器类型",
    )

    args = parser.parse_args()
    if args.command == "query":
        result = query_story_context(
            query=args.query,
            story_library_path=args.library,
            top_k=args.top_k,
            force_reindex=args.force_reindex,
            retriever=args.retriever,
            rag_script_path=args.rag_script,
            chroma_dir=args.chroma_dir,
            embedding_model_path=args.embedding_model,
            character_id=args.character_id,
            chapter=args.chapter,
            summarizer=build_summarizer(args.summarizer),
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
