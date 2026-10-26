#!/usr/bin/env python3
"""
Extract story-related risk warnings from agent.db.analysis_results and summarize them with an LLM.

New behavior:
- read every risk_warnings item from analysis_results
- use title to decide whether it is strongly related to plot/story/character writing
- for selected items, read description and summarize into actionable risks
- write JSON/CSV outputs, never overwrite analysis_results

Environment variables:
- LLM_API_KEY or OPENAI_API_KEY: required for --run-api
- LLM_BASE_URL or OPENAI_BASE_URL: default https://api.deepseek.com
- LLM_MODEL or OPENAI_MODEL: default deepseek-chat
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sqlite3
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

DEFAULT_DB = Path(r"D:\program\two-dimensional_game\agent.db")
DEFAULT_OUT = Path(r"D:\program\two-dimensional_game\record\story_risk_summary")

SYSTEM_PROMPT = """你是游戏剧情舆情分析助手。你的任务不是标题去重，而是从已经预筛过的候选风险中再次筛选并总结“剧情强相关风险”。

处理规则：
1. 先只根据 title 判断该风险是否与剧情、角色塑造、角色关系、文案、叙事节奏、主线/支线、设定冲突、角色崩坏、玩家代入强相关。
2. 必须排除：抽卡、卡池、保底、付费、资源、福利、材料、养成、数值、强度、战斗平衡、性能优化、设备适配、卡顿、闪退、发热、活动奖励、登录、BUG、UI、操作手感、美术建模。ML/XP/角色受众预期属于角色关系与叙事接受风险，不要排除。
3. 只有 title 本身明确指向剧情、角色塑造、角色关系、台词文案、叙事节奏、设定冲突、角色崩坏、玩家代入时，才读取 description 并总结成“需注意的风险”。
4. 输出应面向游戏策划/文案评审使用，语言简洁、可落地。
5. 输出严格 JSON，不要 Markdown，不要额外解释。

JSON schema:
{
  "selected_risks": [
    {
      "analysis_id": 1,
      "character_id": 1,
      "title": "原始标题",
      "story_relevance": "high|medium",
      "risk_summary": "需注意的风险概括",
      "evidence": "从 description 中提炼的依据"
    }
  ],
  "overall_summary": ["跨角色/跨样本共性的剧情风险"],
  "ignored_count": 0
}
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Select story-related risk warnings and summarize them with an LLM.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="Path to agent.db")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="Output directory")
    parser.add_argument("--run-api", action="store_true", help="Call the configured LLM API")
    parser.add_argument("--allow-garbled", action="store_true", help="Run even if titles/descriptions look garbled")
    parser.add_argument("--max-items", type=int, default=0, help="Limit warning items for testing; 0 means all")
    parser.add_argument("--chunk-size", type=int, default=45, help="Items per LLM request")
    parser.add_argument("--write-db", action="store_true", help="Also create/update story_risk_summary table")
    return parser.parse_args()


def load_warning_items(db_path: Path) -> list[dict[str, Any]]:
    if not db_path.exists():
        raise FileNotFoundError(f"Database not found: {db_path}")

    items: list[dict[str, Any]] = []
    con = sqlite3.connect(db_path)
    try:
        con.row_factory = sqlite3.Row
        rows = con.execute(
            "select id, character_id, risk_warnings from analysis_results order by id"
        ).fetchall()
        for row in rows:
            raw = row["risk_warnings"] or "[]"
            try:
                warnings = json.loads(raw)
            except json.JSONDecodeError:
                continue

            if not isinstance(warnings, list):
                continue

            for index, warning in enumerate(warnings):
                if not isinstance(warning, dict):
                    continue
                title = str(warning.get("title") or "").strip()
                description = str(warning.get("description") or warning.get("desc") or "").strip()
                if not title:
                    continue
                items.append({
                    "item_id": f"{row['id']}-{index}",
                    "analysis_id": row["id"],
                    "character_id": row["character_id"],
                    "risk_level": warning.get("risk_level") or warning.get("level") or "",
                    "title": title,
                    "description": description,
                })
    finally:
        con.close()
    return items


def garbled_score(text: str) -> float:
    if not text:
        return 0.0
    length = max(len(text), 1)
    replacement = text.count("�")
    cjk = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
    if replacement >= 2:
        return 1.0
    if cjk / length < 0.15 and length >= 8:
        return 0.8
    return replacement / length


STORY_STRONG_INCLUDE_KEYWORDS = (
    "剧情", "叙事", "主线", "支线", "文案", "台词", "人设", "角色塑造", "角色关系",
    "角色线", "感情线", "情感线", "情感铺垫", "人物弧光", "角色弧光", "成长线",
    "代入", "设定冲突", "剧情逻辑", "叙事逻辑", "剧情节奏", "叙事节奏", "铺垫",
    "反派塑造", "主角塑造", "漂泊者", "OOC", "崩坏", "背刺", "动机", "剧情演出",
    "ML", "XP", "媚", "角色厨", "角色受众", "同质化",
)

ROLE_CONTEXT_KEYWORDS = (
    "塑造", "人设", "关系", "成长", "弧光", "动机", "感情", "情感", "代入", "台词", "剧情",
    "ML", "XP", "媚", "厨", "受众", "同质化",
)

NON_STORY_EXCLUDE_KEYWORDS = (
    "抽卡", "卡池", "保底", "氪", "付费", "充值", "资源", "福利", "材料", "养成",
    "数值", "强度", "膨胀", "战斗", "配队", "技能", "机制", "手感", "操作",
    "性能", "优化", "设备", "手机", "PC", "卡顿", "闪退", "发热", "帧率", "内存", "黑屏",
    "活动", "奖励", "登录", "BUG", "bug", "UI", "界面", "地图", "探索", "副本", "BOSS",
    "社区环境", "男女", "美术", "建模", "皮肤",
)

STORY_OVERRIDE_KEYWORDS = (
    "剧情", "叙事", "文案", "台词", "人设", "角色塑造", "角色关系", "设定冲突",
    "角色崩坏", "OOC", "主线", "支线", "铺垫", "代入", "情感线", "感情线", "反派塑造",
)


def classify_story_candidate(item: dict[str, Any]) -> tuple[bool, str]:
    title = str(item.get("title") or "")
    strong_hits = [word for word in STORY_STRONG_INCLUDE_KEYWORDS if word in title]
    role_context_hits = [word for word in ROLE_CONTEXT_KEYWORDS if word in title]
    exclude_hits = [word for word in NON_STORY_EXCLUDE_KEYWORDS if word in title]
    override_hits = [word for word in STORY_OVERRIDE_KEYWORDS if word in title]

    has_role_context = "角色" in title and bool(role_context_hits)
    if not strong_hits and not has_role_context:
        return False, "标题未明确命中剧情/文案/角色塑造相关语义"
    if exclude_hits and not override_hits:
        return False, "标题命中非剧情排除关键词：" + "、".join(exclude_hits[:4])

    hits = override_hits or strong_hits or role_context_hits
    return True, "标题命中剧情相关关键词：" + "、".join(hits[:4])


def prefilter_story_items(items: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    selected: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for item in items:
        keep, reason = classify_story_candidate(item)
        copied = dict(item)
        copied["prefilter_reason"] = reason
        if keep:
            selected.append(copied)
        else:
            rejected.append(copied)
    return selected, rejected
def build_report(items: list[dict[str, Any]], candidate_items: list[dict[str, Any]] | None = None, rejected_items: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    garbled = [item for item in items if garbled_score(item["title"] + item.get("description", "")) >= 0.25]
    candidate_items = candidate_items or []
    rejected_items = rejected_items or []
    return {
        "total_warning_items": len(items),
        "story_candidate_count": len(candidate_items),
        "prefilter_rejected_count": len(rejected_items),
        "unique_title_count": len({item["title"] for item in items}),
        "garbled_item_count": len(garbled),
        "garbled_ratio": round(len(garbled) / max(len(items), 1), 4),
        "candidate_sample_titles": [item["title"] for item in candidate_items[:20]],
        "rejected_sample_titles": [item["title"] for item in rejected_items[:20]],
        "garbled_examples": [item["title"] for item in garbled[:10]],
    }


def call_chat_completion(messages: list[dict[str, str]]) -> dict[str, Any]:
    api_key = os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("Missing LLM_API_KEY or OPENAI_API_KEY")

    base_url = (os.getenv("LLM_BASE_URL") or os.getenv("OPENAI_BASE_URL") or "https://api.deepseek.com").rstrip("/")
    model = os.getenv("LLM_MODEL") or os.getenv("OPENAI_MODEL") or "deepseek-chat"
    endpoint = f"{base_url}/chat/completions"

    payload = {
        "model": model,
        "temperature": 0.1,
        "response_format": {"type": "json_object"},
        "messages": messages,
    }

    request = urllib.request.Request(
        endpoint,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json; charset=utf-8",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"LLM API HTTP {exc.code}: {detail}") from exc

    content = body["choices"][0]["message"]["content"]
    return json.loads(content)


def analyze_chunk(items: list[dict[str, Any]]) -> dict[str, Any]:
    compact_items = [
        {
            "item_id": item["item_id"],
            "analysis_id": item["analysis_id"],
            "character_id": item["character_id"],
            "risk_level": item.get("risk_level", ""),
            "title": item["title"],
            "description": item.get("description", ""),
        }
        for item in items
    ]
    return call_chat_completion([
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps({"risk_warnings": compact_items}, ensure_ascii=False)},
    ])


def merge_results(partial_results: list[dict[str, Any]]) -> dict[str, Any]:
    selected: list[dict[str, Any]] = []
    overall: list[str] = []
    ignored_count = 0
    seen = set()

    for result in partial_results:
        ignored_count += int(result.get("ignored_count") or 0)
        for risk in result.get("selected_risks", []):
            key = (risk.get("analysis_id"), risk.get("character_id"), risk.get("title"))
            if key in seen:
                continue
            seen.add(key)
            selected.append(risk)
        overall.extend(str(item) for item in result.get("overall_summary", []) if item)

    if not overall:
        return {"selected_risks": selected, "overall_summary": [], "ignored_count": ignored_count}

    # Keep the first-pass summaries if there is only one chunk; otherwise ask the model
    # to consolidate cross-chunk themes without changing selected risk rows.
    if len(partial_results) == 1:
        return {"selected_risks": selected, "overall_summary": overall, "ignored_count": ignored_count}

    try:
        final = call_chat_completion([
            {"role": "system", "content": "你是游戏剧情风险分析助手。请把多批次 overall_summary 合并成不超过 8 条共性剧情风险。输出严格 JSON：{\"overall_summary\":[\"...\"]}"},
            {"role": "user", "content": json.dumps({"summaries": overall}, ensure_ascii=False)},
        ])
        overall = final.get("overall_summary", overall[:8])
    except Exception:
        overall = overall[:8]

    return {"selected_risks": selected, "overall_summary": overall, "ignored_count": ignored_count}


def run_llm(items: list[dict[str, Any]], chunk_size: int) -> dict[str, Any]:
    partial_results = []
    for start in range(0, len(items), chunk_size):
        partial_results.append(analyze_chunk(items[start:start + chunk_size]))
    return merge_results(partial_results)


def write_outputs(out_dir: Path, items: list[dict[str, Any]], report: dict[str, Any], result: dict[str, Any] | None, rejected_items: list[dict[str, Any]] | None = None) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    paths: dict[str, str] = {}

    extracted_json = out_dir / f"story_risk_items_{timestamp}.json"
    extracted_json.write_text(json.dumps({"items": items}, ensure_ascii=False, indent=2), encoding="utf-8")
    paths["items_json"] = str(extracted_json)

    report_json = out_dir / f"story_risk_report_{timestamp}.json"
    report_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    paths["report_json"] = str(report_json)

    items_csv = out_dir / f"story_risk_items_{timestamp}.csv"
    with items_csv.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=["item_id", "analysis_id", "character_id", "risk_level", "title", "description", "prefilter_reason"])
        writer.writeheader()
        writer.writerows(items)
    paths["items_csv"] = str(items_csv)

    rejected_items = rejected_items or []
    rejected_csv = out_dir / f"story_risk_rejected_{timestamp}.csv"
    with rejected_csv.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=["item_id", "analysis_id", "character_id", "risk_level", "title", "prefilter_reason"])
        writer.writeheader()
        for item in rejected_items:
            writer.writerow({
                "item_id": item.get("item_id", ""),
                "analysis_id": item.get("analysis_id", ""),
                "character_id": item.get("character_id", ""),
                "risk_level": item.get("risk_level", ""),
                "title": item.get("title", ""),
                "prefilter_reason": item.get("prefilter_reason", ""),
            })
    paths["rejected_csv"] = str(rejected_csv)

    if result is not None:
        summary_json = out_dir / f"story_risk_summary_{timestamp}.json"
        summary_json.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        paths["summary_json"] = str(summary_json)

        summary_csv = out_dir / f"story_risk_summary_{timestamp}.csv"
        with summary_csv.open("w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=["analysis_id", "character_id", "title", "story_relevance", "risk_summary", "evidence"])
            writer.writeheader()
            for item in result.get("selected_risks", []):
                writer.writerow({
                    "analysis_id": item.get("analysis_id", ""),
                    "character_id": item.get("character_id", ""),
                    "title": item.get("title", ""),
                    "story_relevance": item.get("story_relevance", ""),
                    "risk_summary": item.get("risk_summary", ""),
                    "evidence": item.get("evidence", ""),
                })
        paths["summary_csv"] = str(summary_csv)

    return paths


def write_db(db_path: Path, result: dict[str, Any]) -> None:
    con = sqlite3.connect(db_path)
    try:
        con.execute("""
            create table if not exists story_risk_summary (
                id integer primary key autoincrement,
                analysis_id integer,
                character_id integer,
                title text not null,
                story_relevance text,
                risk_summary text not null,
                evidence text,
                created_at timestamp default current_timestamp
            )
        """)
        con.execute("delete from story_risk_summary")
        for item in result.get("selected_risks", []):
            con.execute(
                """
                insert into story_risk_summary
                    (analysis_id, character_id, title, story_relevance, risk_summary, evidence)
                values (?, ?, ?, ?, ?, ?)
                """,
                (
                    item.get("analysis_id"),
                    item.get("character_id"),
                    item.get("title", ""),
                    item.get("story_relevance", ""),
                    item.get("risk_summary", ""),
                    item.get("evidence", ""),
                ),
            )
        con.commit()
    finally:
        con.close()


def main() -> int:
    args = parse_args()
    items = load_warning_items(args.db)
    if args.max_items > 0:
        items = items[: args.max_items]

    candidate_items, rejected_items = prefilter_story_items(items)
    report = build_report(items, candidate_items, rejected_items)
    result = None

    if report["garbled_ratio"] >= 0.25 and not args.allow_garbled:
        paths = write_outputs(args.out, candidate_items, report, None, rejected_items)
        print("Stopped: risk warning text looks garbled. Fix encoding/source data before LLM analysis.")
        print(json.dumps({"report": report, "outputs": paths}, ensure_ascii=False, indent=2))
        return 2

    if args.run_api:
        result = run_llm(candidate_items, max(args.chunk_size, 1))
        if args.write_db:
            write_db(args.db, result)

    paths = write_outputs(args.out, candidate_items, report, result, rejected_items)
    print(json.dumps({
        "report": report,
        "selected_risks": len(result.get("selected_risks", [])) if result else 0,
        "outputs": paths,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())





