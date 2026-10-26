# -*- coding: utf-8 -*-
"""
GamerPulse 会话记忆封装。

优先复用项目中的 backend.database.engine；如果当前环境还没有完整后端，
则回退到本地 SQLite，方便先把 Agent 工作台骨架跑起来。
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import List

from dotenv import find_dotenv, load_dotenv
from langchain_classic.memory import ConversationBufferMemory
from langchain_core.chat_history import BaseChatMessageHistory
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_openai import ChatOpenAI
from sqlalchemy import create_engine, text

load_dotenv(find_dotenv())

SUMMARY_TOKEN_LIMIT = int(os.getenv("SUMMARY_TOKEN_LIMIT", "2000"))


def _build_fallback_engine():
    db_url = os.getenv(
        "GAMERPULSE_MEMORY_DB_URL",
        f"sqlite:///{Path(__file__).resolve().parents[1] / 'gamerpulse_memory.db'}",
    )
    engine = create_engine(db_url, future=True)
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS sandbox_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    character_id INTEGER NOT NULL DEFAULT 0,
                    title TEXT,
                    current_text TEXT NOT NULL DEFAULT '',
                    selected_constraints TEXT,
                    custom_constraint TEXT,
                    created_at TEXT,
                    updated_at TEXT
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS sandbox_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id INTEGER NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    analysis_payload TEXT,
                    created_at TEXT
                )
                """
            )
        )
    return engine


try:
    from backend.database import engine as backend_engine  # type: ignore

    engine = backend_engine
except Exception:
    engine = _build_fallback_engine()


def _get_summary_llm() -> ChatOpenAI:
    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("DEEPSEEK_API_KEY")
    base_url = os.getenv("OPENAI_BASE_URL")
    model = os.getenv("SUMMARY_MODEL") or os.getenv("OPENAI_MODEL") or os.getenv(
        "DEEPSEEK_MODEL",
        "deepseek-chat",
    )

    if os.getenv("DEEPSEEK_API_KEY") and not base_url:
        base_url = "https://api.deepseek.com"

    return ChatOpenAI(
        model=model,
        api_key=api_key,
        base_url=base_url,
        temperature=0,
    )


class SandboxChatMessageHistory(BaseChatMessageHistory):
    def __init__(self, session_id: int):
        self.session_id = session_id

    @property
    def messages(self) -> List[BaseMessage]:
        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT role, content
                    FROM sandbox_messages
                    WHERE session_id = :sid
                    ORDER BY id ASC
                    """
                ),
                {"sid": self.session_id},
            ).fetchall()

        history: List[BaseMessage] = []
        for role, content in rows:
            if role == "user":
                history.append(HumanMessage(content=content))
            else:
                history.append(AIMessage(content=content))
        return history

    def add_message(self, message: BaseMessage) -> None:
        role = "user" if isinstance(message, HumanMessage) else "assistant"
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO sandbox_messages (session_id, role, content, created_at)
                    VALUES (:sid, :role, :content, datetime('now'))
                    """
                ),
                {
                    "sid": self.session_id,
                    "role": role,
                    "content": message.content,
                },
            )

    def clear(self) -> None:
        with engine.begin() as conn:
            conn.execute(
                text("DELETE FROM sandbox_messages WHERE session_id = :sid"),
                {"sid": self.session_id},
            )


def create_session(
    character_id: int = 0,
    title: str = "未命名会话",
    current_text: str = "",
    selected_constraints: list | None = None,
    custom_constraint: str | None = None,
) -> int:
    import json

    with engine.begin() as conn:
        result = conn.execute(
            text(
                """
                INSERT INTO sandbox_sessions
                (character_id, title, current_text, selected_constraints,
                 custom_constraint, created_at, updated_at)
                VALUES (:cid, :title, :ctext, :constraints, :custom,
                        datetime('now'), datetime('now'))
                """
            ),
            {
                "cid": character_id,
                "title": title,
                "ctext": current_text,
                "constraints": json.dumps(
                    selected_constraints or [],
                    ensure_ascii=False,
                ),
                "custom": custom_constraint,
            },
        )
        return int(result.lastrowid)


def get_memory(session_id: int) -> ConversationBufferMemory:
    return ConversationBufferMemory(
        chat_memory=SandboxChatMessageHistory(session_id),
        memory_key="chat_history",
        return_messages=True,
    )


def build_history_text(memory: ConversationBufferMemory) -> str:
    data = memory.load_memory_variables({})
    messages = data.get("chat_history", [])
    lines = []
    for message in messages:
        role = "策划" if isinstance(message, HumanMessage) else "助手"
        lines.append(f"{role}：{message.content}")
    return "\n".join(lines)


def append_turn(session_id: int, user_input: str, answer: str) -> None:
    memory = get_memory(session_id)
    memory.save_context({"input": user_input}, {"output": answer})


