from __future__ import annotations

import os

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI


def get_chat_model(temperature: float = 0.2) -> ChatOpenAI:
    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("DEEPSEEK_API_KEY")
    base_url = os.getenv("OPENAI_BASE_URL")
    model = os.getenv("OPENAI_MODEL") or os.getenv("DEEPSEEK_MODEL") or "deepseek-chat"

    if os.getenv("DEEPSEEK_API_KEY") and not base_url:
        base_url = "https://api.deepseek.com"

    return ChatOpenAI(
        model=model,
        api_key=api_key,
        base_url=base_url,
        temperature=temperature,
    )


def build_text_chain(system_prompt: str, human_template: str, temperature: float = 0.2):
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", system_prompt),
            ("human", human_template),
        ]
    )
    return prompt | get_chat_model(temperature=temperature) | StrOutputParser()
