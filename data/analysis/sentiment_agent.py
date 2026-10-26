
from llm_client import get_llm_client
from prompts import SINGLE_COMMENT_ANALYSIS_PROMPT, SINGLE_COMMENT_PRO_ANALYSIS_PROMPT, SYSTEM_ROLE_PROMPT
from dataclasses import dataclass
from typing import List, Optional, Tuple


@dataclass
class MentionedCharacter:
    character_name: str


@dataclass
class SingleCommentAnalysisResult:
    has_character: bool
    sentiment: str  # positive/negative/neutral
    tag: str  
    is_toxic: int  # 0/1
    mentioned_characters: List[MentionedCharacter]
    reason: Optional[str] = None
    decision_source: str = "flash" # 元数据：flash / pro


def analyze_single_comment(content: str, known_characters: Optional[List[str]] = None) -> SingleCommentAnalysisResult:
    """
    Cascade Pipeline 架构分析单条游戏评论
    Flash x3 -> 共识检查 -> Pro裁决 -> 业务规则校验
    """
    known_char_prompt = f"已知角色列表: {', '.join(known_characters)}\n请只从该列表中识别角色。" if known_characters else ""
    
    flash_prompt = SINGLE_COMMENT_ANALYSIS_PROMPT.format(
        content=content,
        known_characters=known_char_prompt
    )
    
    client = get_llm_client()
    
    # ==========================
    # 1. Flash 多次采样
    # ==========================
    num_samples = 3
    flash_results = []
    for _ in range(num_samples):
        try:
            result = client.call(
                prompt=flash_prompt,
                system_prompt=SYSTEM_ROLE_PROMPT,
                temperature=0.7 
            )
            flash_results.append(result)
        except Exception as e:
            print(f"Warning: Flash LLM call failed: {e}")
            continue
    
    if not flash_results:
        return _build_fallback_result()

    # ==========================
    # 2. 检查共识 (一致性判断)
    # ==========================
    is_consensus = True
    first_result = flash_results[0]
    
    # 检查核心四个字段是否完全一致
    for r in flash_results[1:]:
        if (r.get("has_character") != first_result.get("has_character") or
            r.get("sentiment") != first_result.get("sentiment") or
            r.get("tag") != first_result.get("tag") or
            r.get("is_toxic") != first_result.get("is_toxic")):
            is_consensus = False
            break

    # ==========================
    # 3. 决定路径 (Flash直接返回 vs Pro裁决)
    # ==========================
    if is_consensus:
        # 提取 mentioned_characters
        chars = [MentionedCharacter(character_name=c.get("character_name", "")) 
                 for c in first_result.get("mentioned_characters", [])]
        
        final_result = SingleCommentAnalysisResult(
            has_character=first_result.get("has_character", False),
            sentiment=first_result.get("sentiment", "neutral"),
            tag=first_result.get("tag", "内容讨论"),
            is_toxic=first_result.get("is_toxic", 0),
            mentioned_characters=chars,
            reason=None,
            decision_source="flash"
        )
    else:
        # 交给 Pro 裁决
        import json
        flash_results_str = ""
        for i, r in enumerate(flash_results):
            flash_results_str += f"\n结果{i+1}:\n{json.dumps(r, ensure_ascii=False, indent=2)}\n"
            
        pro_prompt = SINGLE_COMMENT_PRO_ANALYSIS_PROMPT.format(
            content=content,
            flash_results=flash_results_str,
            known_characters=known_char_prompt
        )
        
        try:
            pro_res = client.call(
                prompt=pro_prompt,
                system_prompt=SYSTEM_ROLE_PROMPT,
                temperature=0.3 # Pro需要更确定的输出
            )
            
            chars = [MentionedCharacter(character_name=c.get("character_name", "")) 
                     for c in pro_res.get("mentioned_characters", [])]
                     
            final_result = SingleCommentAnalysisResult(
                has_character=pro_res.get("has_character", False),
                sentiment=pro_res.get("sentiment", "neutral"),
                tag=pro_res.get("tag", "内容讨论"),
                is_toxic=pro_res.get("is_toxic", 0),
                mentioned_characters=chars,
                reason=pro_res.get("reason", "Pro裁决生成"),
                decision_source="pro"
            )
        except Exception as e:
            print(f"Warning: Pro LLM call failed: {e}")
            return _build_fallback_result()

    # ==========================
    # 4. 业务规则校验
    # ==========================
    # a. 角色白名单校验
    if known_characters:
        valid_chars = []
        for char in final_result.mentioned_characters:
            if char.character_name in known_characters:
                valid_chars.append(char)
            else:
                print(f"Warning: Model hallucinated character '{char.character_name}'. Filtered.")
        final_result.mentioned_characters = valid_chars
        
    # b. 字段自洽性校验 (has_character 和 mentioned_characters 一致性)
    if final_result.has_character and not final_result.mentioned_characters:
        final_result.has_character = False
    elif not final_result.has_character and final_result.mentioned_characters:
        final_result.has_character = True

    return final_result


def _build_fallback_result() -> SingleCommentAnalysisResult:
    """构建调用完全失败时的降级返回"""
    return SingleCommentAnalysisResult(
        has_character=False,
        sentiment="neutral",
        tag="未知",
        is_toxic=0,
        mentioned_characters=[],
        reason="API调用失败",
        decision_source="fallback"
    )

