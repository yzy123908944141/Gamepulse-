from __future__ import annotations

import re
from dataclasses import dataclass, field

from worldview_tool.schemas import SUPPORTED_SECTIONS


SYNONYMS: dict[str, list[str]] = {
    "悲鸣": ["灾变", "灾难", "末日"],
    "海蚀": ["海蚀现象", "现实侵蚀"],
    "残象": ["残响体", "怪物"],
    "声骸": ["残象能力", "数据坞"],
    "共鸣者": ["声痕", "共鸣能力"],
    "超频": ["失控", "能力暴走"],
    "索诺拉": ["记忆空间", "回音空间"],
    "岁主": ["文明守护者"],
    "鸣式": ["高位残象", "文明级灾害"],
    "黑海岸": ["悲鸣研究组织"],
    "残星会": ["敌对组织"],
    "漂泊者": ["主角"],
}

SECTION_ALIASES: dict[str, tuple[str, ...]] = {
    "world_overview": ("世界总览", "一、世界总览"),
    "world_rules": ("世界运行的核心逻辑", "二、世界运行的核心逻辑"),
    "disaster_system": ("灾害体系", "三、灾害体系"),
    "echo_and_sonoro": ("回音、残响与索诺拉", "四、回音、残响与索诺拉"),
    "resonators": ("共鸣者", "五、共鸣者"),
    "civilization_entities": ("文明级存在", "六、文明级存在"),
    "regions_and_factions": ("主要组织与地区", "七、主要组织与地区"),
    "rover": ("漂泊者", "八、漂泊者"),
}


@dataclass(frozen=True)
class LoreChunk:
    title: str
    parent_title: str | None
    body: str
    section_key: str | None
    keywords: set[str] = field(default_factory=set)

    @property
    def label(self) -> str:
        if self.parent_title and self.parent_title != self.title:
            return f"{self.parent_title}/{self.title}"
        return self.title

    @property
    def text(self) -> str:
        return f"{self.label}\n{self.body}".strip()


@dataclass(frozen=True)
class RetrievalResult:
    chunks: list[LoreChunk]
    warnings: list[str]


def parse_markdown_sections(content: str) -> list[LoreChunk]:
    chunks: list[LoreChunk] = []
    current_parent: str | None = None
    current_title: str | None = None
    current_level: int | None = None
    current_body: list[str] = []

    def flush() -> None:
        nonlocal current_title, current_body
        if current_title is None:
            return
        body = "\n".join(current_body).strip()
        if not body:
            return
        parent = current_parent if current_level == 3 else None
        title = _clean_heading(current_title)
        parent_title = _clean_heading(parent) if parent else None
        section_key = _section_key_for(parent_title or title)
        chunks.append(
            LoreChunk(
                title=title,
                parent_title=parent_title,
                body=body,
                section_key=section_key,
                keywords=_extract_keywords(title, parent_title, body),
            )
        )

    for raw_line in content.splitlines():
        match = re.match(r"^(#{2,3})\s+(.+?)\s*$", raw_line)
        if match:
            flush()
            level = len(match.group(1))
            title = match.group(2)
            if level == 2:
                current_parent = title
            current_title = title
            current_level = level
            current_body = []
            continue
        current_body.append(raw_line)

    flush()
    return chunks


class WorldLoreRetriever:
    def __init__(self, content: str) -> None:
        self.chunks = parse_markdown_sections(content)

    def search(
        self,
        query: str,
        section: str | None = None,
        max_chars: int = 3000,
    ) -> RetrievalResult:
        warnings: list[str] = []
        if section and section not in SUPPORTED_SECTIONS:
            return RetrievalResult([], [f"不支持的 section：{section}"])

        scoped_chunks = [
            chunk for chunk in self.chunks if section is None or chunk.section_key == section
        ]
        if section and not scoped_chunks:
            return RetrievalResult([], [f"指定 section 中未找到内容：{section}"])

        expanded_terms = _expand_query_terms(query)
        scored = [
            (self._score(chunk, query, expanded_terms), index, chunk)
            for index, chunk in enumerate(scoped_chunks)
        ]
        matched = [
            chunk
            for score, _index, chunk in sorted(scored, key=lambda item: (-item[0], item[1]))
            if score > 0
        ]

        if not matched:
            return RetrievalResult([], ["未找到相关世界观内容"])

        selected: list[LoreChunk] = []
        used_chars = 0
        for chunk in matched:
            next_len = len(chunk.text) + (2 if selected else 0)
            if selected and used_chars + next_len > max_chars:
                break
            selected.append(chunk)
            used_chars += next_len
            if used_chars >= max_chars:
                break

        return RetrievalResult(selected or matched[:1], warnings)

    def _score(self, chunk: LoreChunk, query: str, terms: set[str]) -> int:
        score = 0
        title_text = chunk.label
        body_text = chunk.body

        if query.strip() and query.strip() == chunk.title:
            score += 120

        for term in terms:
            if not term:
                continue
            if term == chunk.title or term == chunk.parent_title:
                score += 90
            elif term in title_text:
                score += 45
            if term in body_text:
                score += 12 + min(body_text.count(term), 5) * 2
            if term in chunk.keywords:
                score += 10

        for canonical, aliases in SYNONYMS.items():
            if canonical in query and any(alias in chunk.text for alias in aliases):
                score += 8
            if any(alias in query for alias in aliases) and canonical in chunk.text:
                score += 8

        return score


def _clean_heading(title: str | None) -> str:
    if not title:
        return ""
    return re.sub(r"^[一二三四五六七八九十]+、", "", title.strip())


def _section_key_for(title: str) -> str | None:
    clean_title = _clean_heading(title)
    for key, aliases in SECTION_ALIASES.items():
        if clean_title in aliases or clean_title == SUPPORTED_SECTIONS[key]:
            return key
    return None


def _extract_keywords(title: str, parent_title: str | None, body: str) -> set[str]:
    text = f"{title} {parent_title or ''} {body}"
    keywords = {term for term in SYNONYMS if term in text}
    for canonical, aliases in SYNONYMS.items():
        if any(alias in text for alias in aliases):
            keywords.add(canonical)
    return keywords


def _expand_query_terms(query: str) -> set[str]:
    terms = {query.strip()}
    terms.update(re.findall(r"[\u4e00-\u9fffA-Za-z0-9]+", query))
    for canonical, aliases in SYNONYMS.items():
        if canonical in query or any(alias in query for alias in aliases):
            terms.add(canonical)
            terms.update(aliases)
    return {term for term in terms if term}
