"""Database helpers for GamePulse sentiment preprocessing."""
from __future__ import annotations

import sqlite3
from typing import Any

from .connection import get_raw_db_conn, get_agent_db_conn


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    try:
        return {row[1] for row in conn.execute(f'PRAGMA table_info("{table}")').fetchall()}
    except sqlite3.Error:
        return set()


def _pick_existing(cols: set[str], *names: str) -> str | None:
    for name in names:
        if name in cols:
            return name
    return None


class DBTools:
    @staticmethod
    def get_characters():
        conn = get_raw_db_conn()
        cols = _columns(conn, "characters")
        personality_col = _pick_existing(cols, "personality_setting", "personality", "personal_profile")
        select_cols = ["id", "name"]
        if personality_col:
            select_cols.append(personality_col)
        rows = conn.execute(f"SELECT {', '.join(select_cols)} FROM characters").fetchall()
        conn.close()
        characters: dict[str, dict[str, Any]] = {}
        for row in rows:
            characters[row["name"]] = {
                "id": row["id"],
                "name": row["name"],
                "personality_setting": row[personality_col] if personality_col else None,
            }
        return characters

    @staticmethod
    def get_character_by_id(character_id: int):
        conn = get_raw_db_conn()
        cols = _columns(conn, "characters")
        personality_col = _pick_existing(cols, "personality_setting", "personality", "personal_profile")
        select_cols = ["id", "name"]
        if personality_col:
            select_cols.append(personality_col)
        row = conn.execute(
            f"SELECT {', '.join(select_cols)} FROM characters WHERE id = ?",
            (character_id,),
        ).fetchone()
        conn.close()
        if not row:
            return None
        return {
            "id": row["id"],
            "name": row["name"],
            "personality_setting": row[personality_col] if personality_col else None,
        }

    @staticmethod
    def get_character_names():
        conn = get_raw_db_conn()
        rows = conn.execute("SELECT name FROM characters").fetchall()
        conn.close()
        return [row["name"] for row in rows]

    @staticmethod
    def get_all_comments(limit=None):
        raw_conn = get_raw_db_conn()
        raw_cols = _columns(raw_conn, "raw_comments")
        where = "WHERE is_analysis = 0" if "is_analysis" in raw_cols else ""
        query = f"SELECT id, source, content, publish_date FROM raw_comments {where} ORDER BY id"
        params: tuple[Any, ...] = ()
        if limit:
            query += " LIMIT ?"
            params = (limit,)
        rows = raw_conn.execute(query, params).fetchall()
        raw_conn.close()

        if "is_analysis" not in raw_cols:
            agent_conn = get_agent_db_conn()
            try:
                analyzed_ids = {
                    row[0]
                    for row in agent_conn.execute("SELECT raw_comment_id FROM analysis_comments").fetchall()
                }
            except sqlite3.Error:
                analyzed_ids = set()
            finally:
                agent_conn.close()
            rows = [row for row in rows if row["id"] not in analyzed_ids]
            if limit:
                rows = rows[: int(limit)]

        return [
            {
                "id": row["id"],
                "source": row["source"],
                "content": row["content"],
                "publish_date": row["publish_date"],
            }
            for row in rows
        ]

    @staticmethod
    def update_raw_comment_analysis_status(comment_id, status):
        conn = get_raw_db_conn()
        cols = _columns(conn, "raw_comments")
        if "is_analysis" in cols:
            conn.execute("UPDATE raw_comments SET is_analysis = ? WHERE id = ?", (status, comment_id))
            conn.commit()
        conn.close()

    @staticmethod
    def insert_analysis_comment(raw_comment_id, has_character, sentiment, tag, reason, is_toxic, decision_source):
        conn = get_agent_db_conn()
        cols = _columns(conn, "analysis_comments")
        field_values = {
            "raw_comment_id": raw_comment_id,
            "has_character": int(bool(has_character)),
            "sentiment": sentiment,
            "tag": tag,
            "reason": reason,
            "is_toxic": int(is_toxic or 0),
            "decision_source": decision_source,
        }
        fields = [name for name in field_values if name in cols]
        placeholders = ", ".join("?" for _ in fields)
        conn.execute(
            f"INSERT INTO analysis_comments ({', '.join(fields)}) VALUES ({placeholders})",
            tuple(field_values[name] for name in fields),
        )
        new_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.commit()
        conn.close()
        return new_id

    @staticmethod
    def insert_character_link(analysis_comment_id, character_id, character_name, confidence=None):
        conn = get_agent_db_conn()
        cols = _columns(conn, "analysis_characters")
        field_values = {
            "analysis_comment_id": analysis_comment_id,
            "character_id": character_id,
            "character_name": character_name,
            "confidence": confidence,
        }
        fields = [name for name in field_values if name in cols]
        placeholders = ", ".join("?" for _ in fields)
        conn.execute(
            f"INSERT INTO analysis_characters ({', '.join(fields)}) VALUES ({placeholders})",
            tuple(field_values[name] for name in fields),
        )
        conn.commit()
        conn.close()

    @staticmethod
    def insert_analysis_result(character_id, character_score, gameplay_score, system_pain_score, risk_warnings, word_cloud_data, source_comment_ids):
        conn = get_agent_db_conn()
        cols = _columns(conn, "analysis_results")
        ids_field = "associated_comment_ids" if "associated_comment_ids" in cols else "source_comment_ids"
        field_values = {
            "character_id": character_id,
            "character_score": character_score,
            "gameplay_score": gameplay_score,
            "system_pain_score": system_pain_score,
            "risk_warnings": risk_warnings,
            "word_cloud_data": word_cloud_data,
            ids_field: source_comment_ids,
        }
        fields = [name for name in field_values if name in cols]
        placeholders = ", ".join("?" for _ in fields)
        conn.execute(
            f"INSERT INTO analysis_results ({', '.join(fields)}) VALUES ({placeholders})",
            tuple(field_values[name] for name in fields),
        )
        conn.commit()
        conn.close()

    @staticmethod
    def clear_agent_db():
        conn = get_agent_db_conn()
        conn.execute("DROP TABLE IF EXISTS analysis_characters")
        conn.execute("DROP TABLE IF EXISTS analysis_comments")
        conn.execute("DROP TABLE IF EXISTS analysis_results")
        conn.commit()
        conn.close()
