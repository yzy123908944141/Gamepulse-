"""
GamerPulse 爬虫配置文件
基于关键词提取分析 (2026-07-15) 重写
集中管理：维度关键词、角色关键词、tag 细分标签、爬虫参数
"""


# ==========================================
# 1. 物理消噪规则
# ==========================================
NOISE_RULES = {
    "min_content_length": 3,           # 最短有效字数
    "filter_html_tags": True,          # 过滤 HTML 标签
    "filter_urls": True,               # 过滤 URL 链接
    "filter_pure_emoji": True,         # 过滤纯表情内容
    "filter_duplicate_uid": False,     # 是否按 UID 去重（NGA 同帖多楼不去重）
}

# ==========================================
# 2. 数据源路径配置
# ==========================================
DATA_SOURCES = {
    "nga_csv": "crawler/data/nga.csv",
    "taptap_new_csv": "crawler/data/taptap_reviews_new.csv",
    "taptap_hot_csv": "crawler/data/taptap_reviews_dom.csv",
}

# 目标游戏
TARGET_GAME = "鸣潮"

