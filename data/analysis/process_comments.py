
"""
process_comments.py - 处理原始评论，生成 analysis_comments 和 analysis_characters 表
"""
import sqlite3
import time
import json
import sys
import os

# 将项目根目录添加到 sys.path 以便导入 db 等模块
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from db import init_agent_db, DBTools
from sentiment_agent import analyze_single_comment


def main():
    print("=== 评论处理程序 ===")
    
    # 初始化数据库
    init_agent_db()
    
    # 询问是否清空旧数据
    choice = input("是否清空 agent.db 中已有的评论分析数据？(y/n): ")
    if choice.lower() == "y":
        print("正在清空旧数据...")
        DBTools.clear_agent_db()
        init_agent_db() # 重新初始化数据库，创建新表结构
    
    # 加载角色信息
    characters = DBTools.get_characters()
    name_to_id = {name: data["id"] for name, data in characters.items()}
    known_character_names = DBTools.get_character_names()
    
    # 获取评论
    limit_input = input("要处理多少条评论？（留空处理所有）: ")
    limit = int(limit_input) if limit_input.strip() else None
    comments = DBTools.get_all_comments(limit=limit)
    
    print(f"\n找到 {len(comments)} 条评论需要处理")
    
    # 处理评论
    success_count = 0
    for i, comment in enumerate(comments):
        print(f"正在处理第 {i+1}/{len(comments)} 条评论 (ID: {comment['id']})...", end="")
        
        try:
            # 调用 agent 分析
            analysis_result = analyze_single_comment(comment["content"], known_characters=known_character_names)
            
            # 保存到 analysis_comments
            analysis_comment_id = DBTools.insert_analysis_comment(
                raw_comment_id=comment["id"],
                has_character=analysis_result.has_character,
                sentiment=analysis_result.sentiment,
                tag=analysis_result.tag,
                reason=analysis_result.reason,
                is_toxic=analysis_result.is_toxic,
                decision_source=analysis_result.decision_source
            )
            
            # 保存关联角色到 analysis_characters
            if analysis_result.has_character:
                for mentioned_char in analysis_result.mentioned_characters:
                    char_id = name_to_id.get(mentioned_char.character_name)
                    if char_id:
                        DBTools.insert_character_link(
                            analysis_comment_id=analysis_comment_id,
                            character_id=char_id,
                            character_name=mentioned_char.character_name
                        )
            
            success_count += 1
            DBTools.update_raw_comment_analysis_status(comment['id'], 1)  # 标记为已处理
            print(" Done")
        
        except Exception as e:
            print(f" Error: {e}")
            import traceback
            traceback.print_exc()
        
        # 避免 API 请求过快
        time.sleep(0.1)
    
    print(f"\n处理完成！成功 {success_count}/{len(comments)} 条评论")


if __name__ == "__main__":
    main()
