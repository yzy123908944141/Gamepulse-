"""
TapTap 评论爬虫
- hot:count  → 爬取热门评价
- new:count  → 爬取最新评价
可叠加，如: python scrapers/taptap.py hot:300 new:100
"""
import asyncio
import json
import random
import pandas as pd
from pathlib import Path
from playwright.async_api import async_playwright

APP_ID = "234280"  # 鸣潮游戏ID

PROJECT_ROOT = Path(__file__).parent.parent
HOT_CSV = PROJECT_ROOT / "crawler" / "data" / "taptap_reviews_dom.csv"
NEW_CSV = PROJECT_ROOT / "crawler" / "data" / "taptap_reviews_new.csv"
HOT_OLD_CSV = PROJECT_ROOT / "crawler" / "data" / "taptap_reviews_dom_old.csv"
NEW_OLD_CSV = PROJECT_ROOT / "crawler" / "data" / "taptap_reviews_new_old.csv"

# 官方宣传/背景占位词黑名单
BLACK_LIST_WORDS = [
    "漂泊的旅人", "欢迎在这里醒来", "我们的世界刚刚经历", "涨落无声"
]


def is_valid_content(val, path):
    """判断文本是否为有效的玩家评论"""
    if not isinstance(val, str):
        return False
    if any(x in val for x in ["http://", "https://"]):
        return False
    if any(word in val for word in BLACK_LIST_WORDS):
        return False
    p_lower = path.lower()
    if any(x in p_lower for x in ["app.", "game.", "target.", "subject.", "share.", "advert."]):
        return False
    return True


def extract_fields_heuristically(item, app_id):
    """自适应启发式解析：提取评论字段"""
    flat_data = []

    def walk(val, path=""):
        if isinstance(val, dict):
            for k, v in val.items():
                walk(v, f"{path}.{k}" if path else k)
        elif isinstance(val, list):
            for i, sub_val in enumerate(val):
                walk(sub_val, f"{path}[{i}]")
        else:
            flat_data.append((path, val))

    walk(item)

    username = "未知玩家"
    rating = "未评估"
    content = ""
    play_time = "未知"
    review_id = ""

    # 1. 提取评论ID
    for path, val in flat_data:
        p_lower = path.lower()
        if any(x in p_lower for x in ["review_id", "moment_id", "id", "identifier"]) and not any(
                x in p_lower for x in ["user", "author", "creator", "app", "game", "avatar", "image"]):
            if isinstance(val, (int, str)) and str(val).isdigit():
                val_str = str(val)
                if val_str != app_id and len(val_str) > 8:
                    review_id = val_str
                    break

    # 2. 提取正文
    text_candidates = []
    for path, val in flat_data:
        if isinstance(val, str):
            p_lower = path.lower()
            if any(x in p_lower for x in ["url", "avatar", "image", "icon", "background", "http", "theme", "color"]):
                continue
            if any(word in val for word in BLACK_LIST_WORDS):
                continue
            if any(x in p_lower for x in ["app.", "game.", "target.", "subject.", "share."]):
                continue
            if any(x in p_lower for x in ["text", "content", "body", "desc", "html", "summary", "words", "note"]):
                text_candidates.append((len(val), val))

    if text_candidates:
        text_candidates.sort(key=lambda x: x[0], reverse=True)
        content = text_candidates[0][1]
    else:
        str_candidates = [
            (len(val), val) for path, val in flat_data
            if isinstance(val, str) and len(val) > 20
               and not any(x in val for x in ["http://", "https://"])
               and not any(word in val for word in BLACK_LIST_WORDS)
               and not any(x in path.lower() for x in ["app.", "game.", "target.", "subject.", "share."])
        ]
        if str_candidates:
            str_candidates.sort(key=lambda x: x[0], reverse=True)
            content = str_candidates[0][1]

    # 3. 提取用户名
    name_candidates = []
    for path, val in flat_data:
        if isinstance(val, str) and 1 < len(val) < 40:
            p_lower = path.lower()
            if any(x in p_lower for x in ["name", "nickname", "author", "user"]):
                if not any(x in p_lower for x in ["id", "url", "avatar", "type", "style", "class", "event"]):
                    name_candidates.append((path, val))

    user_names = [val for path, val in name_candidates if "user" in path.lower() or "author" in path.lower()]
    if user_names:
        username = user_names[0]
    elif name_candidates:
        username = name_candidates[0][1]

    # 4. 提取评分
    score_candidates = []
    for path, val in flat_data:
        p_lower = path.lower()
        if any(x in p_lower for x in ["app.", "game."]):
            continue
        if any(x in p_lower for x in ["score", "rating", "star", "value"]):
            if isinstance(val, (int, float)) and 1 <= val <= 5:
                score_candidates.append(val)
            elif isinstance(val, str) and val.isdigit() and 1 <= int(val) <= 5:
                score_candidates.append(int(val))
    if score_candidates:
        rating = f"{score_candidates[0]}星"

    # 5. 提取游玩时间
    for path, val in flat_data:
        p_lower = path.lower()
        if any(x in p_lower for x in ["play", "played", "time", "tips"]):
            if isinstance(val, str) and any(x in val for x in ["小时", "分钟", "天", "游玩"]):
                play_time = val
                break

    # 动态拼接URL
    source_url = f"https://www.taptap.cn/moment/{review_id}" if review_id else f"https://www.taptap.cn/app/{app_id}/review"

    return username, rating, content, play_time, source_url, flat_data


def insert_to_db(reviews: dict, source: str):
    """将爬取的数据清洗后直接入库 raw_comments（与 pipelines.py 消噪逻辑一致）"""
    import sqlite3
    import re

    DB_PATH = Path(__file__).parent.parent / "gamerpulse.db"

    if not reviews:
        print("⚠️ 数据为空，跳过入库。")
        return 0

    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    inserted = 0
    skipped = 0

    for review in reviews.values():
        content = review.get("content", "")

        # 物理消噪
        content = re.sub(r"<[^>]+>", "", content)
        content = re.sub(r"https?://\S+", "", content)
        content = re.sub(r"\[[\u4e00-\u9fa5a-zA-Z]+\]", "", content)
        content = content.strip()

        if len(content) < 3:
            skipped += 1
            continue

        url = review.get("source_url", "")

        cursor.execute(
            "INSERT OR IGNORE INTO raw_comments (source, content, publish_date, url) VALUES (?, ?, ?, ?)",
            (source, content, "", url)
        )
        if cursor.rowcount > 0:
            inserted += 1

    conn.commit()
    conn.close()

    total = len(reviews)
    print(f"💾 直接入库完成: 新增 {inserted} 条，过滤 {skipped} 条噪声，重复跳过 {total - inserted - skipped} 条")
    return inserted


async def _crawl_taptap(sort_param: str, output_file: str, max_reviews: int = 100, source: str = "TAPTAP"):
    """通用TapTap爬虫"""
    target_url = f"https://www.taptap.cn/app/{APP_ID}/review?os=pc"
    if sort_param:
        target_url += f"&sort={sort_param}"
    
    all_reviews = {}
    printed_keys = False

    async def handle_response(response):
        nonlocal printed_keys
        url = response.url

        if "/review/" in url or "list-by-app" in url:
            try:
                data = await response.json()
                items = []

                if "data" in data and isinstance(data["data"], dict):
                    items = data["data"].get("list", [])
                elif "data" in data and isinstance(data["data"], list):
                    items = data["data"]
                elif "list" in data:
                    items = data["list"]

                if not items and isinstance(data, dict):
                    for k, v in data.items():
                        if k == "list" and isinstance(v, list):
                            items = v
                            break
                        elif isinstance(v, dict) and "list" in v:
                            items = v["list"]
                            break

                if not items:
                    return

                added_count = 0
                for item in items:
                    username, rating, content, play_time, source_url, flat_paths = extract_fields_heuristically(item, APP_ID)

                    if not printed_keys and flat_paths:
                        print("\n🔍 ====== 首次拦截 JSON 内部扁平化路径探测 (前 15 个元素) ======")
                        for path, val in flat_paths[:15]:
                            print(f"路径: {path} -> 真实取值: {str(val)[:80]}")
                        print("=================================================================\n")
                        printed_keys = True

                    if content and len(content) > 10:
                        unique_id = f"{username}_{content[:5]}"
                        if unique_id not in all_reviews:
                            all_reviews[unique_id] = {
                                "user_name": username,
                                "rating": rating,
                                "play_time": play_time,
                                "content": content,
                                "source_url": source_url
                            }
                            added_count += 1

                if added_count > 0:
                    print(f"✨ 成功解析：新增 {added_count} 条，目前累计唯一评论数: {len(all_reviews)} 条")

            except Exception:
                pass

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"]
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 900}
        )
        await context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

        page = await context.new_page()
        page.on("response", handle_response)

        print(f"正在打开网页: {target_url}")
        await page.goto(target_url)
        await page.wait_for_timeout(4000)

        no_new_count = 0
        last_len = 0

        print("🚀 开始自动向下滚动触发接口加载...")
        while len(all_reviews) < max_reviews:
            await page.evaluate("window.scrollBy(0, 1000)")
            await page.wait_for_timeout(random.uniform(1500, 2500))

            if len(all_reviews) == last_len:
                no_new_count += 1
                if no_new_count > 6:
                    try:
                        more_btn = page.locator("text=加载更多")
                        if await more_btn.is_visible():
                            print("🖱️ 自动检测到底，点击物理【加载更多】按钮...")
                            await more_btn.click()
                            no_new_count = 0
                    except Exception:
                        pass
                if no_new_count > 25:
                    print("⚠️ 连续未获取到更多新增评论，提前终止退出。")
                    break
            else:
                no_new_count = 0
                last_len = len(all_reviews)

            print(f"[滚动进度条] 抓取总数: {len(all_reviews)} / {max_reviews}")

        if all_reviews:
            df = pd.DataFrame(all_reviews.values())
            df.to_csv(output_file, index=False, encoding="utf-8-sig")
            print(f"🎉 抓取成功！已保存 {len(df)} 条评价至本地：{output_file}")

            # 直接入库
            insert_to_db(all_reviews, source)
        else:
            print("❌ 提取失败，请检查上面输出的 JSON 扁平化探测结构路径是否存在变动。")

        await browser.close()


def crawl_hot_reviews(max_reviews: int = 300):
    """爬取TapTap热门评价"""
    print("=" * 50)
    print("开始爬取 TapTap 热门评价")
    print("=" * 50)
    asyncio.run(_crawl_taptap("", str(HOT_CSV), max_reviews, "TAPTAP_HOT"))


def crawl_new_reviews(max_reviews: int = 300):
    """爬取TapTap最新评价"""
    print("=" * 50)
    print("开始爬取 TapTap 最新评价")
    print("=" * 50)
    asyncio.run(_crawl_taptap("new", str(NEW_CSV), max_reviews, "TAPTAP_NEW"))


# ==========================================
# 入口
# ==========================================
if __name__ == "__main__":
    import sys
    import shutil

    args = sys.argv[1:]

    if not args:
        print("用法: python scrapers/taptap.py <type:count> [type:count ...]")
        print("  type: hot (热门) 或 new (最新)")
        print("示例: python scrapers/taptap.py hot:300 new:100")
        print("PyCharm 参数填写: hot:300 new:100")
        sys.exit(1)

    # 解析 type:count 参数对
    tasks = []
    for arg in args:
        if ":" not in arg:
            print(f"⚠️ 参数格式错误: {arg}，应为 type:count（如 hot:300）")
            sys.exit(1)
        type_str, count_str = arg.rsplit(":", 1)
        type_str = type_str.lower().strip()
        if type_str not in ("hot", "new"):
            print(f"⚠️ 未知类型: {type_str}，只支持 hot 或 new")
            sys.exit(1)
        try:
            tasks.append((type_str, int(count_str)))
        except ValueError:
            print(f"⚠️ 参数格式错误: {arg}，count 必须是数字")
            sys.exit(1)

    # 文件轮转
    for csv_path, old_path, label in [
        (HOT_CSV, HOT_OLD_CSV, "热门"),
        (NEW_CSV, NEW_OLD_CSV, "最新"),
    ]:
        # 只轮转即将要爬取的类型
        if any(t == ("hot" if label == "热门" else "new") for t, _ in tasks):
            if csv_path.exists():
                if old_path.exists():
                    old_path.unlink()
                shutil.move(str(csv_path), str(old_path))
                print(f"📦 {label}旧数据已移动到 {old_path.name}")

    # 执行爬取
    for type_str, count in tasks:
        if type_str == "hot":
            crawl_hot_reviews(max_reviews=count)
        elif type_str == "new":
            crawl_new_reviews(max_reviews=count)

    print(f"\n{'='*50}")
    print(f"🎉 全部完成！")
    for type_str, count in tasks:
        label = "热门" if type_str == "hot" else "最新"
        csv_file = HOT_CSV if type_str == "hot" else NEW_CSV
        print(f"   {label} CSV: {csv_file.name}")
    print(f"   数据库: gamerpulse.db (raw_comments)")
    print(f"{'='*50}")
