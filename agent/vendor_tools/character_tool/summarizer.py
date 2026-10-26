from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from abc import ABC, abstractmethod

from character_tool.schemas import SCHEMA_VERSION


class CharacterSummarizer(ABC):
    @abstractmethod
    def summarize_character(
        self,
        character_id: str,
        name: str,
        background_story: str,
        personal_profile: str,
    ) -> dict:
        """Return a compact character summary dict."""


class MockCharacterSummarizer(CharacterSummarizer):
    """Deterministic local implementation for tests and dry-run deployments."""

    def summarize_character(
        self,
        character_id: str,
        name: str,
        background_story: str,
        personal_profile: str,
    ) -> dict:
        combined = f"{background_story}\n{personal_profile}".strip()
        return {
            "metadata": {
                "character_id": character_id,
                "name": name,
                "aliases": [],
                "player_controllable": True,
                "summarized": 1,
                "source_hash": "",
                "schema_version": SCHEMA_VERSION,
            },
            "basic_info": {
                "occupation": _first_match(combined, ("研究员", "军人", "医生", "学生", "商人", "巡防队员")),
                "identity": "",
                "faction": _first_match(combined, ("巡防队", "研究所", "学院", "组织")),
            },
            "personality": _brief(personal_profile, 70),
            "background": _brief(background_story, 90),
            "motivation": _brief(personal_profile, 70),
            "relationships": [],
        }


class OpenAICompatibleCharacterSummarizer(CharacterSummarizer):
    """AI adapter using an OpenAI-compatible chat completions endpoint."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
        timeout: int = 60,
    ) -> None:
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.model = model or os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
        self.base_url = (base_url or os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")).rstrip("/")
        self.timeout = timeout
        if not self.api_key:
            raise ValueError("使用 openai-compatible 总结器需要设置 OPENAI_API_KEY。")

    def summarize_character(
        self,
        character_id: str,
        name: str,
        background_story: str,
        personal_profile: str,
    ) -> dict:
        payload = {
            "model": self.model,
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": CHARACTER_SUMMARY_PROMPT},
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "character_id": character_id,
                            "name": name,
                            "background": background_story,
                            "personality": personal_profile,
                            "required_schema_version": SCHEMA_VERSION,
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
        }
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            raise RuntimeError(f"AI 总结请求失败：{exc}") from exc

        content = data["choices"][0]["message"]["content"]
        return json.loads(content)


ExternalModelCharacterSummarizer = OpenAICompatibleCharacterSummarizer


CHARACTER_SUMMARY_PROMPT = """
你是游戏角色资料压缩助手。请只根据输入的 background 和 personality 两段原文，为上层 Agent 生成极简角色上下文。

必须只输出合法 JSON，不输出 Markdown、解释或代码块。
不得补写原文不存在的信息；缺失信息使用 null 或空字符串。
输出必须只包含顶层字段：metadata、basic_info、personality、background、motivation、relationships。
metadata 可以占位，程序会覆盖其中的 character_id、name、aliases、player_controllable、summarized、source_hash、schema_version。

JSON 结构：
{
  "metadata": {
    "character_id": "",
    "name": "",
    "aliases": [],
    "player_controllable": true,
    "summarized": 1,
    "source_hash": "",
    "schema_version": "1.2"
  },
  "basic_info": {
    "occupation": null,
    "identity": "",
    "faction": ""
  },
  "personality": "",
  "background": "",
  "motivation": "",
  "relationships": [
    {
      "name": "",
      "relation": ""
    }
  ]
}

压缩要求：
- basic_info 只提取职业、身份、阵营，不要性别、年龄、种族、信息缺口。
- personality 用一句话概括，不要分条，不要依据和出处，建议 20-45 个中文字符。
- background 用一句话概括关键出身/经历/现状，建议 25-60 个中文字符。
- motivation 用一句话概括目标或行为驱动，建议 20-45 个中文字符。
- relationships 只保留原文明确出现的主要人物或组织，每项 relation 不超过 25 个中文字符。
- 如果关系不明确，relationships 返回空数组。
- 整体输出要短，服务于更高级 Agent 调用，不要扩写成长档案。
"""


def summarize_character(
    character_id: str,
    name: str,
    background_story: str,
    personal_profile: str,
) -> dict:
    return MockCharacterSummarizer().summarize_character(
        character_id,
        name,
        background_story,
        personal_profile,
    )


def build_summarizer(kind: str) -> CharacterSummarizer:
    if kind == "mock":
        return MockCharacterSummarizer()
    if kind == "openai-compatible":
        return OpenAICompatibleCharacterSummarizer()
    raise ValueError(f"不支持的 summarizer：{kind}")


def _brief(text: str, limit: int) -> str:
    normalized = re.sub(r"\s+", " ", text).strip()
    return normalized[:limit]


def _first_match(text: str, words: tuple[str, ...]) -> str | None:
    for word in words:
        if word in text:
            return word
    return None
