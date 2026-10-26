#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
GamerPulse 定期爬取一键部署脚本
================================

使用方法：
  python schedule.py              # 部署（默认每天10:00运行）
  python schedule.py --time 14:00 # 部署（指定每天14:00运行）
  python schedule.py --uninstall  # 卸载定时任务

部署后效果：
  - 每天指定时间自动运行舆情监测
  - 根据舆情热度自动决定是否爬取评论
  - 热点期间每天爬取，常态3天一次，冷清期7天一次
  - 自动记录日志到 crawler/auto_crawl.log
"""

import os
import sys
import subprocess
from pathlib import Path

# ============================================================
# 路径配置
# ============================================================
PROJECT_ROOT = Path(__file__).parent.parent
CRAWLER_DIR = PROJECT_ROOT / "crawler"
AUTO_CRAWL_PY = CRAWLER_DIR / "auto_crawl.py"
AUTO_CRAWL_BAT = CRAWLER_DIR / "auto_crawl.bat"

VENV_PYTHON = PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"
TASK_NAME = "GamerPulse_AutoCrawl"


def find_python():
    """找到可用的 Python 解释器"""
    if VENV_PYTHON.exists():
        return str(VENV_PYTHON)
    return sys.executable


def check_prerequisites():
    """检查项目完整性"""
    checks = []

    env_file = PROJECT_ROOT / ".env"
    if env_file.exists():
        checks.append(("OK", ".env 配置文件"))
    else:
        checks.append(("WARN", ".env 配置文件", "未找到，爬虫可能无法运行（需要 DeepSeek API Key）"))

    monitor = CRAWLER_DIR / "monitor.py"
    checks.append(("OK" if monitor.exists() else "FAIL", "monitor.py 舆情监测模块"))

    scrapers = CRAWLER_DIR / "run.py"
    checks.append(("OK" if scrapers.exists() else "FAIL", "run.py 一键爬取脚本"))

    return checks


def generate_bat(python_path):
    """生成 auto_crawl.bat 启动脚本"""
    bat_content = f'''@echo off
chcp 65001 >nul 2>&1
cd /d "{PROJECT_ROOT}"
"{python_path}" "{AUTO_CRAWL_PY}"
'''
    AUTO_CRAWL_BAT.write_text(bat_content, encoding="utf-8")
    return AUTO_CRAWL_BAT


def create_task(bat_path, run_time):
    """创建 Windows 任务计划"""
    # 先删除旧任务（如果存在）
    subprocess.run(
        ["schtasks", "/Delete", "/TN", TASK_NAME, "/F"],
        capture_output=True
    )

    # 创建新任务
    result = subprocess.run(
        ["schtasks", "/Create",
         "/TN", TASK_NAME,
         "/TR", f'"{bat_path}"',
         "/SC", "DAILY",
         "/ST", run_time,
         "/F"],
        capture_output=True, text=True
    )
    return result.returncode == 0, result.stdout + result.stderr


def remove_task():
    """删除任务计划"""
    result = subprocess.run(
        ["schtasks", "/Delete", "/TN", TASK_NAME, "/F"],
        capture_output=True, text=True
    )
    return result.returncode == 0


def main():
    print()
    print("=" * 55)
    print("   GamerPulse 定期爬取一键部署工具")
    print("=" * 55)
    print()

    # ---- 卸载模式 ----
    if "--uninstall" in sys.argv:
        print("正在卸载定时任务...")
        if remove_task():
            print(f"  [OK] 已删除任务计划: {TASK_NAME}")
        else:
            print(f"  任务 {TASK_NAME} 不存在或已删除")
        print("\n卸载完成。")
        return

    # ---- 解析运行时间 ----
    run_time = "10:00"
    if "--time" in sys.argv:
        idx = sys.argv.index("--time")
        if idx + 1 < len(sys.argv):
            run_time = sys.argv[idx + 1]

    # ---- 步骤1: 检测 Python ----
    print("[1/4] 检测 Python 环境...")
    python_path = find_python()
    print(f"  Python: {python_path}")
    print()

    # ---- 步骤2: 检查项目依赖 ----
    print("[2/4] 检查项目文件...")
    checks = check_prerequisites()
    has_fail = False
    for item in checks:
        if item[0] == "OK":
            print(f"  [OK]   {item[1]}")
        elif item[0] == "WARN":
            print(f"  [WARN] {item[1]} - {item[2]}")
        elif item[0] == "FAIL":
            print(f"  [FAIL] {item[1]}")
            has_fail = True

    if has_fail:
        print("\n存在缺失文件，请确保项目完整后再部署。")
        return
    print()

    # ---- 步骤3: 生成启动脚本 ----
    print("[3/4] 生成启动脚本...")
    bat_path = generate_bat(python_path)
    print(f"  已生成: {bat_path}")
    print()

    # ---- 步骤4: 创建任务计划 ----
    print(f"[4/4] 创建 Windows 任务计划（每天 {run_time}）...")
    success, output = create_task(bat_path, run_time)

    if not success:
        print(f"  [FAIL] 创建失败")
        print(f"  {output.strip()}")
        print("\n请尝试以管理员身份运行此脚本：")
        print("  1. 右键点击命令行窗口 -> 以管理员身份运行")
        print("  2. 重新执行: python schedule.py")
        return

    # ---- 完成 ----
    print()
    print("=" * 55)
    print("   部署完成！")
    print("=" * 55)
    print(f"""
  任务名称:  {TASK_NAME}
  运行时间:  每天 {run_time}
  启动脚本:  {bat_path}

  功能说明:
  - 每天 {run_time} 自动运行舆情监测
  - 根据舆情热度自动决定是否爬取评论
  - 热点期间每天爬取，常态3天一次，冷清期7天一次
  - 日志文件: crawler/auto_crawl.log
  - 爬取记录: crawler/auto_crawl_log.json

  管理命令:
  - 查看任务状态:  schtasks /Query /TN {TASK_NAME}
  - 立即手动触发:  schtasks /Run /TN {TASK_NAME}
  - 卸载定时任务:  python schedule.py --uninstall
  - 修改运行时间:  python schedule.py --time 14:00
""")
    print("提示: 如果需要修改运行时间，重新运行部署脚本即可覆盖。")
    print()


if __name__ == "__main__":
    main()
