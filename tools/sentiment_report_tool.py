"""
generate_sentiment_report tool

This tool builds a structured sentiment report from Feature A analysis data.
It can be used in two ways:

1. Direct Python call:
   result = generate_sentiment_report(character_id=1, character_name="灯灯")

2. Agent tool call:
   generate_sentiment_report_tool.invoke({...})
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from langchain_core.tools import tool
except Exception:  # pragma: no cover - keeps direct Python use available without LangChain
    def tool(func=None, **_kwargs):
        if func is None:
            return lambda f: f
        return func

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ANALYSIS_DIR = PROJECT_ROOT / "data" / "analysis"


def _default_db_path(filename: str) -> str:
    """Prefer GamePulse local databases, then the source data project, then legacy db/."""
    root_path = PROJECT_ROOT / filename
    if root_path.exists():
        return str(root_path)
    source_project_path = Path(r"D:\program\two-dimensional_game") / filename
    if source_project_path.exists():
        return str(source_project_path)
    return str(PROJECT_ROOT / "db" / filename)


RAW_DB_PATH = os.getenv("GAMERPULSE_RAW_DB_PATH", _default_db_path("raw_data.db"))
AGENT_DB_PATH = os.getenv("GAMERPULSE_AGENT_DB_PATH", _default_db_path("agent.db"))

if ANALYSIS_DIR.exists() and str(ANALYSIS_DIR) not in sys.path:
    sys.path.insert(0, str(ANALYSIS_DIR))


def _connect_sqlite(path: str):
    if not Path(path).exists():
        raise FileNotFoundError(f"SQLite database not found: {path}")
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        conn.execute("PRAGMA journal_mode = WAL")
    except sqlite3.OperationalError:
        pass
    return conn


def get_raw_db_conn():
    return _connect_sqlite(RAW_DB_PATH)


def get_agent_db_conn():
    return _connect_sqlite(AGENT_DB_PATH)

try:
    from .diagnosis import RawComment, generate_diagnosis
except Exception:  # LLM dependencies are optional for non-LLM report tools.
    try:
        from data.analysis.diagnosis import RawComment, generate_diagnosis
    except Exception:
        try:
            from diagnosis import RawComment, generate_diagnosis
        except Exception:
            RawComment = None
            generate_diagnosis = None


SENTIMENT_LABELS = ("positive", "negative", "neutral")

RED_LINE_RULES = [
    {
        "id": "world_001",
        "dimension": "world",
        "tags": ["现代词", "世界观违和", "设定穿帮"],
        "level": "high",
        "title": "禁止出现明显现代互联网/现实商业词汇",
        "description": "剧情文本不应直接出现手机、热搜、KPI、直播等破坏二游世界观沉浸感的现实词。",
        "suggestion": "改成游戏内通讯器、城邦公告、组织考核、记录投影等架空表达。",
    },
    {
        "id": "world_002",
        "dimension": "world",
        "tags": ["现实政治", "现实映射", "阵营冲突"],
        "level": "critical",
        "title": "避免直接映射现实政治实体或现实群体冲突",
        "description": "世界观冲突应保持架空，不要直接套用现实政党、现实民族或现实社会事件。",
        "suggestion": "改成虚构城邦、组织、灾变或阵营矛盾。",
    },
    {
        "id": "narrative_001",
        "dimension": "narrative",
        "tags": ["伏笔", "剧情承接", "突然反转"],
        "level": "high",
        "title": "关键反转必须有前置铺垫",
        "description": "新角色登场、身份揭露、能力觉醒、阵营反转不能没有旧版本线索支撑。",
        "suggestion": "补充 NPC 台词、旧档案、支线传闻或可回忆的事件钩子。",
    },
    {
        "id": "narrative_002",
        "dimension": "narrative",
        "tags": ["信息密度", "说明台词", "节奏"],
        "level": "medium",
        "title": "避免用大段说明台词替代剧情推进",
        "description": "玩家集中吐槽的信息轰炸、纯设定解释、长段独白会降低剧情接受度。",
        "suggestion": "拆成行动、冲突、短句判断和可互动线索。",
    },
    {
        "id": "character_001",
        "dimension": "character",
        "tags": ["OOC", "角色语气", "人设割裂"],
        "level": "high",
        "title": "已上线角色不得突然改变核心语气和行为逻辑",
        "description": "角色台词、行动动机必须符合既有档案和玩家已形成的角色印象。",
        "suggestion": "先查角色档案与历史剧情，再把台词改成符合角色惯用表达的版本。",
    },
    {
        "id": "character_002",
        "dimension": "character",
        "tags": ["抢主角", "强行救世主", "人设重合"],
        "level": "high",
        "title": "新角色不能直接抢走主角或已有角色的核心功能",
        "description": "新角色不能一登场就成为唯一答案或压过已有角色的剧情价值。",
        "suggestion": "把“唯一解决者”改成“掌握关键线索者”，保留主角判断和已有角色分工。",
    },
    {
        "id": "compliance_001",
        "dimension": "compliance",
        "tags": ["血腥暴力", "极端表达", "合规"],
        "level": "critical",
        "title": "避免细节化极端暴力或血腥描写",
        "description": "剧情可以表达危险和冲突，但不应细节化虐杀、肢解、血腥处决等内容。",
        "suggestion": "改成击败、封印、重创、失去行动能力等弱化表达。",
    },
]


@dataclass
class ReportComment:
    id: int
    raw_comment_id: int
    character_id: Optional[int]
    character_name: Optional[str]
    source: str
    content: str
    sentiment: str
    tag: str
    is_toxic: int
    publish_date: str
    url: str
    decision_source: str
    reason: Optional[str] = None


def _safe_json_loads(value: Any, default: Any) -> Any:
    if value is None:
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except Exception:
        return default


def _parse_date(value: str | None) -> Optional[datetime]:
    if not value:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%Y/%m/%d %H:%M:%S", "%Y/%m/%d"):
        try:
            return datetime.strptime(str(value), fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
    except Exception:
        return None


def _empty_report(character_id: Optional[int], character_name: Optional[str], days: int) -> Dict[str, Any]:
    return {
        "tool_name": "generate_sentiment_report",
        "tool_version": "1.0.0",
        "status": "ok",
        "character": {"id": character_id, "name": character_name},
        "period": {"days": days, "start_date": None, "end_date": None},
        "summary": {
            "total_comments": 0,
            "sentiment_counts": {"positive": 0, "negative": 0, "neutral": 0},
            "sentiment_ratio": {"positive": 0.0, "negative": 0.0, "neutral": 0.0},
            "toxic_count": 0,
            "toxic_ratio": 0.0,
            "top_tags": [],
            "top_sources": [],
        },
        "scores": {
            "sentiment_health_score": 50,
            "character_score": None,
            "gameplay_score": None,
            "system_pain_score": None,
        },
        "risk_warnings": [],
        "word_cloud_data": [],
        "sample_comments": [],
        "latest_analysis_result": None,
        "recommendations": ["暂无可用评论数据，建议先运行单条评论分析并入库。"],
        "meta": {"source": "agent_db", "llm_diagnosis_used": False},
    }



def _get_table_columns(conn, table_name: str) -> set[str]:
    cursor = conn.cursor()
    try:
        cursor.execute(f"PRAGMA table_info({table_name})")
        return {row[1] for row in cursor.fetchall()}
    except Exception:
        return set()
def _fetch_comments_from_agent_db(
    character_id: Optional[int],
    character_name: Optional[str],
    days: int,
    limit: int,
) -> List[ReportComment]:
    if get_agent_db_conn is None:
        return []

    conn = get_agent_db_conn()
    cursor = conn.cursor()
    analysis_columns = _get_table_columns(conn, "analysis_comments")
    decision_expr = "COALESCE(ac.decision_source, '')" if "decision_source" in analysis_columns else "''"
    reason_expr = "ac.reason" if "reason" in analysis_columns else "NULL"
    params: list[Any] = []

    # 全局舆情：不经过 analysis_characters，避免一条评论关联多个角色时被重复统计。
    if character_id is None and not character_name:
        query = f"""
            SELECT
                ac.id,
                ac.raw_comment_id,
                NULL AS character_id,
                NULL AS character_name,
                ac.sentiment,
                ac.tag,
                COALESCE(ac.is_toxic, 0) AS is_toxic,
                {decision_expr} AS decision_source,
                {reason_expr} AS reason
            FROM analysis_comments ac
            ORDER BY ac.id DESC
            LIMIT ?
        """
        params.append(limit)
    else:
        where = []
        if character_id is not None:
            where.append("ach.character_id = ?")
            params.append(character_id)
        if character_name:
            where.append("ach.character_name = ?")
            params.append(character_name)
        where_sql = " AND ".join(where) if where else "1=1"
        query = f"""
            SELECT
                ac.id,
                ac.raw_comment_id,
                ach.character_id,
                ach.character_name,
                ac.sentiment,
                ac.tag,
                COALESCE(ac.is_toxic, 0) AS is_toxic,
                {decision_expr} AS decision_source,
                {reason_expr} AS reason
            FROM analysis_comments ac
            LEFT JOIN analysis_characters ach ON ach.analysis_comment_id = ac.id
            WHERE {where_sql}
            ORDER BY ac.id DESC
            LIMIT ?
        """
        params.append(limit)

    try:
        cursor.execute(query, params)
        rows = cursor.fetchall()
    except Exception as exc:
        conn.close()
        raise RuntimeError(f"Failed to read analysis comments from {AGENT_DB_PATH}: {exc}") from exc
    conn.close()

    raw_map = _fetch_raw_comment_map([row[1] for row in rows])
    since = datetime.now() - timedelta(days=max(days, 1))
    comments: list[ReportComment] = []
    for row in rows:
        raw = raw_map.get(row[1], {})
        publish_date = raw.get("publish_date", "")
        parsed_date = _parse_date(publish_date)
        if parsed_date is not None and parsed_date < since:
            continue
        comments.append(
            ReportComment(
                id=row[0],
                raw_comment_id=row[1],
                character_id=row[2],
                character_name=row[3],
                source=raw.get("source", ""),
                content=raw.get("content", ""),
                sentiment=row[4] if row[4] in SENTIMENT_LABELS else "neutral",
                tag=row[5] or "未知",
                is_toxic=int(row[6] or 0),
                publish_date=publish_date,
                url=raw.get("url", ""),
                decision_source=row[7] or "",
                reason=row[8],
            )
        )

    comments.sort(key=lambda item: (_parse_date(item.publish_date) or datetime.min, item.id), reverse=True)
    return comments

def _fetch_raw_comment_map(raw_comment_ids: list[int]) -> dict[int, dict[str, Any]]:
    if get_raw_db_conn is None or not raw_comment_ids:
        return {}

    ids = sorted({int(raw_id) for raw_id in raw_comment_ids if raw_id is not None})
    if not ids:
        return {}

    placeholders = ",".join("?" for _ in ids)
    query = f"SELECT id, source, content, publish_date, url FROM raw_comments WHERE id IN ({placeholders})"

    conn = get_raw_db_conn()
    cursor = conn.cursor()
    try:
        cursor.execute(query, ids)
        rows = cursor.fetchall()
    except Exception as exc:
        conn.close()
        raise RuntimeError(f"Failed to read raw comments from {RAW_DB_PATH}: {exc}") from exc
    conn.close()

    return {
        row[0]: {
            "source": row[1] or "",
            "content": row[2] or "",
            "publish_date": row[3] or "",
            "url": row[4] or "",
        }
        for row in rows
    }


def _fetch_latest_analysis_result(character_id: Optional[int]) -> Optional[Dict[str, Any]]:
    if get_agent_db_conn is None or character_id is None:
        return None

    conn = get_agent_db_conn()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT id, character_id, analysis_date, character_score, gameplay_score,
                   system_pain_score, risk_warnings, word_cloud_data, source_comment_ids
            FROM analysis_results
            WHERE character_id = ?
            ORDER BY analysis_date DESC, id DESC
            LIMIT 1
            """,
            (character_id,),
        )
        row = cursor.fetchone()
    except Exception:
        conn.close()
        return None
    conn.close()

    if not row:
        return None

    return {
        "id": row[0],
        "character_id": row[1],
        "analysis_date": row[2],
        "character_score": row[3],
        "gameplay_score": row[4],
        "system_pain_score": row[5],
        "risk_warnings": _safe_json_loads(row[6], []),
        "word_cloud_data": _safe_json_loads(row[7], []),
        "source_comment_ids": row[8],
    }


def _ratio(count: int, total: int) -> float:
    return round(count / total, 4) if total else 0.0


def _calculate_sentiment_health_score(sentiment_counts: Counter, toxic_count: int, total: int) -> int:
    if total == 0:
        return 50
    positive = sentiment_counts.get("positive", 0)
    negative = sentiment_counts.get("negative", 0)
    neutral = sentiment_counts.get("neutral", 0)
    score = 50 + positive * 8 + neutral * 1 - negative * 10 - toxic_count * 8
    normalized = score / max(total, 1)
    return max(0, min(100, int(round(50 + normalized * 5))))


def _build_recommendations(
    sentiment_counts: Counter,
    toxic_count: int,
    total: int,
    top_tags: list[dict[str, Any]],
) -> list[str]:
    if total == 0:
        return ["暂无可用评论数据，建议先运行单条评论分析并入库。"]

    recommendations = []
    negative_count = sentiment_counts.get("negative", 0)
    positive_count = sentiment_counts.get("positive", 0)
    negative_ratio = _ratio(negative_count, total)
    positive_ratio = _ratio(positive_count, total)
    toxic_ratio = _ratio(toxic_count, total)
    top_tag_names = [str(item.get("tag", "")) for item in top_tags[:3]]

    if negative_ratio >= 0.65:
        recommendations.append(
            f"负面占比达到 {_percent(negative_ratio)}，建议优先做专项复盘：抽取该角色负面评论 Top 20，按“剧情/角色/系统/演出”四类重新标注，找出最集中的触发点。"
        )
    elif negative_ratio >= 0.35:
        recommendations.append(
            f"负面占比为 {_percent(negative_ratio)}，属于需要关注区间；建议先查看高频标签对应原始评论，判断是角色本身问题还是版本体验牵连。"
        )
    else:
        recommendations.append(
            f"负面占比为 {_percent(negative_ratio)}，整体压力不高；建议保持日常监控，重点观察新增评论是否出现集中转负。"
        )

    if toxic_ratio >= 0.15:
        recommendations.append(
            f"攻击性评论占比 {_percent(toxic_ratio)} 偏高，建议将该角色加入风险卡观察名单，并整理典型攻击性表达给文案和运营侧避雷。"
        )
    elif toxic_ratio > 0:
        recommendations.append(
            f"攻击性评论占比 {_percent(toxic_ratio)}，数量不算高但已有情绪化表达；建议保留样例评论，后续版本更新时观察是否扩大。"
        )

    for tag in top_tag_names:
        if "剧情节奏" in tag:
            recommendations.append(
                "高频槽点包含“剧情节奏”，建议回看该角色相关剧情段落的铺垫长度、跳过限制、信息密度和转场节奏，优先减少重复说明和低互动长对白。"
            )
        elif "角色塑造" in tag:
            recommendations.append(
                "高频槽点包含“角色塑造”，建议检查角色动机、台词语气、关系线推进和高光场景是否一致，必要时补充能体现角色主动性的短场景。"
            )
        elif "角色关系" in tag or "情感线" in tag:
            recommendations.append(
                "高频槽点包含“角色关系/情感线”，建议重点复核亲密度推进是否过快、主角参与感是否被削弱，以及玩家是否认为关系变化缺少前置铺垫。"
            )
        elif "抽卡" in tag:
            recommendations.append(
                "高频槽点包含“抽卡系统”，建议区分玩家是在骂角色还是在骂卡池体验；展示角色时避免把商业压力和角色人设绑定得太紧。"
            )
        elif "战斗" in tag or "玩法" in tag:
            recommendations.append(
                "高频槽点包含“战斗与玩法”，建议联动玩法同学检查角色实战手感、强度预期和剧情承诺是否一致，避免文案塑造与实际体验落差过大。"
            )
        elif "美术" in tag or "演出" in tag:
            recommendations.append(
                "高频槽点包含“美术/演出”，建议拆分正负面样例：保留被认可的镜头、建模或配音素材，同时定位被吐槽的演出节奏和镜头重复问题。"
            )
        elif "整体评价" in tag:
            recommendations.append(
                "高频槽点包含“整体评价”，说明玩家反馈较泛化；建议继续下钻原始评论，找出其中反复出现的具体词，如拖沓、无聊、福利、强度或人设。"
            )

    if positive_ratio >= 0.4:
        recommendations.append(
            f"正面占比 {_percent(positive_ratio)} 仍有可利用空间，建议提取正面评论中的高频认可点，用于后续角色亮点包装和运营话术。"
        )

    if not recommendations:
        recommendations.append("当前舆情整体稳定，可继续跟踪新增评论趋势，并定期对高频标签做轻量复盘。")

    deduped = []
    for item in recommendations:
        if item not in deduped:
            deduped.append(item)
    return deduped[:6]

def _comments_to_raw_comments(comments: list[ReportComment]) -> list[Any]:
    if RawComment is None:
        return []
    return [
        RawComment(
            id=comment.raw_comment_id,
            character_id=comment.character_id or 0,
            source=comment.source,
            content=comment.content,
            sentiment=comment.sentiment,
            tag=comment.tag,
            is_toxic=bool(comment.is_toxic),
            publish_date=comment.publish_date,
        )
        for comment in comments
    ]


def _normalize_tags(tags: Any) -> list[str]:
    if tags is None:
        return []
    if isinstance(tags, str):
        return [item.strip() for item in tags.replace("，", ",").split(",") if item.strip()]
    return [str(item).strip() for item in tags if str(item).strip()]


def _comment_matches_entity(comment: ReportComment, entity_type: str, entity_tags: list[str]) -> bool:
    if not entity_tags:
        return True
    entity_type = (entity_type or "all").lower()
    lowered_tags = [tag.lower() for tag in entity_tags]

    if entity_type in {"character", "character_name"}:
        return str(comment.character_name or "").lower() in lowered_tags or str(comment.character_id or "") in lowered_tags
    if entity_type in {"tag", "comment_tag"}:
        return str(comment.tag or "").lower() in lowered_tags
    if entity_type in {"source", "platform"}:
        return str(comment.source or "").lower() in lowered_tags
    if entity_type in {"keyword", "text"}:
        content = (comment.content or "").lower()
        return any(tag in content for tag in lowered_tags)
    return True


def _resolve_time_range(time_range: Any) -> tuple[datetime, datetime, int]:
    end = datetime.now()
    if isinstance(time_range, dict):
        start = _parse_date(time_range.get("start") or time_range.get("start_date"))
        parsed_end = _parse_date(time_range.get("end") or time_range.get("end_date"))
        if parsed_end is not None:
            end = parsed_end
        if start is not None:
            return start, end, max(1, (end - start).days + 1)

    text = str(time_range or "30d").strip().lower()
    if text.endswith("d") and text[:-1].isdigit():
        days = int(text[:-1])
    elif text.isdigit():
        days = int(text)
    elif text in {"week", "7天", "一周"}:
        days = 7
    elif text in {"month", "30天", "一个月"}:
        days = 30
    else:
        days = 30
    start = end - timedelta(days=max(days, 1) - 1)
    return start, end, max(days, 1)


def get_red_lines(dimension: str, tags: Any = None) -> Dict[str, Any]:
    """
    查红线约束。

    Args:
        dimension: 维度，例如 world / narrative / character / compliance。
        tags: 标签列表或逗号分隔字符串，例如 ["OOC", "强行救世主"]。

    Returns:
        该维度下匹配的红线规则列表。
    """
    normalized_dimension = (dimension or "").strip().lower()
    normalized_tags = _normalize_tags(tags)
    tag_set = {tag.lower() for tag in normalized_tags}

    rules = []
    for rule in RED_LINE_RULES:
        if normalized_dimension and rule["dimension"].lower() != normalized_dimension:
            continue
        if tag_set:
            rule_tags = {tag.lower() for tag in rule.get("tags", [])}
            searchable = rule_tags | {str(rule.get("title", "")).lower(), str(rule.get("description", "")).lower()}
            if not any(tag in item or item in tag for tag in tag_set for item in searchable):
                continue
        rules.append(rule)

    return {
        "tool_name": "get_red_lines",
        "tool_version": "1.0.0",
        "status": "ok",
        "input": {"dimension": dimension, "tags": normalized_tags},
        "rules": rules,
        "summary": {"total": len(rules)},
    }


def get_top_complaints(entity_type: str, entity_tags: Any = None, limit: int = 5) -> Dict[str, Any]:
    """
    查 Top N 槽点。

    Args:
        entity_type: 查询实体类型，支持 character / tag / source / keyword / all。
        entity_tags: 实体标签、角色名、平台名或关键词列表。
        limit: 返回 Top N 数量。

    Returns:
        玩家集中吐槽的 Top N 点。
    """
    normalized_tags = _normalize_tags(entity_tags)
    comments = _fetch_comments_from_agent_db(None, None, days=3650, limit=2000)
    filtered = [comment for comment in comments if _comment_matches_entity(comment, entity_type, normalized_tags)]

    complaint_comments = [
        comment for comment in filtered
        if comment.sentiment == "negative" or comment.is_toxic or comment.tag not in {"内容讨论", "正向反馈", "未知"}
    ]
    grouped: dict[str, dict[str, Any]] = {}
    for comment in complaint_comments:
        key = comment.tag or "未知槽点"
        item = grouped.setdefault(
            key,
            {
                "complaint": key,
                "count": 0,
                "negative_count": 0,
                "toxic_count": 0,
                "sample_comment_ids": [],
                "sample_comments": [],
            },
        )
        item["count"] += 1
        item["negative_count"] += 1 if comment.sentiment == "negative" else 0
        item["toxic_count"] += int(comment.is_toxic or 0)
        if len(item["sample_comment_ids"]) < 5:
            item["sample_comment_ids"].append(comment.raw_comment_id)
        if len(item["sample_comments"]) < 3 and comment.content:
            item["sample_comments"].append(comment.content[:120])

    complaints = sorted(
        grouped.values(),
        key=lambda item: (item["negative_count"] + item["toxic_count"] * 2, item["count"]),
        reverse=True,
    )[: max(1, int(limit or 5))]

    return {
        "tool_name": "get_top_complaints",
        "tool_version": "1.0.0",
        "status": "ok",
        "input": {
            "entity_type": entity_type,
            "entity_tags": normalized_tags,
            "limit": limit,
        },
        "complaints": complaints,
        "summary": {
            "total_matched_comments": len(filtered),
            "total_complaint_comments": len(complaint_comments),
            "returned": len(complaints),
        },
    }


def get_sentiment_trend(entity_name: str, time_range: Any = "30d") -> Dict[str, Any]:
    """
    情感趋势查询。

    Args:
        entity_name: 角色名。为空时查询全局趋势。
        time_range: 时间范围，支持 "7d" / "30d" / {"start": "2026-07-01", "end": "2026-07-30"}。

    Returns:
        给完整报告使用的时间序列情感数据。
    """
    start, end, days = _resolve_time_range(time_range)
    comments = _fetch_comments_from_agent_db(None, entity_name or None, days=max(days, 1), limit=5000)
    buckets: dict[str, Counter] = {}
    for comment in comments:
        parsed = _parse_date(comment.publish_date)
        if parsed is None:
            continue
        if parsed.date() < start.date() or parsed.date() > end.date():
            continue
        day = parsed.strftime("%Y-%m-%d")
        buckets.setdefault(day, Counter())
        buckets[day][comment.sentiment] += 1
        buckets[day]["toxic"] += int(comment.is_toxic or 0)
        buckets[day]["total"] += 1

    series = []
    cursor = start.date()
    while cursor <= end.date():
        key = cursor.strftime("%Y-%m-%d")
        counter = buckets.get(key, Counter())
        total = counter.get("total", 0)
        series.append(
            {
                "date": key,
                "positive": counter.get("positive", 0),
                "negative": counter.get("negative", 0),
                "neutral": counter.get("neutral", 0),
                "toxic": counter.get("toxic", 0),
                "total": total,
                "negative_ratio": _ratio(counter.get("negative", 0), total),
            }
        )
        cursor += timedelta(days=1)

    return {
        "tool_name": "get_sentiment_trend",
        "tool_version": "1.0.0",
        "status": "ok",
        "input": {"entity_name": entity_name, "time_range": time_range},
        "series": series,
        "summary": {
            "start_date": start.strftime("%Y-%m-%d"),
            "end_date": end.strftime("%Y-%m-%d"),
            "days": len(series),
            "total_comments": sum(item["total"] for item in series),
        },
    }


get_red_lines_tool = tool(get_red_lines)
get_top_complaints_tool = tool(get_top_complaints)
get_sentiment_trend_tool = tool(get_sentiment_trend)


def generate_sentiment_report(
    character_id: Optional[int] = None,
    character_name: Optional[str] = None,
    days: int = 30,
    limit: int = 200,
    include_llm_diagnosis: bool = False,
) -> Dict[str, Any]:
    """
    Generate a structured sentiment report for a character.

    Args:
        character_id: Character id in analysis_characters / analysis_results.
        character_name: Character name. Used when id is not available.
        days: Time window for source comments.
        limit: Max comments used for aggregation.
        include_llm_diagnosis: Whether to call diagnosis.generate_diagnosis.

    Returns:
        JSON-compatible report for dashboard, frontend, or Agent reasoning.
    """
    comments = _fetch_comments_from_agent_db(character_id, character_name, days, limit)
    if not comments:
        return _empty_report(character_id, character_name, days)

    sentiment_counts = Counter(comment.sentiment for comment in comments)
    tag_counts = Counter(comment.tag for comment in comments)
    source_counts = Counter(comment.source or "unknown" for comment in comments)
    toxic_count = sum(comment.is_toxic for comment in comments)
    total = len(comments)
    latest = _fetch_latest_analysis_result(character_id)

    dates = [_parse_date(comment.publish_date) for comment in comments]
    dates = [date for date in dates if date is not None]
    start_date = min(dates).strftime("%Y-%m-%d") if dates else None
    end_date = max(dates).strftime("%Y-%m-%d") if dates else None

    top_tags = [{"tag": tag, "count": count} for tag, count in tag_counts.most_common(8)]
    top_sources = [{"source": source, "count": count} for source, count in source_counts.most_common(5)]

    llm_result = None
    if include_llm_diagnosis and generate_diagnosis is not None:
        try:
            llm_result = generate_diagnosis(
                character_name or str(character_id or "未知角色"),
                _comments_to_raw_comments(comments),
            )
        except Exception as exc:
            llm_result = {"error": str(exc)}

    character_score = None
    gameplay_score = None
    system_pain_score = None
    risk_warnings = []
    word_cloud_data = []
    if latest:
        character_score = latest.get("character_score")
        gameplay_score = latest.get("gameplay_score")
        system_pain_score = latest.get("system_pain_score")
        risk_warnings = latest.get("risk_warnings") or []
        word_cloud_data = latest.get("word_cloud_data") or []
    if llm_result and "error" not in llm_result:
        character_score = llm_result.get("character_score", character_score)
        gameplay_score = llm_result.get("gameplay_score", gameplay_score)
        system_pain_score = llm_result.get("system_pain_score", system_pain_score)
        risk_warnings = llm_result.get("risk_warnings", risk_warnings)
        word_cloud_data = llm_result.get("word_cloud_data", word_cloud_data)

    report = {
        "tool_name": "generate_sentiment_report",
        "tool_version": "1.0.0",
        "status": "ok",
        "character": {
            "id": character_id,
            "name": character_name or (comments[0].character_name if (character_id is not None and comments) else "全部舆情"),
        },
        "period": {"days": days, "start_date": start_date, "end_date": end_date},
        "summary": {
            "total_comments": total,
            "sentiment_counts": {label: sentiment_counts.get(label, 0) for label in SENTIMENT_LABELS},
            "sentiment_ratio": {label: _ratio(sentiment_counts.get(label, 0), total) for label in SENTIMENT_LABELS},
            "toxic_count": toxic_count,
            "toxic_ratio": _ratio(toxic_count, total),
            "top_tags": top_tags,
            "top_sources": top_sources,
        },
        "scores": {
            "sentiment_health_score": _calculate_sentiment_health_score(sentiment_counts, toxic_count, total),
            "character_score": character_score,
            "gameplay_score": gameplay_score,
            "system_pain_score": system_pain_score,
        },
        "risk_warnings": risk_warnings,
        "word_cloud_data": word_cloud_data,
        "sample_comments": [
            {
                "raw_comment_id": comment.raw_comment_id,
                "source": comment.source,
                "content": comment.content[:160],
                "sentiment": comment.sentiment,
                "tag": comment.tag,
                "is_toxic": comment.is_toxic,
                "publish_date": comment.publish_date,
                "url": comment.url,
            }
            for comment in comments[:5]
        ],
        "latest_analysis_result": latest,
        "llm_diagnosis": llm_result,
        "recommendations": _build_recommendations(sentiment_counts, toxic_count, total, top_tags),
        "meta": {
            "source": "agent_db",
            "llm_diagnosis_used": bool(include_llm_diagnosis),
            "comment_limit": limit,
        },
    }
    return report



def _percent(value: Any) -> str:
    try:
        return f"{float(value) * 100:.1f}%"
    except Exception:
        return "0.0%"


def _score_text(value: Any) -> str:
    return "暂无" if value is None else str(value)


def format_sentiment_report_markdown(report: Dict[str, Any]) -> str:
    """Convert generate_sentiment_report JSON result into a readable Markdown report."""
    character = report.get("character", {}) or {}
    period = report.get("period", {}) or {}
    summary = report.get("summary", {}) or {}
    scores = report.get("scores", {}) or {}
    character_name = character.get("name") or "全部角色"
    character_id = character.get("id")
    sentiment_counts = summary.get("sentiment_counts", {}) or {}
    sentiment_ratio = summary.get("sentiment_ratio", {}) or {}
    top_tags = summary.get("top_tags", []) or []
    top_sources = summary.get("top_sources", []) or []
    risk_warnings = report.get("risk_warnings", []) or []
    word_cloud_data = report.get("word_cloud_data", []) or []
    sample_comments = report.get("sample_comments", []) or []
    recommendations = report.get("recommendations", []) or []

    lines = [
        f"# {character_name} 舆情报告",
        "",
        "## 角色信息",
        "",
        f"- 角色：{character_name}",
        f"- 角色 ID：{character_id if character_id is not None else '未指定'}",
        f"- 统计周期：最近 {period.get('days', '未知')} 天",
        f"- 数据范围：{period.get('start_date') or '暂无'} 至 {period.get('end_date') or '暂无'}",
        "",
        "## 总体概览",
        "",
        "| 指标 | 数值 |",
        "| --- | ---: |",
        f"| 评论总数 | {summary.get('total_comments', 0)} |",
        f"| 正面评论 | {sentiment_counts.get('positive', 0)}（{_percent(sentiment_ratio.get('positive', 0))}） |",
        f"| 负面评论 | {sentiment_counts.get('negative', 0)}（{_percent(sentiment_ratio.get('negative', 0))}） |",
        f"| 中性评论 | {sentiment_counts.get('neutral', 0)}（{_percent(sentiment_ratio.get('neutral', 0))}） |",
        f"| 攻击性评论 | {summary.get('toxic_count', 0)}（{_percent(summary.get('toxic_ratio', 0))}） |",
        "",
        "## 舆情评分",
        "",
        "| 评分项 | 分数 |",
        "| --- | ---: |",
        f"| 舆情健康度 | {_score_text(scores.get('sentiment_health_score'))} |",
        f"| 人设风评 | {_score_text(scores.get('character_score'))} |",
        f"| 玩法爽感 | {_score_text(scores.get('gameplay_score'))} |",
        f"| 系统避坑 | {_score_text(scores.get('system_pain_score'))} |",
        "",
        "## 高频槽点",
        "",
    ]

    if top_tags:
        lines.extend(["| 排名 | 标签 | 次数 |", "| ---: | --- | ---: |"])
        for idx, item in enumerate(top_tags, 1):
            lines.append(f"| {idx} | {item.get('tag', '未知')} | {item.get('count', 0)} |")
    else:
        lines.append("暂无高频槽点数据。")

    lines.extend(["", "## 评论来源", ""])
    if top_sources:
        lines.extend(["| 来源 | 数量 |", "| --- | ---: |"])
        for item in top_sources:
            lines.append(f"| {item.get('source', 'unknown')} | {item.get('count', 0)} |")
    else:
        lines.append("暂无来源数据。")

    lines.extend(["", "## 风险预警", ""])
    if risk_warnings:
        for idx, risk in enumerate(risk_warnings, 1):
            if isinstance(risk, dict):
                title = risk.get("title") or risk.get("risk") or f"风险 {idx}"
                level = risk.get("risk_level") or risk.get("level") or "unknown"
                desc = risk.get("description") or risk.get("detail") or ""
                lines.append(f"{idx}. **{title}**（{level}）：{desc}")
            else:
                lines.append(f"{idx}. {risk}")
    else:
        lines.append("暂无风险预警。")

    lines.extend(["", "## 词云关键词", ""])
    if word_cloud_data:
        lines.extend(["| 关键词 | 权重 | 情感 |", "| --- | ---: | --- |"])
        for item in word_cloud_data[:12]:
            if isinstance(item, dict):
                lines.append(f"| {item.get('word', '未知')} | {item.get('weight', 0)} | {item.get('sentiment', 'unknown')} |")
    else:
        lines.append("暂无词云数据。")

    lines.extend(["", "## 代表性评论", ""])
    if sample_comments:
        for idx, comment in enumerate(sample_comments, 1):
            content = str(comment.get("content", "")).replace("\n", " ").strip()
            if len(content) > 140:
                content = content[:140] + "..."
            url = str(comment.get("url") or "").strip()
            link_text = f"[点击查看原评论]({url})" if url else "暂无链接"
            lines.extend([
                f"### 评论 {idx}",
                "",
                f"- 来源：{comment.get('source') or 'unknown'}",
                f"- 情感：{comment.get('sentiment') or 'unknown'}",
                f"- 标签：{comment.get('tag') or '未知'}",
                f"- 攻击性：{'是' if comment.get('is_toxic') else '否'}",
                f"- 时间：{comment.get('publish_date') or '未知'}",
                f"- url：{link_text}",
                f"> {content or '无评论正文'}",
                "",
            ])
    else:
        lines.append("暂无代表性评论。")

    lines.extend(["", "## 建议", ""])
    if recommendations:
        for idx, item in enumerate(recommendations, 1):
            lines.append(f"{idx}. {item}")
    else:
        lines.append("暂无建议。")

    return "\n".join(lines).strip() + "\n"
@tool
def generate_sentiment_report_tool(
    character_id: Optional[int] = None,
    character_name: Optional[str] = None,
    days: int = 30,
    limit: int = 200,
    include_llm_diagnosis: bool = False,
) -> Dict[str, Any]:
    """
    生成角色舆情报告。

    用于 Agent 工作流中汇总某个角色的评论情感分布、攻击性比例、高频标签、
    最新舆情诊断结果、风险预警和复盘建议。
    """
    return generate_sentiment_report(
        character_id=character_id,
        character_name=character_name,
        days=days,
        limit=limit,
        include_llm_diagnosis=include_llm_diagnosis,
    )



def _fetch_top_characters(limit: int = 8) -> list[dict[str, Any]]:
    if get_agent_db_conn is None:
        return []
    conn = get_agent_db_conn()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT character_id, character_name, COUNT(*) AS comment_count
            FROM analysis_characters
            GROUP BY character_id, character_name
            ORDER BY comment_count DESC
            LIMIT ?
            """,
            (max(1, int(limit or 8)),),
        )
        rows = cursor.fetchall()
    except Exception:
        conn.close()
        return []
    conn.close()
    return [
        {"character_id": row[0], "character_name": row[1], "comment_count": row[2]}
        for row in rows
    ]


def format_character_grouped_markdown(days: int = 30, character_limit: int = 8, comment_limit: int = 50) -> str:
    """Build a compact Markdown report grouped by character."""
    characters = _fetch_top_characters(character_limit)
    lines = [
        "# 角色舆情分组报告",
        "",
        f"- 统计周期：最近 {days} 天",
        f"- 展示角色数：{len(characters)}",
        "",
    ]
    if not characters:
        lines.append("暂无角色关联数据。")
        return "\n".join(lines).strip() + "\n"

    for idx, character in enumerate(characters, 1):
        report = generate_sentiment_report(
            character_id=character.get("character_id"),
            character_name=character.get("character_name"),
            days=days,
            limit=comment_limit,
        )
        summary = report.get("summary", {}) or {}
        scores = report.get("scores", {}) or {}
        sentiment_counts = summary.get("sentiment_counts", {}) or {}
        sentiment_ratio = summary.get("sentiment_ratio", {}) or {}
        top_tags = summary.get("top_tags", []) or []
        recommendations = report.get("recommendations", []) or []
        top_tag_text = "、".join(f"{item.get('tag')}({item.get('count')})" for item in top_tags[:3]) or "暂无"

        lines.extend([
            f"## {idx}. {character.get('character_name') or '未知角色'}",
            "",
            f"- 角色 ID：{character.get('character_id')}",
            f"- 关联评论数：{character.get('comment_count')}",
            f"- 本次统计评论数：{summary.get('total_comments', 0)}",
            f"- 舆情健康度：{_score_text(scores.get('sentiment_health_score'))}",
            f"- 正面/负面/中性：{sentiment_counts.get('positive', 0)} / {sentiment_counts.get('negative', 0)} / {sentiment_counts.get('neutral', 0)}",
            f"- 负面占比：{_percent(sentiment_ratio.get('negative', 0))}",
            f"- 攻击性占比：{_percent(summary.get('toxic_ratio', 0))}",
            f"- 高频槽点：{top_tag_text}",
        ])
        if recommendations:
            lines.append("- 建议：")
            for rec_idx, recommendation in enumerate(recommendations[:4], 1):
                lines.append(f"  {rec_idx}. {recommendation}")
        else:
            lines.append("- 建议：暂无建议。")
        lines.append("")

    return "\n".join(lines).strip() + "\n"
def main() -> None:
    import argparse
    from pathlib import Path

    parser = argparse.ArgumentParser(description="Generate a character sentiment report.")
    parser.add_argument("--character-id", type=int, default=None)
    parser.add_argument("--character-name", default=None)
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--include-llm-diagnosis", action="store_true")
    parser.add_argument("--format", choices=["md", "json"], default="md", help="Output format. Default: md")
    parser.add_argument("--group-by-character", action="store_true", help="Output a compact Markdown report grouped by character")
    parser.add_argument("--character-limit", type=int, default=8, help="Max characters shown in grouped report")
    parser.add_argument("--output", default=None, help="Write output to a file with Windows-friendly UTF-8 encoding")
    args = parser.parse_args()

    if args.group_by_character:
        output_text = format_character_grouped_markdown(
            days=args.days,
            character_limit=args.character_limit,
            comment_limit=args.limit,
        )
    else:
        report = generate_sentiment_report(
            character_id=args.character_id,
            character_name=args.character_name,
            days=args.days,
            limit=args.limit,
            include_llm_diagnosis=args.include_llm_diagnosis,
        )
        if args.format == "json":
            output_text = json.dumps(report, ensure_ascii=False, indent=2)
        else:
            output_text = format_sentiment_report_markdown(report)

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(output_text, encoding="utf-8-sig")
        print(f"已生成文件：{output_path}")
    else:
        print(output_text)

if __name__ == "__main__":
    main()

















