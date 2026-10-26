
import os
import time
from typing import Dict, Any, Optional
from dotenv import load_dotenv

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.output_parsers import JsonOutputParser

load_dotenv()


class LLMClient:
    """基于 LangChain 封装的 LLM 客户端"""

    def __init__(self, model=None):
        self.model = model or os.getenv("LLM_MODEL", "deepseek-v4-flash")
        
        # 兼容现有环境变量与作业中的环境变量
        api_key = os.getenv("OPENAI_API_KEY") or os.getenv("DEEPSEEK_API_KEY")
        base_url = os.getenv("OPENAI_BASE_URL", "https://api.deepseek.com/v1")
        
        if not api_key:
            raise ValueError("API KEY 环境变量未设置，请检查 OPENAI_API_KEY 或 DEEPSEEK_API_KEY")
        
        self.api_key = api_key
        self.base_url = base_url
        self.max_retries = 3
        
        # 实例化 LangChain 的 JSON 解析器
        self.parser = JsonOutputParser()

    def call(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048
    ) -> Dict[str, Any]:
        """调用 LLM API，返回结构化 JSON 结果"""
        
        # 动态实例化 ChatOpenAI 以支持不同的请求参数
        llm = ChatOpenAI(
            model=self.model,
            openai_api_key=self.api_key,
            base_url=self.base_url,
            temperature=temperature,
            max_tokens=max_tokens,
            request_timeout=60.0,
            max_retries=0 # 我们在外部手动控制重试，以便网络异常和 JSON 解析异常都能走同一套重试逻辑
        )
        
        messages = []
        if system_prompt:
            messages.append(SystemMessage(content=system_prompt))
        messages.append(HumanMessage(content=prompt))
        
        # 组装 LangChain Chain: LLM -> JSON 解析器
        chain = llm | self.parser
        
        last_error = None
        for attempt in range(self.max_retries):
            try:
                # 触发 LangChain 执行
                return chain.invoke(messages)
            except Exception as e:
                last_error = e
                if attempt < self.max_retries - 1:
                    wait_time = (attempt + 1) * 2
                    time.sleep(wait_time)
                else:
                    break
        
        raise Exception(f"LangChain LLM 调用失败，重试 {self.max_retries} 次后仍未成功: {last_error}")


_llm_client_instance = None


def get_llm_client():
    """获取单例 LLM 客户端"""
    global _llm_client_instance
    if _llm_client_instance is None:
        _llm_client_instance = LLMClient()
    return _llm_client_instance

