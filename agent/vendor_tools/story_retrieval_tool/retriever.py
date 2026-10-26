from __future__ import annotations

import math
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass

from story_retrieval_tool.schemas import StoryChunk


@dataclass(frozen=True)
class RetrievedChunk:
    chunk: StoryChunk
    score: float
    relevance: str


class StoryRetriever(ABC):
    @abstractmethod
    def retrieve(self, query: str, top_k: int) -> list[RetrievedChunk]:
        """Return top matching chunks."""


class KeywordStoryRetriever(StoryRetriever):
    def __init__(self, chunks: list[StoryChunk]) -> None:
        self.chunks = chunks
        self.chunk_terms = [_terms(_chunk_search_text(chunk)) for chunk in chunks]
        self.doc_freq = self._document_frequency()

    def retrieve(self, query: str, top_k: int) -> list[RetrievedChunk]:
        query_terms = _terms(query)
        if not query_terms:
            return []
        scored: list[RetrievedChunk] = []
        for chunk, terms in zip(self.chunks, self.chunk_terms):
            score = self._score(query_terms, terms, chunk)
            if score > 0:
                scored.append(
                    RetrievedChunk(
                        chunk=chunk,
                        score=score,
                        relevance=_relevance(score),
                    )
                )
        return sorted(scored, key=lambda item: (-item.score, item.chunk.chunk_id))[:top_k]

    def _score(self, query_terms: list[str], terms: list[str], chunk: StoryChunk) -> float:
        term_counts = {term: terms.count(term) for term in set(terms)}
        score = 0.0
        total_docs = max(len(self.chunks), 1)
        title_text = f"{chunk.chapter} {chunk.scene}"
        for term in query_terms:
            if not term:
                continue
            tf = term_counts.get(term, 0)
            if tf:
                df = self.doc_freq.get(term, 1)
                idf = math.log((total_docs + 1) / df) + 1
                score += (1 + math.log(tf)) * idf
            if term in title_text:
                score += 4.0
            if term in chunk.characters:
                score += 3.0
            if term in chunk.content:
                score += 1.0
        return score

    def _document_frequency(self) -> dict[str, int]:
        doc_freq: dict[str, int] = {}
        for terms in self.chunk_terms:
            for term in set(terms):
                doc_freq[term] = doc_freq.get(term, 0) + 1
        return doc_freq


def _chunk_search_text(chunk: StoryChunk) -> str:
    return " ".join(
        [chunk.chapter, chunk.scene, " ".join(chunk.characters), chunk.content]
    )


def _terms(text: str) -> list[str]:
    terms = re.findall(r"[\u4e00-\u9fffA-Za-z0-9]+", text.lower())
    chinese_bigrams: list[str] = []
    for term in terms:
        if re.fullmatch(r"[\u4e00-\u9fff]+", term) and len(term) > 2:
            chinese_bigrams.extend(term[index : index + 2] for index in range(len(term) - 1))
    return terms + chinese_bigrams


def _relevance(score: float) -> str:
    if score >= 15:
        return "high"
    if score >= 6:
        return "medium"
    return "low"
