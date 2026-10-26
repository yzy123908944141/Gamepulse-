import csv
import html
import json
import os
import random
import re
import time
from urllib.parse import parse_qs, urlparse
from bs4 import BeautifulSoup
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# 引入 Playwright 用于自动化登录操作
try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("❌ 缺少依赖库，请在虚拟环境中运行: pip install playwright && playwright install chromium")
    exit(1)

# 本地保存 Cookie 的 JSON 文件路径
COOKIE_FILE_PATH = str(Path(__file__).resolve().parent.parent / "secrets" / "nga_cookie.json")

def auto_login_and_save_cookie():
    """使用 Playwright 弹出浏览器进行手动登录，并自动存储 Cookie 到本地"""
    print("\n[!] 检测到本地无有效的 Cookie 缓存，正在启动浏览器请求登录...")

    with sync_playwright() as p:
        # headless=False 开启带界面的谷歌浏览器进行操作
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()

        # 核心防崩溃：自动过滤并解决登录成功/失败时网页弹出的 JavaScript 警告框 (Alert/Confirm)
        page.on("dialog", lambda dialog: dialog.accept())

        # 跳转到 NGA 统一登录中心
        page.goto("https://nga.178.com/nuke.php?__lib=login&__act=login_ui")

        print("\n" + "=" * 60)
        print("登录指引步骤：")
        print("   1. 请在弹出的 Chrome 浏览器窗口中完成 NGA 账号登录（推荐使用微信/扫码登录）。")
        print("   2. 登录成功并且跳转回 NGA 论坛首页后，请保持浏览器处于开启状态，千万不要手动关闭！")
        print("   3. 直接切回本控制台（终端）窗口，按下 [回车键 Enter] 键。")
        print("=" * 60 + "\n")

        # 阻塞等待用户操作
        input("确认已经登录成功跳转后，在此处按下 [Enter] 回车：")

        try:
            # 自动提取当前环境上下文的 Cookies 状态
            state = context.storage_state()
            with open(COOKIE_FILE_PATH, "w", encoding="utf-8") as f:
                json.dump(state, f, ensure_ascii=False, indent=4)
            print(f"登录凭证成功保存至本地: {COOKIE_FILE_PATH}")
        except Exception as e:
            print("\n❌ 提取 Cookie 失败。")
            print("💡 提示：你可能在按回车前手动把浏览器窗口关掉了，后续请直接按回车，让脚本自动关闭它。")
            print(f"详细异常错误信息: {e}")
        finally:
            # 释放浏览器线程
            browser.close()

def load_cookie_to_session(session: requests.Session):
    """读取本地 Cookie 文件的内容并灌入 requests.Session 中"""
    # 如果文件不存在，则先执行一次自动登录
    if not os.path.exists(COOKIE_FILE_PATH):
        auto_login_and_save_cookie()

    try:
        with open(COOKIE_FILE_PATH, "r", encoding="utf-8") as f:
            state = json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        print("⚠️ 发现本地 Cookie 缓存损坏，尝试重新获取...")
        auto_login_and_save_cookie()
        with open(COOKIE_FILE_PATH, "r", encoding="utf-8") as f:
            state = json.load(f)

    # 提取 Playwright 导出的 cookies 数组并格式化导入到 Requests Session 中
    cookies_list = state.get("cookies", [])
    if not cookies_list:
        print("⚠️ 原有 Cookie 过期或为空，强制清空并重新登陆...")
        if os.path.exists(COOKIE_FILE_PATH):
            os.remove(COOKIE_FILE_PATH)
        auto_login_and_save_cookie()
        return

    for ck in cookies_list:
        session.cookies.set(
            name=ck["name"],
            value=ck["value"],
            domain=ck["domain"],
            path=ck["path"]
        )
    print("✅ 登录 Cookie 凭证已载入网络连接池中")

def create_robust_session() -> requests.Session:
    """创建一个高防伪度、具备重试保障的 Session 客户端"""
    session = requests.Session()
    # 模拟真实 Edge/Chrome 浏览器的请求头结构，绕过 NGA 的硬重置封锁
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Upgrade-Insecure-Requests": "1"
    })
    # 设置 3 次自动重试机制避免由于偶尔的网络抖动导致的抓取失败
    retry_strategy = Retry(
        total=3,
        backoff_factor=1.5,  # 每次重试间隔 1.5s * 2^n
        status_forcelist=[500, 502, 503, 504],
        allowed_methods=["GET"]
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session

class PreprocessorPipeline:
    """舆情文本规范化与消噪管道层 (消除 NGA 的 BBCode 论坛格式符)"""

    @staticmethod
    def clean_bbcode(text: str) -> str:
        if not text:
            return ""
        # 1. 还原网页中的转义字符
        text = html.unescape(text)
        # 2. 匹配并剔除 [img] [size] [style] [randomblock] 及其闭合标签 [/... ]
        text = re.sub(r"\[(randomblock|fixsize|style|color|font|align|b|i|u|url|img)[^\]]*\]", "", text,
                      flags=re.IGNORECASE)
        text = re.sub(r"\[/(randomblock|fixsize|style|color|font|align|b|i|u|url|img)\]", "", text, flags=re.IGNORECASE)
        # 3. 规范化缩进与空格
        text = re.sub(r"\n+", "\n", text)
        return text.strip()

class NGAWebScraper:
    """NGA 爬虫主体类"""

    def __init__(self):
        self.session = create_robust_session()
        # 初始化时自动装载/唤醒验证本地 Cookie 状态
        load_cookie_to_session(self.session)

    def get_post_detail(self, tid: int, page: int = 1) -> list:
        """根据帖子 ID 和页数获取单页的舆情内容（底层数据提取函数）"""
        url = f"https://nga.178.com/read.php?tid={tid}&page={page}"
        # 伪装动态来源 Referer
        self.session.headers["Referer"] = f"https://nga.178.com/read.php?tid={tid}"
        print(f"➡️ 正在请求论坛帖子 (第 {page} 页): {url}")

        try:
            # 建立物理连接，超时时间限制为 12s
            response = self.session.get(url, timeout=12)
            response.raise_for_status()

            # 必须采用 gbk 对 NGA 网页进行正确编码恢复
            response.encoding = "gbk"

            # 使用 BeautifulSoup 解析 HTML DOM 树
            soup = BeautifulSoup(response.text, "lxml")
            posts_data = []

            # 抓取包含论坛帖内容的楼层盒子 Table
            post_tables = soup.find_all("table", class_="forumbox postbox")
            if not post_tables:
                print(f"⚠️ 网页已打开但未在第 {page} 页找到帖子楼层。可视为已抓完所有页面。")
                return []

            for table in post_tables:
                # 1. 抓取用户唯一标识 UID
                author_link = table.find("a", href=re.compile(r"nuke\.php\?func=ucp"))
                uid = None
                if author_link and "href" in author_link.attrs:
                    parsed = urlparse(author_link["href"])
                    uid = parse_qs(parsed.query).get("uid", [None])[0]

                # 2. 抓取楼层发贴的物理时间 (即 评论时间)
                date_span = table.find("span", id=lambda x: x and x.startswith("postdate"))
                post_time = date_span.text.strip() if date_span else "未知"

                # 3. 提取楼层正文部分并进行 BBcode 消噪
                content_elem = table.find(
                    ["span", "p"],
                    id=lambda x: x and x.startswith("postcontent"),
                    class_=lambda x: x and "postcontent" in x
                )
                raw_content = content_elem.text if content_elem else ""
                clean_content = PreprocessorPipeline.clean_bbcode(raw_content)

                if clean_content:
                    posts_data.append({
                        "用户UID": uid,
                        "评论时间": post_time,
                        "评论内容": clean_content,
                        "source_url": url
                    })

            return posts_data

        except requests.exceptions.ConnectionError:
            print("❌ 请求时发生 RST 网络中断 (10054)。可能是触发防爬封锁。")
            return []
        except Exception as e:
            print(f"❌ 运行单页抓取异常: {e}")
            return []

    def get_comments_by_limit(self, tid: int, max_count: int = 50) -> list:
        """主入口：控制爬取总条数并支持翻页"""
        all_comments = []
        page = 1

        print(f"\n🚀 开始抓取帖子 {tid}，目标计划获取 {max_count} 条数据...")

        while len(all_comments) < max_count:
            page_comments = self.get_post_detail(tid, page)
            if not page_comments:
                print("🏁 没有获取到更多新回复，提前结束抓取。")
                break

            # 计算本次还需要保留多少条回复，防止超出总额
            needed_count = max_count - len(all_comments)
            all_comments.extend(page_comments[:needed_count])

            print(f"📈 [页码 {page}] 本页提取出 {len(page_comments)} 条，目前累计抓取进展: {len(all_comments)}/{max_count} 条")

            # 翻页
            page += 1
            # 随机休眠 1.5 - 3.5秒，温柔爬取，防止被 NGA 识别并拉黑
            if len(all_comments) < max_count:
                sleep_time = random.uniform(1.5, 3.5)
                time.sleep(sleep_time)

        return all_comments


def save_to_csv(data: list, file_path: str):
    """将抓取的数据存入 CSV 文件 (覆写)"""
    if not data:
        print("⚠️ 数据为空，取消写入 CSV。")
        return

    headers = ["用户UID", "评论时间", "评论内容", "source_url"]

    try:
        with open(file_path, mode="w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()

            for row in data:
                clean_row = {k: row.get(k, "") for k in headers}
                writer.writerow(clean_row)

        print(f"💾 数据已写入: {file_path}")
    except Exception as e:
        print(f"❌ 写入 CSV 发生错误: {e}")


def insert_to_db(data: list, source: str = "NGA"):
    """将爬取的数据清洗后直接入库 raw_comments（与 pipelines.py 消噪逻辑一致）"""
    import sqlite3

    DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "gamerpulse.db")

    if not data:
        print("⚠️ 数据为空，跳过入库。")
        return 0

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    inserted = 0
    skipped = 0

    for item in data:
        content = item.get("评论内容", "")

        # 物理消噪
        content = re.sub(r"<[^>]+>", "", content)
        content = re.sub(r"https?://\S+", "", content)
        content = re.sub(r"\[[\u4e00-\u9fa5a-zA-Z]+\]", "", content)
        content = content.strip()

        if len(content) < 3:
            skipped += 1
            continue

        publish_date = item.get("评论时间", "")
        url = item.get("source_url", "")

        cursor.execute(
            "INSERT OR IGNORE INTO raw_comments (source, content, publish_date, url) VALUES (?, ?, ?, ?)",
            (source, content, publish_date, url)
        )
        if cursor.rowcount > 0:
            inserted += 1

    conn.commit()
    conn.close()

    total = len(data)
    print(f"💾 直接入库完成: 新增 {inserted} 条，过滤 {skipped} 条噪声，重复跳过 {total - inserted - skipped} 条")
    return inserted


# ==========================================
# 入口
# ==========================================
if __name__ == "__main__":
    import sys
    import shutil
    from pathlib import Path

    PROJECT_ROOT = Path(__file__).parent.parent
    NEW_CSV = PROJECT_ROOT / "crawler" / "nga.csv"
    OLD_CSV = PROJECT_ROOT / "crawler" / "nga_old.csv"

    args = sys.argv[1:]

    if not args:
        print("用法: python scrapers/nga.py <tid:count> [tid:count ...]")
        print("示例: python scrapers/nga.py 47144463:300 12345678:100")
        print("PyCharm 参数填写: 47144463:300 12345678:100")
        sys.exit(1)

    # 解析 tid:count 参数对
    tasks = []
    for arg in args:
        if ":" not in arg:
            print(f"⚠️ 参数格式错误: {arg}，应为 tid:count（如 47144463:300）")
            sys.exit(1)
        tid_str, count_str = arg.rsplit(":", 1)
        try:
            tasks.append((int(tid_str), int(count_str)))
        except ValueError:
            print(f"⚠️ 参数格式错误: {arg}，tid 和 count 必须是数字")
            sys.exit(1)

    # 文件轮转：nga.csv → nga_old.csv
    if NEW_CSV.exists():
        if OLD_CSV.exists():
            OLD_CSV.unlink()
        shutil.move(str(NEW_CSV), str(OLD_CSV))
        print(f"📦 旧数据已移动到 nga_old.csv")

    # 爬取所有 tid
    scraper = NGAWebScraper()
    all_comments = []

    for tid, count in tasks:
        print(f"\n{'='*50}")
        print(f"📋 开始爬取 tid={tid}，目标 {count} 条")
        print(f"{'='*50}")
        comments = scraper.get_comments_by_limit(tid=tid, max_count=count)
        all_comments.extend(comments)
        print(f"✅ tid={tid} 完成，获取 {len(comments)} 条")

    # 保存到 nga.csv
    save_to_csv(all_comments, str(NEW_CSV))

    # 直接入库
    insert_to_db(all_comments, "NGA")

    print(f"\n{'='*50}")
    print(f"🎉 全部完成！共爬取 {len(all_comments)} 条")
    print(f"   CSV: {NEW_CSV.name}")
    print(f"   数据库: gamerpulse.db (raw_comments)")
    if OLD_CSV.exists():
        print(f"   旧CSV: {OLD_CSV.name}")
    print(f"{'='*50}")
