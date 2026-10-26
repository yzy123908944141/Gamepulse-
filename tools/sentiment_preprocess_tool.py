"""Sentiment preprocessing integration tool for GamePulse.

This wraps the copied data/crawler and data/analysis components so they use
GamePulse-local databases and can be called from Agent/backend code.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover
    load_dotenv = None

try:
    from langchain_core.tools import tool
except Exception:  # pragma: no cover
    def tool(func=None, **_kwargs):
        if func is None:
            return lambda f: f
        return func

GAMEPULSE_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = GAMEPULSE_ROOT / "data"
ANALYSIS_DIR = DATA_DIR / "analysis"
CRAWLER_DIR = DATA_DIR / "crawler"
RAW_DB_PATH = DATA_DIR / "raw_data.db"
AGENT_DB_PATH = DATA_DIR / "agent.db"


def _prepare_imports() -> None:
    if load_dotenv is not None:
        load_dotenv(GAMEPULSE_ROOT / ".env", override=False)
    os.environ.setdefault("GAMEPULSE_ROOT", str(GAMEPULSE_ROOT))
    os.environ.setdefault("GAMERPULSE_RAW_DATA_DB", str(RAW_DB_PATH))
    os.environ.setdefault("GAMERPULSE_RAW_DB_PATH", str(RAW_DB_PATH))
    os.environ.setdefault("GAMERPULSE_AGENT_DB_PATH", str(AGENT_DB_PATH))
    for path in (DATA_DIR, ANALYSIS_DIR, CRAWLER_DIR):
        value = str(path)
        if value not in sys.path:
            sys.path.insert(0, value)


def _json(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


def init_sentiment_preprocess() -> dict[str, Any]:
    """Initialize analysis tables used by the sentiment preprocessing pipeline."""
    _prepare_imports()
    from db import init_agent_db

    init_agent_db()
    return {
        "success": True,
        "raw_db_path": str(RAW_DB_PATH),
        "agent_db_path": str(AGENT_DB_PATH),
        "message": "sentiment preprocess database initialized",
    }


def run_csv_preprocess() -> dict[str, Any]:
    """Run crawler CSV cleaning/noise filtering and import into raw_comments."""
    _prepare_imports()
    from crawler.pipelines import run_pipeline

    stats = run_pipeline()
    return {
        "success": True,
        "stage": "csv_preprocess",
        "raw_db_path": str(RAW_DB_PATH),
        "stats": stats,
    }


def process_comments_with_ai(limit: int | None = 20, clear_existing: bool = False, sleep_seconds: float = 0.1) -> dict[str, Any]:
    """Analyze raw comments with the copied sentiment_agent and write analysis_comments/analysis_characters."""
    _prepare_imports()
    from db import init_agent_db, DBTools
    from sentiment_agent import analyze_single_comment

    init_agent_db()
    if clear_existing:
        DBTools.clear_agent_db()
        init_agent_db()

    characters = DBTools.get_characters()
    name_to_id = {name: data["id"] for name, data in characters.items()}
    known_character_names = DBTools.get_character_names()
    comments = DBTools.get_all_comments(limit=limit)

    processed_ids: list[int] = []
    failed_items: list[dict[str, Any]] = []

    for index, comment in enumerate(comments, 1):
        try:
            result = analyze_single_comment(comment["content"], known_characters=known_character_names)
            analysis_comment_id = DBTools.insert_analysis_comment(
                raw_comment_id=comment["id"],
                has_character=result.has_character,
                sentiment=result.sentiment,
                tag=result.tag,
                reason=result.reason,
                is_toxic=result.is_toxic,
                decision_source=result.decision_source,
            )
            if result.has_character:
                for mentioned in result.mentioned_characters:
                    char_id = name_to_id.get(mentioned.character_name)
                    if char_id:
                        DBTools.insert_character_link(
                            analysis_comment_id=analysis_comment_id,
                            character_id=char_id,
                            character_name=mentioned.character_name,
                        )
            DBTools.update_raw_comment_analysis_status(comment["id"], 1)
            processed_ids.append(comment["id"])
        except Exception as exc:  # keep batch processing resilient
            failed_items.append({"raw_comment_id": comment.get("id"), "error": str(exc)})
        if sleep_seconds and index < len(comments):
            time.sleep(max(float(sleep_seconds), 0.0))

    return {
        "success": not failed_items,
        "stage": "comment_ai_analysis",
        "total_comments": len(comments),
        "processed_comments": len(processed_ids),
        "failed_comments": len(failed_items),
        "processed_ids": processed_ids,
        "failed_items": failed_items,
        "raw_db_path": str(RAW_DB_PATH),
        "agent_db_path": str(AGENT_DB_PATH),
    }


def aggregate_character_opinion(character_id: int | None = None) -> dict[str, Any]:
    """Aggregate analyzed comments into analysis_results for one or all mentioned characters."""
    _prepare_imports()
    from db import init_agent_db, get_agent_db_conn, DBTools
    from aggregate_opinion import get_comments_for_character, save_analysis_result
    from diagnosis import generate_diagnosis

    init_agent_db()
    if character_id is None:
        conn = get_agent_db_conn()
        rows = conn.execute("SELECT DISTINCT character_id FROM analysis_characters ORDER BY character_id").fetchall()
        conn.close()
        character_ids = [row[0] for row in rows]
    else:
        character_ids = [int(character_id)]

    processed: list[int] = []
    failed_items: list[dict[str, Any]] = []
    skipped: list[int] = []

    for char_id in character_ids:
        try:
            char_info = DBTools.get_character_by_id(char_id)
            comments = get_comments_for_character(char_id)
            if not char_info or not comments:
                skipped.append(char_id)
                continue
            result = generate_diagnosis(character_name=char_info["name"], comments=comments)
            save_analysis_result(char_id, result)
            processed.append(char_id)
        except Exception as exc:
            failed_items.append({"character_id": char_id, "error": str(exc)})

    return {
        "success": not failed_items,
        "stage": "character_opinion_aggregation",
        "total_characters": len(character_ids),
        "processed_character_ids": processed,
        "skipped_character_ids": skipped,
        "failed_items": failed_items,
        "agent_db_path": str(AGENT_DB_PATH),
    }


@tool
def run_sentiment_preprocess(
    run_csv_import: bool = False,
    run_comment_analysis: bool = False,
    run_aggregation: bool = False,
    limit: int = 20,
    clear_existing: bool = False,
    character_id: int | None = None,
) -> str:
    """运行 GamePulse 舆情预处理：CSV 清洗入库、评论 AI 分析、角色舆情聚合。"""
    results: list[dict[str, Any]] = [init_sentiment_preprocess()]
    if run_csv_import:
        results.append(run_csv_preprocess())
    if run_comment_analysis:
        results.append(process_comments_with_ai(limit=limit, clear_existing=clear_existing))
    if run_aggregation:
        results.append(aggregate_character_opinion(character_id=character_id))
    return _json({"success": all(item.get("success", False) for item in results), "results": results})
