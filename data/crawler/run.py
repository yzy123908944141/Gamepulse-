"""
一键爬取脚本 —— NGA + TapTap 评论采集
交互式输入参数，依次执行两个爬虫，爬完自动入库。

用法: python run.py
"""
import subprocess
import sys
import os
from pathlib import Path

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent
CRAWLER_DIR = Path(__file__).parent
NGA_SCRIPT = CRAWLER_DIR / "scrapers" / "nga.py"
TAPTAP_SCRIPT = CRAWLER_DIR / "scrapers" / "taptap.py"

# Python 解释器（优先用虚拟环境）
VENV_PYTHON = PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"
PYTHON = str(VENV_PYTHON) if VENV_PYTHON.exists() else sys.executable


def run_nga():
    """交互式收集 NGA 参数并执行爬虫"""
    print("\n" + "=" * 50)
    print("📡 NGA 论坛爬虫")
    print("=" * 50)
    print("输入格式: tid:count（多个用空格分隔）")
    print("示例: 47144463:300 12345678:100")
    print("直接回车跳过 NGA")

    while True:
        raw = input("\n请输入 NGA 爬取参数: ").strip()
        if not raw:
            print("⏭️ 跳过 NGA")
            return

        # 校验格式
        params = raw.split()
        valid = True
        for p in params:
            if ":" not in p:
                print(f"⚠️ 格式错误: {p}，应为 tid:count")
                valid = False
                break
            tid_str, count_str = p.rsplit(":", 1)
            if not tid_str.isdigit() or not count_str.isdigit():
                print(f"⚠️ 格式错误: {p}，tid 和 count 必须是数字")
                valid = False
                break

        if valid:
            break

    print(f"\n🚀 启动 NGA 爬虫: {raw}")
    cmd = [PYTHON, str(NGA_SCRIPT)] + params
    subprocess.run(cmd, cwd=str(CRAWLER_DIR))


def run_taptap():
    """交互式收集 TapTap 参数并执行爬虫"""
    print("\n" + "=" * 50)
    print("📡 TapTap 评论爬虫")
    print("=" * 50)
    print("输入格式: type:count（type 为 hot 或 new，多个用空格分隔）")
    print("示例: hot:300 new:100")
    print("直接回车跳过 TapTap")

    while True:
        raw = input("\n请输入 TapTap 爬取参数: ").strip()
        if not raw:
            print("⏭️ 跳过 TapTap")
            return

        params = raw.split()
        valid = True
        for p in params:
            if ":" not in p:
                print(f"⚠️ 格式错误: {p}，应为 type:count")
                valid = False
                break
            type_str, count_str = p.rsplit(":", 1)
            type_str = type_str.lower().strip()
            if type_str not in ("hot", "new"):
                print(f"⚠️ 未知类型: {type_str}，只支持 hot 或 new")
                valid = False
                break
            if not count_str.isdigit():
                print(f"⚠️ 格式错误: {p}，count 必须是数字")
                valid = False
                break

        if valid:
            break

    print(f"\n🚀 启动 TapTap 爬虫: {raw}")
    cmd = [PYTHON, str(TAPTAP_SCRIPT)] + params
    subprocess.run(cmd, cwd=str(CRAWLER_DIR))


def show_db_stats():
    """显示当前数据库 raw_comments 统计"""
    import sqlite3
    db_path = PROJECT_ROOT / "gamerpulse.db"
    if not db_path.exists():
        print("⚠️ 数据库不存在")
        return

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM raw_comments")
    total = cursor.fetchone()[0]

    cursor.execute("SELECT source, COUNT(*) FROM raw_comments GROUP BY source")
    by_source = cursor.fetchall()

    conn.close()

    print("\n" + "=" * 50)
    print("📊 数据库统计 (raw_comments)")
    print("=" * 50)
    print(f"总计: {total} 条")
    for source, count in by_source:
        print(f"  {source}: {count} 条")
    print("=" * 50)


if __name__ == "__main__":
    print("=" * 50)
    print("🎮 GamerPulse 一键评论爬取工具")
    print("=" * 50)

    # 先看看当前数据库状态
    show_db_stats()

    # 依次执行
    run_nga()
    run_taptap()

    # 爬完再看数据库
    print("\n✅ 全部爬取完成！")
    show_db_stats()

    input("\n按回车退出...")
