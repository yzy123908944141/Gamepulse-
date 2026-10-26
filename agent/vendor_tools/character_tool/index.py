from __future__ import annotations

from pathlib import Path

from character_tool.io_utils import atomic_write_json, read_json
from character_tool.schemas import CharacterIndexItem


INDEX_FILENAME = "character_index.json"


def index_path_for(output_json_path: str | Path) -> Path:
    return Path(output_json_path) / INDEX_FILENAME


def load_index(output_json_path: str | Path) -> dict[str, CharacterIndexItem]:
    path = index_path_for(output_json_path)
    if not path.exists():
        return {}

    raw = read_json(path)
    records = raw.get("characters", raw if isinstance(raw, list) else [])
    index: dict[str, CharacterIndexItem] = {}
    for item in records:
        character_id = str(item.get("character_id", "")).strip()
        if not character_id:
            continue
        index[character_id] = CharacterIndexItem(
            character_id=character_id,
            name=str(item.get("name", "")),
            summarized=int(item.get("summarized", 0)),
            source_hash=str(item.get("source_hash", "")),
            source_updated_at=str(item.get("source_updated_at", "")),
            summary_updated_at=str(item.get("summary_updated_at", "")),
            status=str(item.get("status", "active")),
            error=str(item.get("error", "")),
        )
    return index


def save_index(output_json_path: str | Path, index: dict[str, CharacterIndexItem]) -> None:
    path = index_path_for(output_json_path)
    payload = {
        "characters": [
            item.to_dict()
            for item in sorted(index.values(), key=lambda record: record.character_id)
        ]
    }
    atomic_write_json(path, payload)
