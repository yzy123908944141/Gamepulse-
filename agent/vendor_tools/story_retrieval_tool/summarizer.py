from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from typing import Any


class StorySummarizer(ABC):
    @abstractmethod
    def summarize_story_context(
        self,
        query: str,
        retrieved_chunks: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Return structured story context JSON."""


class MockStorySummarizer(StorySummarizer):
    def summarize_story_context(
        self,
        query: str,
        retrieved_chunks: list[dict[str, Any]],
    ) -> dict[str, Any]:
        joined = "\n".join(chunk["content"] for chunk in retrieved_chunks)
        characters = _extract_names(joined)
        return {
            "query": query,
            "characters": [
                {
                    "name": name,
                    "personality": [],
                    "motivation": [],
                    "role_in_story": "",
                }
                for name in characters[:6]
            ],
            "story": {
                "summary": _brief(joined, 160),
                "key_events": [
                    {
                        "order": index + 1,
                        "event": event,
                        "participants": characters[:4],
                    }
                    for index, event in enumerate(_sentences(joined, 4))
                ],
                "main_conflict": "",
                "result": "",
            },
            "background_setting": {
                "locations": [],
                "factions": [],
                "world_rules": [],
                "historical_context": [],
            },
            "source_refs": [
                {
                    "chunk_id": chunk["chunk_id"],
                    "source": chunk["source_file"],
                    "relevance": "检索命中",
                }
                for chunk in retrieved_chunks
            ],
            "information_gaps": [] if retrieved_chunks else ["未检索到相关剧情片段。"],
            "confidence": "medium" if retrieved_chunks else "low",
        }


class OpenAICompatibleStorySummarizer(StorySummarizer):
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

    def summarize_story_context(
        self,
        query: str,
        retrieved_chunks: list[dict[str, Any]],
    ) -> dict[str, Any]:
        payload = {
            "model": self.model,
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": STORY_SUMMARY_PROMPT},
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "query": query,
                            "retrieved_chunks": retrieved_chunks,
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
            raise RuntimeError(f"剧情总结请求失败：{exc}") from exc
        return parse_model_json(data["choices"][0]["message"]["content"])


STORY_SUMMARY_PROMPT = """
你是游戏剧情资料结构化助手。你只能根据用户提供的 retrieved_chunks 回答，不得使用外部知识。

要求：
- 只输出合法 JSON，不输出 Markdown、解释或代码块。
- 不虚构人物性格、剧情事件、世界设定或来源。
- 人物性格必须能由剧情行为或描述支持。
- 按发生顺序整理关键事件。
- 区分故事事件和背景设定。
- 无法确定的信息写入 information_gaps。
- 多个片段存在冲突时，在 information_gaps 中指出。
- 不增加 Schema 之外的字段。
- source_refs 只能引用 retrieved_chunks 中存在的 chunk_id；不能编造来源。

输出 JSON：
{
  "query": "",
  "characters": [
    {
      "name": "",
      "personality": [],
      "motivation": [],
      "role_in_story": ""
    }
  ],
  "story": {
    "summary": "",
    "key_events": [
      {
        "order": 1,
        "event": "",
        "participants": []
      }
    ],
    "main_conflict": "",
    "result": ""
  },
  "background_setting": {
    "locations": [
      {
        "name": "",
        "description": ""
      }
    ],
    "factions": [
      {
        "name": "",
        "description": ""
      }
    ],
    "world_rules": [],
    "historical_context": []
  },
  "source_refs": [
    {
      "chunk_id": "",
      "source": "",
      "relevance": ""
    }
  ],
  "information_gaps": [],
  "confidence": "low"
}
"""


def parse_model_json(content: str) -> dict[str, Any]:
    text = content.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fenced:
        text = fenced.group(1).strip()
    if not text.startswith("{"):
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            text = text[start : end + 1]
    return json.loads(text)


def build_summarizer(kind: str) -> StorySummarizer:
    if kind == "mock":
        return MockStorySummarizer()
    if kind == "openai-compatible":
        return OpenAICompatibleStorySummarizer()
    raise ValueError(f"不支持的 summarizer：{kind}")


def _brief(text: str, limit: int) -> str:
    return re.sub(r"\s+", " ", text).strip()[:limit]


def _sentences(text: str, limit: int) -> list[str]:
    return [
        part.strip()
        for part in re.split(r"[。！？!?]\s*", text)
        if part.strip()
    ][:limit]


def _extract_names(text: str) -> list[str]:
    names: list[str] = []
    for match in re.finditer(r"(?:角色|人物|登场人物)[:：]\s*([^\n]+)", text):
        for part in re.split(r"[、,，；;]\s*", match.group(1)):
            name = part.strip()
            if name and name not in names:
                names.append(name)
    return names
