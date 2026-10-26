"""Database connections for GamePulse sentiment preprocessing."""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from .schema import (
    SQL_CREATE_ANALYSIS_COMMENTS,
    SQL_CREATE_ANALYSIS_CHARACTERS,
    SQL_CREATE_ANALYSIS_RESULTS,
)

GAMEPULSE_ROOT = Path(os.getenv("GAMEPULSE_ROOT", Path(__file__).resolve().parents[3]))
DATA_DIR = GAMEPULSE_ROOT / "data"
RAW_DB_PATH = Path(
    os.getenv(
        "GAMERPULSE_RAW_DATA_DB",
        os.getenv("GAMERPULSE_RAW_DB_PATH", str(DATA_DIR / "raw_data.db")),
    )
)
AGENT_DB_PATH = Path(
    os.getenv(
        "GAMERPULSE_AGENT_DB_PATH",
        os.getenv("GAMERPULSE_AGENT_DB", str(DATA_DIR / "agent.db")),
    )
)


def get_raw_db_conn():
    conn = sqlite3.connect(str(RAW_DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def get_agent_db_conn():
    conn = sqlite3.connect(str(AGENT_DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    try:
        return {row[1] for row in conn.execute(f'PRAGMA table_info("{table}")').fetchall()}
    except sqlite3.Error:
        return set()


def _ensure_optional_columns(conn: sqlite3.Connection) -> None:
    comments_cols = _columns(conn, "analysis_comments")
    if comments_cols and "reason" not in comments_cols:
        conn.execute("ALTER TABLE analysis_comments ADD COLUMN reason TEXT")
    if comments_cols and "decision_source" not in comments_cols:
        conn.execute("ALTER TABLE analysis_comments ADD COLUMN decision_source TEXT DEFAULT 'flash'")

    chars_cols = _columns(conn, "analysis_characters")
    if chars_cols and "confidence" not in chars_cols:
        conn.execute("ALTER TABLE analysis_characters ADD COLUMN confidence REAL")

    results_cols = _columns(conn, "analysis_results")
    if results_cols and "associated_comment_ids" not in results_cols and "source_comment_ids" not in results_cols:
        conn.execute("ALTER TABLE analysis_results ADD COLUMN associated_comment_ids TEXT")
    conn.commit()


def init_agent_db():
    """Initialize analysis tables in GamePulse local agent.db."""
    conn = get_agent_db_conn()
    cursor = conn.cursor()
    cursor.execute(SQL_CREATE_ANALYSIS_COMMENTS)
    cursor.execute(SQL_CREATE_ANALYSIS_CHARACTERS)
    cursor.execute(SQL_CREATE_ANALYSIS_RESULTS)
    conn.commit()
    _ensure_optional_columns(conn)
    conn.close()
