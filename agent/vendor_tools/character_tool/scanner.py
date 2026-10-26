from __future__ import annotations

import logging
import re
import sqlite3
from pathlib import Path

from character_tool.io_utils import read_json
from character_tool.schemas import CharacterSource


LOGGER = logging.getLogger(__name__)


def scan_sources(character_library_path: str | Path) -> list[CharacterSource]:
    library_path = Path(character_library_path)
    if not library_path.exists():
        raise FileNotFoundError(f"角色库路径不存在：{library_path}")
    if library_path.is_file() and library_path.suffix.lower() in {".db", ".sqlite", ".sqlite3"}:
        return _sources_from_sqlite(library_path)
    if not library_path.is_dir():
        raise NotADirectoryError(f"角色库路径不是目录或 SQLite 数据库：{library_path}")

    sources: list[CharacterSource] = []
    seen_ids: set[str] = set()

    for json_path in sorted(library_path.glob("*.json")):
        source = _source_from_json(json_path)
        if source.character_id in seen_ids:
            LOGGER.warning("跳过重复 character_id：%s", source.character_id)
            continue
        seen_ids.add(source.character_id)
        sources.append(source)

    for child in sorted(path for path in library_path.iterdir() if path.is_dir()):
        source = _source_from_directory(child)
        if source is None:
            continue
        if source.character_id in seen_ids:
            LOGGER.warning("跳过重复 character_id：%s", source.character_id)
            continue
        seen_ids.add(source.character_id)
        sources.append(source)

    return sources


def _sources_from_sqlite(path: Path) -> list[CharacterSource]:
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    try:
        table = _choose_character_table(con)
        columns = _table_columns(con, table)
        id_column = _choose_column(columns, ("character_id", "id"))
        name_column = _choose_column(columns, ("name", "character_name"))
        background_column = _choose_column(
            columns,
            ("background", "background_lore", "background_story"),
        )
        personality_column = _choose_column(
            columns,
            ("personality", "personality_setting", "personal_profile"),
        )
        if not all([id_column, name_column, background_column, personality_column]):
            raise ValueError(
                "SQLite 角色表必须包含 id/name/background/personality 对应字段；"
                f"当前表 {table} 字段为：{', '.join(columns)}"
            )

        rows = con.execute(
            "select * from " + _quote_identifier(table) + " order by " + _quote_identifier(id_column)
        ).fetchall()
    finally:
        con.close()

    sources: list[CharacterSource] = []
    db_updated_at = _mtime_iso(path)
    for row in rows:
        raw_id = str(row[id_column]).strip()
        character_id = raw_id if raw_id.startswith("char_") else _db_character_id(raw_id)
        background_story = str(row[background_column] or "")
        personal_profile = str(row[personality_column] or "")
        sources.append(
            CharacterSource(
                character_id=character_id,
                name=str(row[name_column] or "").strip() or character_id,
                background_story=background_story,
                personal_profile=personal_profile,
                aliases=[],
                player_controllable=True,
                source_path=f"{path}#{table}:{raw_id}",
                source_updated_at=db_updated_at,
                status="active",
            )
        )
    return sources


def _choose_character_table(con: sqlite3.Connection) -> str:
    tables = [
        row[0]
        for row in con.execute(
            "select name from sqlite_master where type='table' and name not like 'sqlite_%' order by name"
        )
    ]
    if "characters" in tables:
        return "characters"
    for table in tables:
        columns = _table_columns(con, table)
        if _choose_column(columns, ("background", "background_lore", "background_story")) and _choose_column(
            columns,
            ("personality", "personality_setting", "personal_profile"),
        ):
            return table
    raise ValueError("SQLite 数据库中未找到角色表")


def _table_columns(con: sqlite3.Connection, table: str) -> list[str]:
    return [row[1] for row in con.execute("pragma table_info(" + _quote_identifier(table) + ")")]


def _choose_column(columns: list[str], candidates: tuple[str, ...]) -> str:
    normalized = {column.lower(): column for column in columns}
    for candidate in candidates:
        if candidate.lower() in normalized:
            return normalized[candidate.lower()]
    return ""


def _quote_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _db_character_id(raw_id: str) -> str:
    if raw_id.isdigit():
        return f"db_char_{int(raw_id):04d}"
    safe = re.sub(r"[^A-Za-z0-9_]+", "_", raw_id).strip("_").lower()
    return f"db_char_{safe or 'unknown'}"


def _source_from_json(path: Path) -> CharacterSource:
    data = read_json(path)
    character_id = _required_str(data, "character_id", path)
    name = _required_str(data, "name", path)
    background_story = str(data.get("background_story", ""))
    personal_profile = str(data.get("personal_profile", ""))
    if not background_story and not personal_profile:
        raise ValueError(f"角色资料缺少 background_story 和 personal_profile：{path}")

    return CharacterSource(
        character_id=character_id,
        name=name,
        background_story=background_story,
        personal_profile=personal_profile,
        aliases=list(data.get("aliases", [])),
        player_controllable=bool(data.get("player_controllable", True)),
        source_path=str(path),
        source_updated_at=_mtime_iso(path),
        status=str(data.get("status", "active")),
    )


def _source_from_directory(path: Path) -> CharacterSource | None:
    metadata_path = path / "metadata.json"
    background_path = path / "background_story.txt"
    profile_path = path / "personal_profile.txt"
    if not metadata_path.exists():
        return None

    metadata = read_json(metadata_path)
    character_id = _required_str(metadata, "character_id", metadata_path)
    name = _required_str(metadata, "name", metadata_path)
    background_story = (
        background_path.read_text(encoding="utf-8-sig") if background_path.exists() else ""
    )
    personal_profile = (
        profile_path.read_text(encoding="utf-8-sig") if profile_path.exists() else ""
    )
    if not background_story and not personal_profile:
        raise ValueError(f"角色目录缺少背景故事和个人概括：{path}")

    updated_at = max(
        item.stat().st_mtime
        for item in [metadata_path, background_path, profile_path]
        if item.exists()
    )
    return CharacterSource(
        character_id=character_id,
        name=name,
        background_story=background_story,
        personal_profile=personal_profile,
        aliases=list(metadata.get("aliases", [])),
        player_controllable=bool(metadata.get("player_controllable", True)),
        source_path=str(path),
        source_updated_at=_timestamp_iso(updated_at),
        status=str(metadata.get("status", "active")),
    )


def _required_str(data: dict, key: str, path: Path) -> str:
    value = str(data.get(key, "")).strip()
    if not value:
        raise ValueError(f"角色资料缺少必填字段 {key}：{path}")
    return value


def _mtime_iso(path: Path) -> str:
    return _timestamp_iso(path.stat().st_mtime)


def _timestamp_iso(timestamp: float) -> str:
    from datetime import datetime, timezone

    return datetime.fromtimestamp(timestamp, timezone.utc).isoformat()
