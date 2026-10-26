
"""
aggregate_opinion.py - 舆情聚合程序，从已处理的 analysis_comments 和 raw_comments 读取数据，调用 generate_diagnosis() 生成 analysis_results
"""
import sqlite3
import json
import sys
import os

# 将项目根目录添加到 sys.path 以便导入 db 等模块
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from db import init_agent_db, get_agent_db_conn, get_raw_db_conn, DBTools
from diagnosis import generate_diagnosis
from dataclasses import dataclass


@dataclass
class RawCommentForDiagnosis:
    """诊断需要的评论结构"""
    id: int
    character_id: int
    source: str
    content: str
    sentiment: str
    tag: str
    is_toxic: bool
    publish_date: str


def main():
    print("=== 舆情聚合程序 ===")
    
    # 初始化数据库
    init_agent_db()
    
    # 清空旧的分析结果
    choice = input("是否清空旧的 analysis_results 数据？(y/n): ")
    if choice.lower() == "y":
        print("正在清空旧数据...")
        conn = get_agent_db_conn()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM analysis_results;")
        conn.commit()
        conn.close()
    
    # 1. 从 agent.db 获取所有提及的角色
    print("\n正在获取被提及的角色列表...")
    conn = get_agent_db_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT character_id FROM analysis_characters;")
    mentioned_character_ids = [row[0] for row in cursor.fetchall()]
    conn.close()
    
    if not mentioned_character_ids:
        print("没有找到任何被提及的角色！请先运行 process_comments.py")
        return
    
    print(f"找到 {len(mentioned_character_ids)} 个被提及的角色")
    
    # 2. 对每个角色进行舆情聚合分析
    print("\n开始分析角色...")
    for i, char_id in enumerate(mentioned_character_ids):
        print(f"\n分析角色 ID: {char_id} ({i+1}/{len(mentioned_character_ids)})")
        
        # 获取角色名称
        char_info = DBTools.get_character_by_id(char_id)
        if not char_info:
            print(f"找不到角色ID {char_id} 的信息，跳过")
            continue
        char_name = char_info["name"]
        
        # 获取该角色相关的评论信息
        comments_for_diagnosis = get_comments_for_character(char_id)
        
        if not comments_for_diagnosis:
            print(f"没有找到角色 {char_id} 的评论")
            continue
        
        print(f"找到 {len(comments_for_diagnosis)} 条相关评论")
        
        # 调用 generate_diagnosis
        print("调用生成诊断分析...")
        try:
            diagnosis_result = generate_diagnosis(
                character_name=char_name,
                comments=comments_for_diagnosis
            )
            
            # 保存到 database
            save_analysis_result(char_id, diagnosis_result)
            print("Done!")
            
        except Exception as e:
            print(f"Error: {e}")
            import traceback
            traceback.print_exc()
    
    print("\n=== 所有角色分析完成 ===")
    print_results_summary()


def get_comments_for_character(char_id: int) -> list:
    """获取某个角色相关的所有评论，整理成诊断需要的格式"""
    comments = []
    
    # 从 agent.db 和 raw_data.db 关联查询
    conn_agent = get_agent_db_conn()
    conn_raw = get_raw_db_conn()
    cursor_agent = conn_agent.cursor()
    cursor_raw = conn_raw.cursor()
    
    # 获取该角色相关的评论
    cursor_agent.execute('''
        SELECT DISTINCT ac.raw_comment_id, ac.sentiment, ac.tag, ac.is_toxic
        FROM analysis_comments ac
        JOIN analysis_characters achar ON ac.id = achar.analysis_comment_id
        WHERE achar.character_id = ?
    ''', (char_id,))
    rows = cursor_agent.fetchall()
    
    for row in rows:
        raw_comment_id = row[0]
        sentiment = row[1]
        tag = row[2]
        is_toxic = row[3]
        
        # 从 raw_data.db 获取原始评论内容
        cursor_raw.execute(
            "SELECT id, source, content, publish_date FROM raw_comments WHERE id = ?",
            (raw_comment_id,)
        )
        raw_row = cursor_raw.fetchone()
        
        if raw_row:
            comment = RawCommentForDiagnosis(
                id=raw_row[0],
                character_id=char_id,
                source=raw_row[1],
                content=raw_row[2],
                sentiment=sentiment,
                tag=tag,
                is_toxic=is_toxic,
                publish_date=raw_row[3]
            )
            comments.append(comment)
    
    conn_agent.close()
    conn_raw.close()
    
    return comments


def save_analysis_result(char_id: int, diagnosis_result: dict):
    """保存诊断结果到 analysis_results 表"""
    # 序列化 JSON 字段
    risk_warnings_json = json.dumps(diagnosis_result.get('risk_warnings', []), ensure_ascii=False)
    word_cloud_json = json.dumps(diagnosis_result.get('word_cloud_data', []), ensure_ascii=False)
    
    DBTools.insert_analysis_result(
        character_id=char_id,
        character_score=diagnosis_result.get('character_score', 50),
        gameplay_score=diagnosis_result.get('gameplay_score', 50),
        system_pain_score=diagnosis_result.get('system_pain_score', 50),
        risk_warnings=risk_warnings_json,
        word_cloud_data=word_cloud_json,
        source_comment_ids=diagnosis_result.get('source_comment_ids', '')
    )


def print_results_summary():
    """打印结果摘要"""
    print("\n=== 结果摘要 ===")
    conn = get_agent_db_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT id, character_id, character_score, gameplay_score, system_pain_score FROM analysis_results")
    rows = cursor.fetchall()
    
    for row in rows:
        print(f"角色 {row[1]}: 角色评分={row[2]}, 玩法评分={row[3]}, 系统痛点={row[4]}")
    
    conn.close()


if __name__ == "__main__":
    main()
