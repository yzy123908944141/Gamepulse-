#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
GamerPulse 每日自动爬取脚本
==========================

由 Windows 任务计划定时调用，执行流程：
  1. 运行 monitor.py 检测舆情热度
  2. 根据检测结果 + 上次爬取时间，判断今天是否需要爬取
  3. 如需爬取，运行 run.py 抓取评论并入库
  4. 记录日志到 crawler/auto_crawl.log

爬取频率（自适应）：
  - 热点期间: 每 1 天爬取一次（信号触发后持续 7 天）
  - 常态运行: 每 3 天爬取一次
  - 冷清期间: 每 7 天爬取一次
"""

import os
import sys
import json
import subprocess
import logging
from pathlib import Path
from datetime import datetime

# ============================================================
# 路径配置
# ============================================================
PROJECT_ROOT = Path(__file__).parent.parent
CRAWLER_DIR = PROJECT_ROOT / "crawler"

OPINION_MONITOR = CRAWLER_DIR / "monitor.py"
RUN_SCRAPERS = CRAWLER_DIR / "run.py"
RECORD_FILE = CRAWLER_DIR / "opinion_monitor_record.json"
CRAWL_LOG = CRAWLER_DIR / "auto_crawl_log.json"
LOG_FILE = CRAWLER_DIR / "auto_crawl.log"

# Python 解释器（优先用 venv）
VENV_PYTHON = PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"
PYTHON = str(VENV_PYTHON) if VENV_PYTHON.exists() else sys.executable

# 爬取间隔（天）
INTERVAL_HOT = 1       # 热点期间：每天爬
INTERVAL_NORMAL = 3    # 常态：3天一次
INTERVAL_COLD = 7      # 冷清期：7天一次

# ============================================================
# 日志配置
# ============================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("GamerPulse")


def run_script(script_path):
    """运行 Python 脚本，返回是否成功"""
    logger.info(f"执行脚本: {script_path.name}")
    try:
        result = subprocess.run(
            [PYTHON, str(script_path)],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace"
        )
        if result.returncode == 0:
            logger.info(f"完成: {script_path.name}")
            if result.stdout:
                # 只记录前500字符，避免日志过长
                logger.info(f"输出摘要: {result.stdout[:500]}")
            return True
        else:
            logger.error(f"失败: {script_path.name}")
            if result.stderr:
                logger.error(f"错误信息: {result.stderr[:500]}")
            return False
    except Exception as e:
        logger.error(f"执行异常: {e}")
        return False


def read_monitor_record():
    """读取舆情监测记录"""
    if not RECORD_FILE.exists():
        logger.info("未找到监测记录文件，视为首次运行")
        return None

    try:
        with open(RECORD_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"读取监测记录失败: {e}")
        return None


def read_crawl_log():
    """读取爬取日志"""
    if not CRAWL_LOG.exists():
        return {"last_crawl_date": None, "crawl_history": []}

    try:
        with open(CRAWL_LOG, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {"last_crawl_date": None, "crawl_history": []}


def write_crawl_log(log_data):
    """写入爬取日志"""
    try:
        with open(CRAWL_LOG, "w", encoding="utf-8") as f:
            json.dump(log_data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"写入爬取日志失败: {e}")


def check_hot_signals(record):
    """
    检查是否有活跃的舆情热点信号。
    兼容 opinion_monitor_record.json 的不同结构。
    """
    if record is None:
        return False

    try:
        # 结构1: 顶层有 current_mode 字段
        if "current_mode" in record:
            return record["current_mode"] == "hot"

        # 结构2: 顶层有 is_hot 字段
        if "is_hot" in record:
            return bool(record["is_hot"])

        # 结构3: 有 records 列表，取最新一条
        if "records" in record and record["records"]:
            latest = record["records"][-1]
            if "is_hot" in latest:
                return bool(latest["is_hot"])
            if "signals" in latest:
                return any(latest["signals"].values())
            if "mode" in latest:
                return latest["mode"] == "hot"

        # 结构4: 有 latest_signals 字段
        if "latest_signals" in record:
            return any(record["latest_signals"].values())

    except Exception:
        pass

    return False


def should_crawl(record, crawl_log):
    """
    判断今天是否需要爬取。
    
    返回: (是否爬取, 当前模式, 间隔天数)
    """
    today = datetime.now().date()
    last_crawl_str = crawl_log.get("last_crawl_date")

    # 首次运行，直接爬取
    if last_crawl_str is None:
        logger.info("首次运行，执行爬取")
        return True, "首次", 0

    try:
        last_date = datetime.strptime(last_crawl_str, "%Y-%m-%d").date()
    except:
        logger.info("上次爬取日期格式异常，执行爬取")
        return True, "异常", 0

    days_since = (today - last_date).days

    # 检查舆情热度
    is_hot = check_hot_signals(record)

    if is_hot:
        mode = "热点"
        interval = INTERVAL_HOT
    else:
        mode = "常态"
        interval = INTERVAL_NORMAL

    logger.info(
        f"当前模式: {mode} | 上次爬取: {last_crawl_str} | "
        f"距今 {days_since} 天 | 需间隔 {interval} 天"
    )

    if days_since >= interval:
        logger.info(f"达到爬取间隔，执行爬取")
        return True, mode, interval
    else:
        logger.info(f"未达到爬取间隔，跳过今日爬取")
        return False, mode, interval


def main():
    logger.info("=" * 50)
    logger.info("GamerPulse 每日自动爬取启动")
    logger.info(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 50)

    # ---- 步骤1: 运行舆情监测 ----
    logger.info("")
    logger.info(">>> 步骤1: 运行舆情监测 (monitor.py)")
    monitor_ok = run_script(OPINION_MONITOR)
    if not monitor_ok:
        logger.warning("舆情监测执行失败，将继续判断是否爬取")

    # ---- 步骤2: 读取监测结果 ----
    logger.info("")
    logger.info(">>> 步骤2: 读取舆情监测结果")
    record = read_monitor_record()

    # ---- 步骤3: 判断是否需要爬取 ----
    logger.info("")
    logger.info(">>> 步骤3: 判断是否需要爬取")
    crawl_log = read_crawl_log()
    need_crawl, mode, interval = should_crawl(record, crawl_log)

    # ---- 步骤4: 执行爬取 ----
    logger.info("")
    if need_crawl:
        logger.info(f">>> 步骤4: 执行爬取 (run.py) [模式: {mode}]")
        crawl_ok = run_script(RUN_SCRAPERS)

        # 更新爬取日志
        crawl_log["last_crawl_date"] = datetime.now().strftime("%Y-%m-%d")
        crawl_log["crawl_history"].append({
            "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "mode": mode,
            "status": "success" if crawl_ok else "failed"
        })
        # 只保留最近 30 条记录
        crawl_log["crawl_history"] = crawl_log["crawl_history"][-30:]
        write_crawl_log(crawl_log)

        if crawl_ok:
            logger.info("爬取完成，数据已入库")
        else:
            logger.error("爬取失败，请检查日志")
    else:
        logger.info(f">>> 步骤4: 跳过爬取 [模式: {mode}, 还需等待 {interval} 天]")

    # ---- 结束 ----
    logger.info("")
    logger.info("=" * 50)
    logger.info("GamerPulse 每日自动爬取结束")
    logger.info("=" * 50)


if __name__ == "__main__":
    main()
