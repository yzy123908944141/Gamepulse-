from __future__ import annotations

import argparse
import json
from pathlib import Path

from character_tool.summarizer import build_summarizer
from character_tool.tool import scan_character_library


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m character_tool")
    subparsers = parser.add_subparsers(dest="command", required=True)

    scan_parser = subparsers.add_parser("scan", help="扫描角色库并生成结构化档案")
    scan_parser.add_argument("--library", default="./characters", help="角色库目录或 SQLite 数据库")
    scan_parser.add_argument("--output", default="./outputs", help="输出根目录")
    scan_parser.add_argument(
        "--summarizer",
        choices=["mock", "openai-compatible"],
        default="mock",
        help="总结器类型。openai-compatible 会调用 AI，需要 OPENAI_API_KEY。",
    )
    scan_parser.add_argument(
        "--force-rescan",
        action="store_true",
        help="重新总结全部角色",
    )
    scan_parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="仅处理前 N 个角色，用于小样本测试",
    )

    args = parser.parse_args()
    if args.command == "scan":
        output_root = Path(args.output)
        result = scan_character_library(
            character_library_path=args.library,
            output_json_path=str(output_root / "character_json"),
            output_document_path=str(output_root / "角色档案汇总.md"),
            force_rescan=args.force_rescan,
            limit=args.limit,
            summarizer=build_summarizer(args.summarizer),
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
