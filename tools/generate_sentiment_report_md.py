"""
Run this file directly to generate the global sentiment report Markdown file.

Output:
    reports/全部舆情报告.md
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

try:
    from .sentiment_report_tool import (
        format_sentiment_report_markdown,
        generate_sentiment_report,
    )
except Exception:  # Allows direct execution: python tools/generate_sentiment_report_md.py
    from sentiment_report_tool import (  # type: ignore
        format_sentiment_report_markdown,
        generate_sentiment_report,
    )


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = PROJECT_ROOT / "reports" / "全部舆情报告.md"


def generate_global_sentiment_report_md() -> Dict[str, Any]:
    """Generate reports/全部舆情报告.md and return basic metadata."""
    report = generate_sentiment_report(days=5000, limit=200)
    markdown = format_sentiment_report_markdown(report)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(markdown, encoding="utf-8-sig")

    summary = report.get("summary", {}) or {}
    return {
        "status": "ok",
        "file_path": str(OUTPUT_PATH),
        "file_name": OUTPUT_PATH.name,
        "format": "md",
        "encoding": "utf-8-sig",
        "character": report.get("character", {}) or {},
        "period": report.get("period", {}) or {},
        "total_comments": summary.get("total_comments", 0),
    }


def main() -> None:
    result = generate_global_sentiment_report_md()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"已生成 Markdown 文件：{result['file_path']}")


if __name__ == "__main__":
    main()

