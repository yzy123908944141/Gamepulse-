from __future__ import annotations

import json
from pathlib import Path
from queue import Queue
from threading import Thread
import logging
import os
import sqlite3
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent / ".env")
except Exception:
    pass

from agent.orchestrator import invoke_orchestrator
from agent.langchain_memory import create_session
from tools import sentiment_report_tool as sentiment_tool
from tools.sentiment_preprocess_tool import run_sentiment_preprocess

logger = logging.getLogger(__name__)

app = FastAPI(title="GamerPulse Agent Workbench")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

FRONTEND_DIR = Path(__file__).resolve().parent / "frontend_assistant_yellow_white" / "frontend_yellow_white_fastapi_package_20260729"

@app.get("/")
def root():
    return {
        "name": "GamerPulse Agent Workbench",
        "status": "running",
        "docs": "/docs",
        "health": "/health",
        "endpoints": {
            "create_session": "POST /sessions",
            "chat": "POST /chat",
            "chat_stream": "POST /chat/stream",
            "frontend": "GET /frontend/",
        },
    }


class CreateSessionRequest(BaseModel):
    character_id: int = 0
    title: str = "未命名会话"
    current_text: str = ""
    selected_constraints: list[str] = Field(default_factory=list)
    custom_constraint: str | None = None


class ChatRequest(BaseModel):
    session_id: int
    message: str
    shared_context: dict[str, Any] = Field(default_factory=dict)


class SentimentPreprocessRequest(BaseModel):
    run_csv_import: bool = False
    run_comment_analysis: bool = False
    run_aggregation: bool = False
    limit: int = 20
    clear_existing: bool = False
    character_id: int | None = None

RAW_DATA_DB = Path(os.getenv("GAMERPULSE_RAW_DATA_DB", Path(__file__).resolve().parent / "data" / "raw_data.db"))
AGENT_DATA_DB = Path(os.getenv("GAMERPULSE_AGENT_DB_PATH", Path(__file__).resolve().parent / "data" / "agent.db"))


def _connect_sqlite(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    return connection


def _json_loads(value: Any, fallback: Any) -> Any:
    if value is None or value == "":
        return fallback
    if isinstance(value, (list, dict)):
        return value
    try:
        return json.loads(str(value))
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
    if not RAW_DATA_DB.exists():
        return None
    with _connect_sqlite(RAW_DATA_DB) as connection:
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
    story = "\n\n".join(
        part
        for part in [row["background_lore"], row["personality_setting"], row["combat_style"]]
        if part
    )
    return {
        "id": row["id"],
        "name": row["name"],
        "version": row["version"],
        "personal_story": story,
    }

def _sqlite_table_summary(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"exists": False, "path": str(path), "size_bytes": 0, "tables": []}
    tables: list[dict[str, Any]] = []
    with _connect_sqlite(path) as connection:
        table_rows = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
        for table_row in table_rows:
            table_name = table_row["name"]
            count = connection.execute(f'SELECT COUNT(*) AS count FROM "{table_name}"').fetchone()["count"]
            columns = [row["name"] for row in connection.execute(f'PRAGMA table_info("{table_name}")').fetchall()]
            tables.append({"name": table_name, "rows": count, "columns": columns[:8]})
    return {"exists": True, "path": str(path), "size_bytes": path.stat().st_size, "tables": tables}


@app.get("/health")
def health_check():
    return {"status": "ok"}




@app.get("/api/db/summary")
def api_db_summary():
    raw = _sqlite_table_summary(RAW_DATA_DB)
    agent = _sqlite_table_summary(AGENT_DATA_DB)
    return {
        "databases": [
            {
                "key": "raw_data",
                "label": "raw_data.db",
                "purpose": "角色基础资料、原始评论、评论 URL",
                **raw,
            },
            {
                "key": "agent",
                "label": "agent.db",
                "purpose": "角色评分、风险警告、关键词、关联评论 ID",
                **agent,
            },
        ]
    }

@app.get("/api/characters")
def api_characters():
    if not RAW_DATA_DB.exists():
        return {"characters": [], "error": f"raw_data.db not found: {RAW_DATA_DB}"}
    with _connect_sqlite(RAW_DATA_DB) as connection:
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
def api_diagnosis(character_id: int):
    character = _fetch_character(character_id)
    if not AGENT_DATA_DB.exists():
        return {"error": f"agent.db not found: {AGENT_DATA_DB}", "character_id": character_id, "analysis_id": None}

    with _connect_sqlite(AGENT_DATA_DB) as connection:
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
def api_comments_trace(ids: str):
    comment_ids = _parse_comment_ids(ids)
    if not comment_ids:
        return {"comments": []}
    if not RAW_DATA_DB.exists():
        return {"comments": [], "error": f"raw_data.db not found: {RAW_DATA_DB}"}

    placeholders = ",".join("?" for _ in comment_ids)
    with _connect_sqlite(RAW_DATA_DB) as connection:
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


@app.get("/api/report/export")
def api_report_export(character_id: int | None = None, days: int = 30):
    sentiment_tool.RAW_DB_PATH = str(RAW_DATA_DB)
    sentiment_tool.AGENT_DB_PATH = str(AGENT_DATA_DB)
    report = sentiment_tool.generate_sentiment_report(character_id=character_id, days=days, limit=200)
    markdown = sentiment_tool.format_sentiment_report_markdown(report)
    character = report.get("character", {}) or {}
    character_name = character.get("name") or (f"character_{character_id}" if character_id else "global")
    safe_name = "".join(ch if ch not in r'\\/:*?"<>|' else "_" for ch in str(character_name)).strip() or "global"
    file_name = f"GamePulse_舆情报告_{safe_name}.md"
    return {
        "success": True,
        "file_name": file_name,
        "mime_type": "text/markdown;charset=utf-8",
        "encoding": "utf-8-sig",
        "content": markdown,
        "total_comments": (report.get("summary", {}) or {}).get("total_comments", 0),
    }

@app.post("/api/sentiment/preprocess")
def api_sentiment_preprocess(request: SentimentPreprocessRequest):
    raw = run_sentiment_preprocess.invoke(request.model_dump())
    return json.loads(raw)

@app.post("/sessions")
def new_session(request: CreateSessionRequest):
    session_id = create_session(
        character_id=request.character_id,
        title=request.title,
        current_text=request.current_text,
        selected_constraints=request.selected_constraints,
        custom_constraint=request.custom_constraint,
    )
    return {"session_id": session_id}


@app.post("/chat")
def chat(request: ChatRequest):
    try:
        return invoke_orchestrator(
            session_id=request.session_id,
            user_input=request.message,
            shared_context=request.shared_context,
        )
    except Exception as exc:
        logger.exception("GamePulse chat failed")
        return {
            "session_id": request.session_id,
            "answer": f"GamePulse 总控 Agent 调用失败：{exc.__class__.__name__}。请检查模型 API 网络、Key 和代理配置后重试。",
            "called_agents": [],
            "called_tools": [],
            "shared_context": request.shared_context,
            "active_agent": "orchestrator",
            "success": False,
            "error": str(exc),
        }



def _json_line(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False) + "\n"


@app.post("/chat/stream")
def chat_stream(request: ChatRequest):
    events: Queue[dict[str, Any] | None] = Queue()

    def emit(payload: dict[str, Any]) -> None:
        events.put(payload)

    def run_chat() -> None:
        try:
            result = invoke_orchestrator(
                session_id=request.session_id,
                user_input=request.message,
                shared_context=request.shared_context,
                event_sink=emit,
            )
            events.put({"type": "final", "payload": result})
        except Exception as exc:
            logger.exception("GamePulse streaming chat failed")
            events.put(
                {
                    "type": "final",
                    "payload": {
                        "session_id": request.session_id,
                        "answer": f"GamePulse 总控 Agent 调用失败：{exc.__class__.__name__}。请检查模型 API 网络、Key 和代理配置后重试。",
                        "called_agents": [],
                        "called_tools": [],
                        "shared_context": request.shared_context,
                        "active_agent": "orchestrator",
                        "success": False,
                        "error": str(exc),
                    },
                }
            )
        finally:
            events.put(None)

    def stream():
        yield _json_line({"type": "status", "kind": "system", "name": "request", "detail": "已收到请求，正在启动总控 Agent"})
        worker = Thread(target=run_chat, daemon=True)
        worker.start()
        while True:
            event = events.get()
            if event is None:
                break
            yield _json_line(event)

    return StreamingResponse(stream(), media_type="application/x-ndjson; charset=utf-8")
if FRONTEND_DIR.exists():
    app.mount("/frontend", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")









