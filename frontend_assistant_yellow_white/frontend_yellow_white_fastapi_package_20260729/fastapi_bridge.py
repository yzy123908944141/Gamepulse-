from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DB = PROJECT_ROOT / "raw_data.db"
AGENT_DB = PROJECT_ROOT / "agent.db"

app = FastAPI(title="GamerPulse Frontend SQLite Bridge", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _connect(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    return connection


def _json_loads(value: Any, fallback: Any) -> Any:
    if value is None or value == "":
        return fallback
    if isinstance(value, (list, dict)):
        return value
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return fallback


def _parse_comment_ids(value: Any) -> list[int]:
    if value is None:
        return []
    if isinstance(value, list):
        raw_items = value
    else:
        text = str(value).strip()
        if not text:
            return []
        try:
            parsed = json.loads(text)
            raw_items = parsed if isinstance(parsed, list) else str(parsed).split(",")
        except json.JSONDecodeError:
            raw_items = text.split(",")
    ids: list[int] = []
    for item in raw_items:
        try:
            ids.append(int(str(item).strip()))
        except (TypeError, ValueError):
            continue
    return ids


def _fetch_character(character_id: int) -> dict[str, Any] | None:
    if not RAW_DB.exists():
        return None
    with _connect(RAW_DB) as connection:
        row = connection.execute(
            """
            SELECT id, name, version, background_lore, personality_setting, combat_style
            FROM characters
            WHERE id = ?
            """,
            (character_id,),
        ).fetchone()
    if not row:
        return None
    story_parts = [
        ("背景故事", row["background_lore"]),
        ("性格设定", row["personality_setting"]),
        ("战斗风格", row["combat_style"]),
    ]
    story = "\n\n".join(f"【{label}】{text}" for label, text in story_parts if text)
    return {
        "id": row["id"],
        "name": row["name"],
        "version": row["version"],
        "personal_story": story,
    }


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "raw_data_db": RAW_DB.exists(),
        "agent_db": AGENT_DB.exists(),
    }


@app.get("/api/characters")
def characters() -> dict[str, Any]:
    if not RAW_DB.exists():
        return {"characters": []}
    with _connect(RAW_DB) as connection:
        rows = connection.execute(
            "SELECT id, name, version, background_lore, personality_setting, combat_style FROM characters ORDER BY id"
        ).fetchall()
    return {
        "characters": [
            {
                "id": row["id"],
                "name": row["name"],
                "version": row["version"],
                "personal_story": "\n\n".join(
                    part
                    for part in [row["background_lore"], row["personality_setting"], row["combat_style"]]
                    if part
                ),
            }
            for row in rows
        ]
    }


@app.get("/api/diagnosis")
def diagnosis(character_id: int = Query(..., ge=1)) -> dict[str, Any]:
    character = _fetch_character(character_id)
    if not AGENT_DB.exists():
        return {"error": "agent.db not found", "character_id": character_id, "analysis_id": None}

    with _connect(AGENT_DB) as connection:
        row = connection.execute(
            """
            SELECT id, character_id, analysis_date, character_score, gameplay_score, system_pain_score,
                   risk_warnings, word_cloud_data, associated_comment_ids
            FROM analysis_results
            WHERE character_id = ?
            ORDER BY datetime(analysis_date) DESC, id DESC
            LIMIT 1
            """,
            (character_id,),
        ).fetchone()

    if not row:
        return {
            "analysis_id": None,
            "character_id": character_id,
            "scores": {"character": 0, "gameplay": 0, "systempain": 0},
            "risk_warnings": [],
            "word_cloud_data": [],
            "associated_comment_ids": [],
            "personal_story": character.get("personal_story") if character else "",
        }

    return {
        "analysis_id": row["id"],
        "character_id": row["character_id"],
        "analysis_date": row["analysis_date"],
        "character_name": character.get("name") if character else None,
        "version": character.get("version") if character else None,
        "scores": {
            "character": row["character_score"],
            "gameplay": row["gameplay_score"],
            "systempain": row["system_pain_score"],
        },
        "risk_warnings": _json_loads(row["risk_warnings"], []),
        "word_cloud_data": _json_loads(row["word_cloud_data"], []),
        "associated_comment_ids": _parse_comment_ids(row["associated_comment_ids"]),
        "personal_story": character.get("personal_story") if character else "",
    }


@app.get("/api/comments/trace")
def comments_trace(ids: str = Query(...)) -> dict[str, Any]:
    comment_ids = _parse_comment_ids(ids)
    if not comment_ids or not RAW_DB.exists():
        return {"comments": []}

    placeholders = ",".join("?" for _ in comment_ids)
    with _connect(RAW_DB) as connection:
        rows = connection.execute(
            f"SELECT id, source, content, publish_date, url FROM raw_comments WHERE id IN ({placeholders})",
            comment_ids,
        ).fetchall()

    order = {comment_id: index for index, comment_id in enumerate(comment_ids)}
    comments = sorted(rows, key=lambda row: order.get(row["id"], len(order)))
    return {
        "comments": [
            {
                "id": row["id"],
                "platform": row["source"],
                "source": row["source"],
                "content": row["content"],
                "publish_date": row["publish_date"],
                "url": row["url"],
            }
            for row in comments
        ]
    }
