
from dataclasses import dataclass
from llm_client import get_llm_client
from prompts import SYSTEM_ROLE_PROMPT, DIAGNOSIS_PROMPT_TEMPLATE
import random

MAX_COMMENTS = 200

@dataclass
class RawComment:
    """原始评论数据结构"""
    id: int
    character_id: int
    source: str
    content: str
    sentiment: str
    tag: str
    is_toxic: bool
    publish_date: str


def _sample_comments(comments: list, max_count: int = MAX_COMMENTS) -> list:
    """
    评论采样策略。
    当前默认策略：如果超过上限，则进行随机均匀采样。
    预留接口方便后续改为按时间、按情感分层等策略。
    """
    if len(comments) <= max_count:
        return comments
    
    # 简单的随机采样
    return random.sample(comments, max_count)


def _format_comments_for_llm(comments):
    """格式化评论列表供 LLM 处理"""
    formatted = []
    for comment in comments:
        toxic_str = "是" if comment.is_toxic == 1 else "否"
        formatted.append(
            f"ID: {comment.id}\n"
            f"平台: {comment.source}\n"
            f"情感: {comment.sentiment}\n"
            f"标签: {comment.tag}\n"
            f"攻击性: {toxic_str}\n"
            f"内容: {comment.content}\n"
            "---"
        )
    return "\n".join(formatted)


def generate_diagnosis(
    character_name: str,
    comments: list
):
    """
    聚合诊断入口函数
    
    Args:
        character_name: 角色名称
        comments: 评论列表
    
    Returns:
        analysis_results 表的整行数据
    """
    if not comments:
        return {
            "character_score": 50,
            "gameplay_score": 50,
            "system_pain_score": 50,
            "risk_warnings": [],
            "word_cloud_data": [],
            "source_comment_ids": ""
        }
    
    # 1. 评论采样
    sampled_comments = _sample_comments(comments)
    
    # 2. 提取并记录本次实际参与分析的评论ID
    source_comment_ids = ",".join(str(c.id) for c in sampled_comments)
    
    # 3. 格式化评论
    comments_text = _format_comments_for_llm(sampled_comments)
    
    # 4. 构建 Prompt
    prompt = DIAGNOSIS_PROMPT_TEMPLATE.format(
        character_name=character_name,
        comments=comments_text
    )
    
    client = get_llm_client()
    
    # 5. 调用 LLM
    result = client.call(
        prompt=prompt,
        system_prompt=SYSTEM_ROLE_PROMPT,
        temperature=0.5,
        max_tokens=4096
    )
    
    # 6. 附加元数据
    result["source_comment_ids"] = source_comment_ids
    
    return result

