from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Any

try:
    from langchain_core.tools import tool
except ModuleNotFoundError:
    class _SimpleTool:
        def __init__(self, func, name=None):
            self.func = func
            self.name = name or func.__name__
            self.__name__ = self.name
            self.description = func.__doc__ or ""

        def invoke(self, value):
            if isinstance(value, dict):
                return self.func(**value)
            return self.func(value)

        def __call__(self, *args, **kwargs):
            return self.func(*args, **kwargs)

    def tool(*args, **kwargs):
        if args and callable(args[0]):
            return _SimpleTool(args[0])
        name = args[0] if args and isinstance(args[0], str) else kwargs.get("name")

        def decorator(func):
            return _SimpleTool(func, name=name)

        return decorator

GAMEPULSE_ROOT = Path(__file__).resolve().parents[1]
VENDOR_ROOT = GAMEPULSE_ROOT / "agent" / "vendor_tools"
if str(VENDOR_ROOT) not in sys.path:
    sys.path.insert(0, str(VENDOR_ROOT))

DEFAULT_CHARACTER_JSON_DIR = VENDOR_ROOT / "character_outputs" / "character_json"
DEFAULT_STORY_LIBRARY = VENDOR_ROOT / "story_library"
DEFAULT_WORLD_PATH = VENDOR_ROOT / "world_outlook" / "world.txt"
DEFAULT_RAG_ROOT = Path(os.getenv("GAMEPULSE_RAG_ROOT", str(GAMEPULSE_ROOT / "rag")))
if not (DEFAULT_RAG_ROOT / "rag_query.py").exists() and (GAMEPULSE_ROOT.parent / "rag" / "rag_query.py").exists():
    DEFAULT_RAG_ROOT = GAMEPULSE_ROOT.parent / "rag"
DEFAULT_RAG_SCRIPT = DEFAULT_RAG_ROOT / "rag_query.py"
DEFAULT_CHROMA_DIR = DEFAULT_RAG_ROOT / "chroma_db" / "chroma_db"
DEFAULT_EMBEDDING_MODEL = DEFAULT_RAG_ROOT / "models" / "bge-m3"
DEFAULT_RISK_DB = Path(r"D:\program\two-dimensional_game\agent.db")
DEFAULT_RISK_OUTPUT_DIR = Path(r"D:\program\two-dimensional_game\record\story_risk_summary")
DEFAULT_RISK_SCRIPT = VENDOR_ROOT / "risk_card_story_tool" / "compress_risk_titles.py"


def _to_json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


def _terms(query: str) -> list[str]:
    query = (query or "").strip()
    terms = [query] if query else []
    for token in query.replace("，", " ").replace("、", " ").replace("？", " ").split():
        token = token.strip()
        if token and token not in terms:
            terms.append(token)
    for size in (4, 3, 2):
        for start in range(0, max(len(query) - size + 1, 0)):
            token = query[start : start + size]
            if token.strip() and token not in terms:
                terms.append(token)
    return terms[:40]


def _score_text(text: str, terms: list[str]) -> int:
    if not text:
        return 0
    score = 0
    for term in terms:
        if not term:
            continue
        count = text.count(term)
        if count:
            score += count * max(len(term), 1)
    return score


def _load_character_summaries() -> list[dict[str, Any]]:
    json_dir = Path(os.getenv("GAMEPULSE_CHARACTER_JSON_DIR", str(DEFAULT_CHARACTER_JSON_DIR)))
    if not json_dir.exists():
        return []
    summaries = []
    for path in sorted(json_dir.glob("*.json")):
        if path.name == "character_index.json":
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if data.get("metadata", {}).get("summarized") == 1:
            summaries.append(data)
    return summaries


def _compact_character(data: dict[str, Any]) -> dict[str, Any]:
    metadata = data.get("metadata", {}) or {}
    basic = data.get("basic_info", {}) or {}
    relationships = data.get("relationships", []) or []
    return {
        "character_id": metadata.get("character_id", ""),
        "name": metadata.get("name", ""),
        "basic": "；".join(
            str(value)
            for value in [basic.get("occupation"), basic.get("identity"), basic.get("faction")]
            if value
        ) or "-",
        "traits": data.get("personality") or "-",
        "background": data.get("background") or "-",
        "motivation": data.get("motivation") or "-",
        "relations": "；".join(
            f"{item.get('name', '')}={item.get('relation', '')}".strip("=")
            for item in relationships
            if isinstance(item, dict) and (item.get("name") or item.get("relation"))
        ) or "-",
    }


@tool
def get_character_profiles(query: str) -> str:
    """查询已结构化角色档案，用于角色设定、性格、动机、背景和关系检索。"""
    terms = _terms(query)
    summaries = _load_character_summaries()
    ranked = []
    for data in summaries:
        compact = _compact_character(data)
        searchable = _to_json(compact)
        score = _score_text(searchable, terms)
        if score > 0:
            ranked.append((score, compact))
    ranked.sort(key=lambda item: (-item[0], item[1].get("character_id", "")))
    if not ranked:
        return _to_json(
            {
                "success": False,
                "query": query,
                "results": [],
                "warnings": ["未检索到相关角色档案；可先运行 scan_character_library 生成角色 JSON。"],
                "source": str(Path(os.getenv("GAMEPULSE_CHARACTER_JSON_DIR", str(DEFAULT_CHARACTER_JSON_DIR)))),
            }
        )
    return _to_json(
        {
            "success": True,
            "query": query,
            "results": [item for _, item in ranked[:8]],
            "source": str(Path(os.getenv("GAMEPULSE_CHARACTER_JSON_DIR", str(DEFAULT_CHARACTER_JSON_DIR)))),
        }
    )


@tool("get_world_lore")
def get_world_lore_tool(query: str, section: str | None = None, max_chars: int = 2200) -> str:
    """查询《鸣潮》世界观事实资料；只返回 world.txt 中明确存在的信息。"""
    from worldview_tool import get_world_lore as _get_world_lore

    result = _get_world_lore(
        query=query,
        section=section,
        max_chars=max_chars,
        world_path=Path(os.getenv("GAMEPULSE_WORLD_PATH", str(DEFAULT_WORLD_PATH))),
    )
    return _to_json(result)


@tool
def rag_search_story(query: str, top_k: int = 8) -> str:
    """查询剧情资料或外部 Chroma RAG，并返回结构化剧情上下文和来源片段。"""
    from story_retrieval_tool import query_story_context
    from story_retrieval_tool.summarizer import build_summarizer

    rag_script = os.getenv("GAMEPULSE_RAG_SCRIPT")
    chroma_dir = os.getenv("GAMEPULSE_CHROMA_DIR")
    embedding_model = os.getenv("GAMEPULSE_EMBEDDING_MODEL")
    has_internal_rag = DEFAULT_RAG_SCRIPT.exists() and DEFAULT_CHROMA_DIR.exists() and DEFAULT_EMBEDDING_MODEL.exists()
    if not rag_script and has_internal_rag:
        rag_script = str(DEFAULT_RAG_SCRIPT)
    if not chroma_dir and has_internal_rag:
        chroma_dir = str(DEFAULT_CHROMA_DIR)
    if not embedding_model and has_internal_rag:
        embedding_model = str(DEFAULT_EMBEDDING_MODEL)
    retriever = os.getenv("GAMEPULSE_STORY_RETRIEVER") or ("chroma-rag" if rag_script else "keyword")
    summarizer_name = os.getenv("GAMEPULSE_STORY_SUMMARIZER", "mock")

    result = query_story_context(
        query=query,
        story_library_path=os.getenv("GAMEPULSE_STORY_LIBRARY", str(DEFAULT_STORY_LIBRARY)),
        top_k=top_k,
        retriever=retriever,
        rag_script_path=rag_script,
        chroma_dir=chroma_dir,
        embedding_model_path=embedding_model,
        summarizer=build_summarizer(summarizer_name),
    )
    return _to_json(result)


def _risk_rows_from_db(query: str, max_results: int) -> list[dict[str, Any]]:
    db_path = Path(os.getenv("GAMEPULSE_RISK_DB", str(DEFAULT_RISK_DB)))
    if not db_path.exists():
        return []
    try:
        con = sqlite3.connect(db_path)
        con.row_factory = sqlite3.Row
        exists = con.execute(
            "select name from sqlite_master where type='table' and name='story_risk_summary'"
        ).fetchone()
        if not exists:
            return []
        rows = con.execute(
            "select analysis_id, character_id, title, story_relevance, risk_summary, evidence "
            "from story_risk_summary order by id desc limit 500"
        ).fetchall()
    except Exception:
        return []
    finally:
        try:
            con.close()
        except Exception:
            pass

    terms = _terms(query)
    ranked = []
    for row in rows:
        item = dict(row)
        score = _score_text(_to_json(item), terms)
        if score > 0:
            ranked.append((score, item))
    ranked.sort(key=lambda item: -item[0])
    return [item for _, item in ranked[:max_results]]


def _risk_rows_from_latest_json(query: str, max_results: int) -> list[dict[str, Any]]:
    out_dir = Path(os.getenv("GAMEPULSE_RISK_OUTPUT_DIR", str(DEFAULT_RISK_OUTPUT_DIR)))
    candidates = sorted(out_dir.glob("story_risk_summary_*.json"), key=lambda path: path.stat().st_mtime, reverse=True) if out_dir.exists() else []
    if not candidates:
        vendor_examples = VENDOR_ROOT / "risk_card_story_tool" / "examples"
        candidates = sorted(vendor_examples.glob("story_risk_summary_*.json"), key=lambda path: path.stat().st_mtime, reverse=True) if vendor_examples.exists() else []
    if not candidates:
        return []
    try:
        data = json.loads(candidates[0].read_text(encoding="utf-8-sig"))
    except Exception:
        return []
    rows = data.get("selected_risks", []) if isinstance(data, dict) else []
    terms = _terms(query)
    ranked = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        score = _score_text(_to_json(row), terms)
        if score > 0:
            ranked.append((score, row))
    ranked.sort(key=lambda item: -item[0])
    return [item for _, item in ranked[:max_results]]


@tool
def search_risk_cards(query: str, max_results: int = 8) -> str:
    """查询剧情/角色强相关风险卡摘要，用于识别 OOC、叙事节奏、设定冲突和玩家接受风险。"""
    max_results = max(1, min(int(max_results or 8), 20))
    rows = _risk_rows_from_db(query, max_results) or _risk_rows_from_latest_json(query, max_results)
    if not rows:
        return _to_json(
            {
                "success": False,
                "query": query,
                "results": [],
                "warnings": ["未找到已生成的剧情风险卡摘要；可先运行 risk_card_story_tool/compress_risk_titles.py。"],
                "source": [str(DEFAULT_RISK_DB), str(DEFAULT_RISK_OUTPUT_DIR)],
            }
        )
    return _to_json({"success": True, "query": query, "results": rows[:max_results]})


@tool
def refresh_story_risk_cards(max_items: int = 20, run_api: bool = False) -> str:
    """刷新剧情风险卡摘要；默认只做无 API 小样本检查，run_api=True 时才调用模型。"""
    script = Path(os.getenv("GAMEPULSE_RISK_SCRIPT", str(DEFAULT_RISK_SCRIPT)))
    if not script.exists():
        return _to_json({"success": False, "warnings": [f"找不到风险卡脚本：{script}"]})
    command = [sys.executable, str(script), "--max-items", str(max(0, int(max_items or 0)))]
    if run_api:
        command.append("--run-api")
    try:
        completed = subprocess.run(
            command,
            cwd=str(script.parent),
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=240,
        )
    except Exception as exc:
        return _to_json({"success": False, "warnings": [str(exc)]})
    return _to_json(
        {
            "success": completed.returncode == 0,
            "returncode": completed.returncode,
            "stdout": completed.stdout[-4000:],
            "stderr": completed.stderr[-2000:],
        }
    )


@tool
def rewrite_script(text: str) -> str:
    """对高风险台词或设定表达进行轻量改写占位；正式改写仍由上层 Agent 根据审查结论完成。"""
    return _to_json(
        {
            "success": True,
            "input": text,
            "suggestion": "请结合角色档案、剧情来源片段、世界观事实和风险卡结论后再生成正式改写。",
        }
    )








