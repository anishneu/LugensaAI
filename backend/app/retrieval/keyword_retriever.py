"""Keyword (lexical) retrieval.

This is the first of the hybrid-retrieval methods called for in the project
plan: fast, deterministic, requires no embedding model or vector database,
and is easy to unit test exactly (same input always produces the same
score). It scores each candidate by term overlap against the topic's search
queries and is intentionally not semantic — a query for "commute options"
will not match a document that only says "getting to campus" unless they
share literal tokens.

This is a real limitation, not a placeholder: it is why the project plan
calls for adding semantic retrieval (embeddings) as a second, complementary
method later, plus metadata/temporal/geographic filtering and reranking on
top of both. Those are out of scope for Milestone 1 because they'd require
an embeddings API or a vector database, neither of which is needed to prove
the rest of the pipeline works.
"""

from __future__ import annotations

import re

from app.models.evidence import Evidence
from app.retrieval.base import EvidenceRetriever

_TOKEN_RE = re.compile(r"[a-z0-9']+")


def _tokenize(text: str) -> set[str]:
    return set(_TOKEN_RE.findall(text.lower()))


class KeywordEvidenceRetriever(EvidenceRetriever):
    def score(self, candidates: list[Evidence], queries: list[str]) -> list[Evidence]:
        query_token_sets = [tokens for q in queries if (tokens := _tokenize(q))]
        scored: list[Evidence] = []
        for evidence in candidates:
            doc_tokens = _tokenize(f"{evidence.source_title} {evidence.text}")
            best_score = 0.0
            for query_tokens in query_token_sets:
                overlap = len(query_tokens & doc_tokens)
                best_score = max(best_score, overlap / len(query_tokens))
            scored.append(evidence.model_copy(update={"relevance_score": round(best_score, 3)}))
        scored.sort(key=lambda e: e.relevance_score or 0.0, reverse=True)
        return scored
