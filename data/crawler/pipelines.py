"""
GamerPulse 数据处理 Pipeline（精简版）
流程：CSV 读取 → 物理消噪 → SQLite 入库
角色识别、维度分类、Tag 打标、情感分析等交给 AI（算法 D）处理，不在 pipeline 层完成
"""

import csv
import os
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Optional

from crawler.config import (
    NOISE_RULES,
    DATA_SOURCES,
)

# 数据库路径（项目根目录）
DATA_ROOT = Path(__file__).resolve().parents[1]
GAMEPULSE_ROOT = DATA_ROOT.parent
DB_PATH = Path(os.getenv("GAMERPULSE_RAW_DATA_DB", str(DATA_ROOT / "raw_data.db")))


# ==========================================
# 1. 物理消噪
# ==========================================

def clean_content(text: str) -> str:
    """物理消噪：去 HTML 标签、URL、纯表情、过短内容"""
    if not text:
        return ""
    
    # 去 HTML 标签
    if NOISE_RULES.get("filter_html_tags"):
        text = re.sub(r"<[^>]+>", "", text)
    
    # 去 URL
    if NOISE_RULES.get("filter_urls"):
        text = re.sub(r"https?://\S+", "", text)
    
    # 去纯表情（如 [笑哭]、[doge]）
    if NOISE_RULES.get("filter_pure_emoji"):
        text = re.sub(r"\[[\u4e00-\u9fa5a-zA-Z]+\]", "", text)
    
    # 去首尾空白
    text = text.strip()
    
    return text


def is_noise(text: str) -> bool:
    """判断是否为噪声（过短/无意义）"""
    min_len = NOISE_RULES.get("min_content_length", 3)
    return len(text) < min_len


# ==========================================
# 2. CSV 读取
# ==========================================

def read_csv(filepath: str, source: str) -> List[Dict]:
    """读取 CSV 文件，统一返回 [{content, source, publish_date}] 格式"""
    results = []
    # 将相对路径转为相对于项目根目录的绝对路径
    project_root = Path(__file__).parent.parent
    path = project_root / filepath
    
    if not path.exists():
        print(f"[WARN] 文件不存在: {filepath}")
        return results
    
    # taptap_reviews 系列 CSV 没有表头，需要特殊处理
    is_dom_csv = "taptap_reviews" in filepath
    
    with open(path, "r", encoding="utf-8-sig") as f:
        if is_dom_csv:
            # 无表头：user_name, rating, play_time, content, source_url
            # 字段索引: 0=用户名, 1=评分, 2=游玩时间, 3=内容, 4=链接
            for line in f:
                parts = line.strip().split(",", 4)
                if len(parts) >= 4:
                    content = parts[3]
                    url = parts[4] if len(parts) > 4 else ""
                    if content:
                        results.append({
                            "content": content,
                            "source": source,
                            "publish_date": datetime.now(timezone.utc).isoformat(),
                            "url": url,
                        })
        else:
            reader = csv.DictReader(f)
            for row in reader:
                content = ""
                if source == "NGA":
                    content = row.get("评论内容", "")
                elif source == "TapTap":
                    content = row.get("content", "")
                
                if content:
                    results.append({
                        "content": content,
                        "source": source,
                        "publish_date": datetime.now(timezone.utc).isoformat(),
                        "url": row.get("source_url", ""),
                    })
    
    return results


# ==========================================
# 3. Pipeline 主流程
# ==========================================

def _process_single_comment(comment: Dict) -> Optional[Dict]:
    """处理单条评论：物理消噪后返回，被过滤则返回 None"""
    raw_content = comment["content"]
    
    # 物理消噪
    cleaned = clean_content(raw_content)
    if is_noise(cleaned):
        return None
    
    return {
        "content": cleaned,
        "source": comment["source"],
        "publish_date": comment["publish_date"],
        "url": comment.get("url", ""),
    }


def run_pipeline() -> Dict:
    """
    执行 Pipeline：
    1. 读取所有 CSV 数据源
    2. 物理消噪
    3. 入库 SQLite（仅 source / content / publish_date）
    
    返回处理统计信息
    """
    stats = {
        "total_read": 0,
        "noise_filtered": 0,
        "inserted": 0,
    }
    
    # 1. 读取所有数据源
    all_comments = []
    for source, filepath in DATA_SOURCES.items():
        source_name = source.replace("_csv", "").upper()
        comments = read_csv(filepath, source_name)
        all_comments.extend(comments)
        print(f"[INFO] 读取 {source_name}: {len(comments)} 条")
    
    stats["total_read"] = len(all_comments)
    print(f"\n[INFO] 共读取 {len(all_comments)} 条原始评论\n")
    
    # 2. 物理消噪
    processed = []
    for comment in all_comments:
        result = _process_single_comment(comment)
        if result is None:
            stats["noise_filtered"] += 1
        else:
            processed.append(result)
    
    # 3. 入库
    stats["inserted"] = _insert_to_db(processed)
    
    # 4. 输出统计
    print("\n" + "=" * 50)
    print("Pipeline 处理完成")
    print("=" * 50)
    print(f"总读取:    {stats['total_read']}")
    print(f"噪声过滤:  {stats['noise_filtered']}")
    print(f"成功入库:  {stats['inserted']}")
    if stats['total_read'] > 0:
        print(f"入库率:    {stats['inserted']/stats['total_read']*100:.1f}%")
    print("=" * 50)
    
    return stats


def _insert_to_db(records: List[Dict]) -> int:
    """将清洗后的数据插入 raw_comments（仅 source / content / publish_date），返回插入条数"""
    if not records:
        return 0
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    inserted = 0
    for record in records:
        cursor.execute("""
            INSERT OR IGNORE INTO raw_comments (source, content, publish_date, url)
            VALUES (?, ?, ?, ?)
        """, (
            record["source"],
            record["content"],
            record["publish_date"],
            record.get("url", ""),
        ))
        inserted += 1
    
    conn.commit()
    
    # 统计实际写入数（OR IGNORE 可能跳过重复）
    actual = cursor.execute("SELECT COUNT(*) FROM raw_comments").fetchone()[0]
    conn.close()
    
    print(f"[INFO] 尝试插入 {inserted} 条，当前库中共 {actual} 条")
    return inserted


# ==========================================
# 入口
# ==========================================

if __name__ == "__main__":
    run_pipeline()

