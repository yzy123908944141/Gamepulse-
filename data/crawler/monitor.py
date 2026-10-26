"""
monitor.py - 舆情热度检测模块

在每次爬取后运行，通过三重信号检测是否有舆情爆发：
1. 评论量异常 - 近期日均评论数 vs 历史均值
2. 关键词频率突增 - 高危关键词出现频率飙升
3. 情感骤变 - 负面占比突然上升（需analysis_results表）

检测到异常时建议切换到每日爬取模式。

使用方式：
    python monitor.py            # 运行检测
    python monitor.py --history   # 查看历史检测记录
"""

import sqlite3
import json
import os
from datetime import datetime, timedelta

# ============ 配置区 ============

# 数据库路径（脚本在 crawler/ 下，数据库在项目根目录）
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(PROJECT_ROOT, "gamerpulse.db")

# 高危关键词列表（负面情绪 / 技术故障 / 付费争议 / 社区节奏）
ALARM_KEYWORDS = [
    # 通用负面
    "退款", "垃圾", "恶心", "差评", "跑路", "摆烂", "不作为", "敷衍",
    # 技术问题
    "闪退", "卡顿", "掉帧", "发热", "bug", "BUG", "Bug", "优化差", "黑屏",
    # 付费争议
    "抽卡", "保底", "歪了", "氪金", "逼氪", "割韭菜", "骗钱",
    # 社区节奏
    "节奏", "封号", "误封", "运营", "策划",
]

# 检测阈值
VOLUME_SPIKE_RATIO = 2.0       # 评论量达均值N倍 → 异常
KEYWORD_SPIKE_RATIO = 3.0      # 关键词频率达均值N倍 → 异常
KEYWORD_MIN_ABSOLUTE = 5       # 关键词近期至少出现N次才算（过滤噪音）
SENTIMENT_NEG_THRESHOLD = 0.5  # 负面占比超过50% → 异常
SENTIMENT_SPIKE_RATIO = 1.5    # 负面占比为基线N倍 → 异常

# 时间窗口
RECENT_WINDOW_DAYS = 3         # 近期窗口（一个爬取周期）
BASELINE_WINDOW_DAYS = 30      # 基线窗口（历史对比范围）
HOT_MODE_DURATION_DAYS = 7     # 热点模式持续天数

# 检测记录文件
RECORD_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "opinion_monitor_record.json")


# ============ 数据库连接 ============

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# ============ 检测模块 ============

def check_volume_anomaly(conn):
    """信号1：评论量异常检测"""
    now = datetime.now()
    recent_start = (now - timedelta(days=RECENT_WINDOW_DAYS)).strftime("%Y-%m-%d %H:%M:%S")
    baseline_start = (now - timedelta(days=BASELINE_WINDOW_DAYS)).strftime("%Y-%m-%d %H:%M:%S")

    # 近期评论数
    recent_count = conn.execute(
        "SELECT COUNT(*) FROM raw_comments WHERE publish_date >= ?", (recent_start,)
    ).fetchone()[0]

    # 基线期评论数（排除近期窗口，避免重叠）
    baseline_count = conn.execute(
        "SELECT COUNT(*) FROM raw_comments WHERE publish_date >= ? AND publish_date < ?",
        (baseline_start, recent_start)
    ).fetchone()[0]

    baseline_days = BASELINE_WINDOW_DAYS - RECENT_WINDOW_DAYS
    if baseline_days <= 0 or baseline_count == 0:
        return {"triggered": False, "reason": "基线数据不足，无法比较", "recent_count": recent_count}

    recent_daily = recent_count / RECENT_WINDOW_DAYS
    baseline_daily = baseline_count / baseline_days
    ratio = recent_daily / baseline_daily if baseline_daily > 0 else 0
    triggered = ratio >= VOLUME_SPIKE_RATIO

    return {
        "triggered": triggered,
        "recent_count": recent_count,
        "recent_daily_avg": round(recent_daily, 1),
        "baseline_daily_avg": round(baseline_daily, 1),
        "ratio": round(ratio, 2),
        "message": f"近期日均 {recent_daily:.0f} 条 vs 基线日均 {baseline_daily:.0f} 条（{ratio:.2f}x）"
                   + (" ⚠️ 超阈值！" if triggered else " ✅"),
    }


def check_keyword_spike(conn):
    """信号2：高危关键词频率突增检测"""
    now = datetime.now()
    recent_start = (now - timedelta(days=RECENT_WINDOW_DAYS)).strftime("%Y-%m-%d %H:%M:%S")
    baseline_start = (now - timedelta(days=BASELINE_WINDOW_DAYS)).strftime("%Y-%m-%d %H:%M:%S")

    # 拉取评论内容
    recent_contents = [row[0] for row in conn.execute(
        "SELECT content FROM raw_comments WHERE publish_date >= ?", (recent_start,)
    ).fetchall()]

    baseline_contents = [row[0] for row in conn.execute(
        "SELECT content FROM raw_comments WHERE publish_date >= ? AND publish_date < ?",
        (baseline_start, recent_start)
    ).fetchall()]

    if not baseline_contents:
        return {"triggered": False, "reason": "基线数据不足，无法比较"}
    if not recent_contents:
        return {"triggered": False, "reason": "近期无评论数据"}

    # 统计每个关键词的归一化频率（每100条评论中出现次数）
    spiked = []
    for kw in ALARM_KEYWORDS:
        r_count = sum(1 for c in recent_contents if kw in c)
        b_count = sum(1 for c in baseline_contents if kw in c)

        # 归一化：频率 = 出现次数 / 评论总数 * 100
        r_freq = r_count / len(recent_contents) * 100
        b_freq = b_count / len(baseline_contents) * 100

        # 基线为0但近期频繁出现
        if b_freq == 0 and r_count >= KEYWORD_MIN_ABSOLUTE:
            spiked.append({"keyword": kw, "recent": r_count, "baseline": b_count, "ratio": "∞"})
        # 基线有数据，比较归一化频率
        elif b_freq > 0:
            ratio = r_freq / b_freq
            if ratio >= KEYWORD_SPIKE_RATIO and r_count >= KEYWORD_MIN_ABSOLUTE:
                spiked.append({"keyword": kw, "recent": r_count, "baseline": b_count, "ratio": round(ratio, 2)})

    return {
        "triggered": len(spiked) > 0,
        "spiked_keywords": spiked,
        "message": f"检测到 {len(spiked)} 个关键词突增 ⚠️" if spiked else "未检测到关键词突增 ✅",
    }


def check_sentiment_shift(conn):
    """信号3：情感骤变检测（需要 analysis_results 表）"""
    # 检查表是否存在
    table = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='analysis_results'"
    ).fetchone()

    if not table:
        return {"triggered": False, "available": False, "reason": "analysis_results 表不存在，跳过情感检测"}

    now = datetime.now()
    recent_start = (now - timedelta(days=RECENT_WINDOW_DAYS)).strftime("%Y-%m-%d %H:%M:%S")
    baseline_start = (now - timedelta(days=BASELINE_WINDOW_DAYS)).strftime("%Y-%m-%d %H:%M:%S")

    # 尝试多种常见的情感字段名
    # 不同团队可能用不同的字段名，这里做兼容
    sentiment_column = None
    for col_name in ["sentiment", "sentiment_label", "label", "emotion"]:
        cols = conn.execute("PRAGMA table_info(analysis_results)").fetchall()
        if any(col[1] == col_name for col in cols):
            sentiment_column = col_name
            break

    if not sentiment_column:
        return {"triggered": False, "available": False, "reason": "analysis_results 表中未找到情感字段，跳过"}

    # 时间字段也做兼容
    time_column = None
    for col_name in ["created_at", "analyze_time", "timestamp", "created_time"]:
        cols = conn.execute("PRAGMA table_info(analysis_results)").fetchall()
        if any(col[1] == col_name for col in cols):
            time_column = col_name
            break

    if not time_column:
        return {"triggered": False, "available": False, "reason": "analysis_results 表中未找到时间字段，跳过"}

    # 近期负面占比
    recent_total = conn.execute(
        f"SELECT COUNT(*) FROM analysis_results WHERE {time_column} >= ?", (recent_start,)
    ).fetchone()[0]
    recent_neg = conn.execute(
        f"SELECT COUNT(*) FROM analysis_results WHERE {time_column} >= ? AND {sentiment_column} LIKE '%negative%'",
        (recent_start,)
    ).fetchone()[0]

    # 基线负面占比
    baseline_total = conn.execute(
        f"SELECT COUNT(*) FROM analysis_results WHERE {time_column} >= ? AND {time_column} < ?",
        (baseline_start, recent_start)
    ).fetchone()[0]
    baseline_neg = conn.execute(
        f"SELECT COUNT(*) FROM analysis_results WHERE {time_column} >= ? AND {time_column} < ? AND {sentiment_column} LIKE '%negative%'",
        (baseline_start, recent_start)
    ).fetchone()[0]

    if recent_total == 0:
        return {"triggered": False, "available": True, "reason": "近期无分析数据"}
    if baseline_total == 0:
        return {"triggered": False, "available": True, "reason": "基线无分析数据"}

    r_neg_ratio = recent_neg / recent_total
    b_neg_ratio = baseline_neg / baseline_total

    # 触发条件：负面占比超50% 且 为基线的1.5倍以上
    triggered = r_neg_ratio >= SENTIMENT_NEG_THRESHOLD and r_neg_ratio >= b_neg_ratio * SENTIMENT_SPIKE_RATIO

    return {
        "triggered": triggered,
        "available": True,
        "recent_neg_ratio": round(r_neg_ratio, 2),
        "baseline_neg_ratio": round(b_neg_ratio, 2),
        "message": f"近期负面 {r_neg_ratio:.0%} vs 基线 {b_neg_ratio:.0%}"
                   + (" ⚠️ 负面骤增！" if triggered else " ✅"),
    }


# ============ 记录管理 ============

def load_record():
    """加载历史检测记录"""
    if os.path.exists(RECORD_FILE):
        try:
            with open(RECORD_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {"last_check": None, "hot_mode_until": None, "history": []}


def save_record(record):
    """保存检测记录"""
    with open(RECORD_FILE, "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2)


# ============ 主函数 ============

def detect_hot_opinion():
    """运行全部检测，输出舆情状态判断"""
    if not os.path.exists(DB_PATH):
        print(f"❌ 数据库不存在: {DB_PATH}")
        return

    conn = get_connection()

    # 检查数据量
    total = conn.execute("SELECT COUNT(*) FROM raw_comments").fetchone()[0]
    if total == 0:
        print("⚠️ 数据库中无评论数据，请先运行爬虫。")
        conn.close()
        return

    print()
    print("📊 GamerPulse 舆情热度检测")
    print("=" * 55)
    print(f"  数据库评论总数: {total}")
    print(f"  检测窗口: 近 {RECENT_WINDOW_DAYS} 天 vs 基线 {BASELINE_WINDOW_DAYS} 天")
    print(f"  数据库: {DB_PATH}")
    print("=" * 55)
    print()

    # ---- 信号1：评论量 ----
    print("【1/3】评论量异常检测")
    vol = check_volume_anomaly(conn)
    print(f"  → {vol['message']}")
    print()

    # ---- 信号2：关键词 ----
    print("【2/3】关键词频率突增检测")
    kw = check_keyword_spike(conn)
    print(f"  → {kw['message']}")
    if kw.get("spiked_keywords"):
        print(f"  突增关键词:")
        for sk in kw["spiked_keywords"]:
            print(f"    · 「{sk['keyword']}」 近期 {sk['recent']} 次 / 基线 {sk['baseline']} 次（{sk['ratio']}x）")
    print()

    # ---- 信号3：情感 ----
    print("【3/3】情感骤变检测")
    sent = check_sentiment_shift(conn)
    if not sent.get("available"):
        print(f"  → {sent.get('reason', '跳过')}")
    else:
        print(f"  → {sent['message']}")
    print()

    conn.close()

    # ---- 综合判断 ----
    signals = [vol, kw, sent]
    triggered_count = sum(1 for s in signals if s.get("triggered", False))

    record = load_record()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 判断是否还在热点模式期内
    in_hot_mode = False
    if record.get("hot_mode_until"):
        try:
            hot_until = datetime.strptime(record["hot_mode_until"], "%Y-%m-%d %H:%M:%S")
            if datetime.now() < hot_until:
                in_hot_mode = True
        except ValueError:
            pass

    if triggered_count >= 1:
        status = "🔥 舆情爆发"
        recommendation = f"建议切换到每日爬取，持续 {HOT_MODE_DURATION_DAYS} 天后复检"
        record["hot_mode_until"] = (
            datetime.now() + timedelta(days=HOT_MODE_DURATION_DAYS)
        ).strftime("%Y-%m-%d %H:%M:%S")
    elif in_hot_mode:
        remaining_days = (hot_until - datetime.now()).days
        status = f"🔥 热点模式中（剩余 {remaining_days} 天）"
        recommendation = "维持每日爬取，热点模式结束后复检"
    else:
        status = "✅ 正常"
        recommendation = "维持 3 天/次常规爬取"
        record["hot_mode_until"] = None

    # 保存记录
    record["last_check"] = now_str
    record["history"].append({
        "time": now_str,
        "status": status,
        "triggered_signals": triggered_count,
        "total_comments": total,
    })
    # 只保留最近 30 条
    if len(record["history"]) > 30:
        record["history"] = record["history"][-30:]
    save_record(record)

    # 输出结果
    print("=" * 55)
    print(f"  检测结果: {status}")
    print(f"  触发信号: {triggered_count} / 3")
    print(f"  建议: {recommendation}")
    print("=" * 55)
    print()

    return {
        "status": status,
        "triggered_count": triggered_count,
        "recommendation": recommendation,
        "details": {"volume": vol, "keyword": kw, "sentiment": sent},
    }


def show_history():
    """显示历史检测记录"""
    record = load_record()
    if not record["history"]:
        print("暂无历史检测记录")
        return

    print()
    print(f"📋 舆情检测历史记录（共 {len(record['history'])} 条）")
    print("-" * 60)
    for entry in record["history"]:
        print(f"  {entry['time']}  |  {entry['status']}  |  信号:{entry['triggered_signals']}/3  |  总评论:{entry.get('total_comments', '?')}")
    print("-" * 60)
    print(f"  上次检测: {record['last_check']}")
    if record.get("hot_mode_until"):
        print(f"  热点模式到期: {record['hot_mode_until']}")
    print()


# ============ 入口 ============

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--history":
        show_history()
    else:
        detect_hot_opinion()
