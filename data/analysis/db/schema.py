"""
schema.py - 包含系统所有的数据库建表SQL语句
"""

# ==========================================
# 功能A：舆情分析所需表 (存放在 agent.db)
# ==========================================

SQL_CREATE_ANALYSIS_COMMENTS = '''
CREATE TABLE IF NOT EXISTS analysis_comments (
    id INTEGER PRIMARY KEY,
    raw_comment_id INTEGER NOT NULL,
    has_character BOOLEAN NOT NULL,
    sentiment TEXT NOT NULL,
    tag TEXT NOT NULL,
    reason TEXT,
    is_toxic INTEGER DEFAULT 0,
    decision_source TEXT DEFAULT 'flash', -- 结果来源: flash / pro
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
'''

SQL_CREATE_ANALYSIS_CHARACTERS = '''
CREATE TABLE IF NOT EXISTS analysis_characters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    analysis_comment_id INTEGER NOT NULL,
    character_id INTEGER NOT NULL,
    character_name TEXT NOT NULL
)
'''

SQL_CREATE_ANALYSIS_RESULTS = '''
CREATE TABLE IF NOT EXISTS analysis_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    character_id INTEGER NOT NULL,
    analysis_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    character_score REAL NOT NULL,
    gameplay_score REAL NOT NULL,
    system_pain_score REAL NOT NULL,
    risk_warnings TEXT NOT NULL,
    word_cloud_data TEXT NOT NULL,
    source_comment_ids TEXT NOT NULL
)
'''

# ==========================================
# 功能B：剧情沙盒 —— 目前暂不使用持久化表，等前后端联调阶段再按需建表
# ==========================================

# SQL_CREATE_SANDBOX_SESSIONS = '''  (暂未启用)
# CREATE TABLE IF NOT EXISTS sandbox_sessions ( ...
# '''

# SQL_CREATE_SANDBOX_MESSAGES = '''  (暂未启用)
# CREATE TABLE IF NOT EXISTS sandbox_messages ( ...
# '''

