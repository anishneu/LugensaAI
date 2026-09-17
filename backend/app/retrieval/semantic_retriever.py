"""Semantic (embedding-based) retrieval (Milestone 4).

Addresses the specific, documented gap in `KeywordEvidenceRetriever`: a
query for "commute options" doesn't match a passage that only says "getting
to campus," because they share no literal tokens. Embeddings place both
close together in vector space even with zero token overlap.

Uses a local `sentence-transformers` model — no API key, but real (if
one-time, cached) model download and CPU inference, unlike the instant,
zero-dependency keyword retriever. The model is loaded lazily on first use,
not at import or construction time, so importing this module (e.g. via
`app/agents/factory.py`) never requires the package to be installed —
only actually scoring does.

`encode_fn` exists so tests can inject a deterministic fake embedding
function instead of loading a real model — see `tests/test_semantic_retriever.py`.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence

from app.core.config import SEMANTIC_MODEL_NAME
from app.models.evidence import Evidence
from app.retrieval.base import EvidenceRetriever

EncodeFn = Callable[[list[str]], Sequence[Sequence[float]]]


def _cosine_similarity(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(float(x) * float(y) for x, y in zip(a, b))
    norm_a = math.sqrt(sum(float(x) ** 2 for x in a))
    norm_b = math.sqrt(sum(float(y) ** 2 for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


class SemanticEvidenceRetriever(EvidenceRetriever):
    def __init__(self, model_name: str = SEMANTIC_MODEL_NAME, encode_fn: EncodeFn | None = None) -> None:
        self._model_name = model_name
        self._model = None
        self._encode_fn = encode_fn

    def _encode(self, texts: list[str]) -> Sequence[Sequence[float]]:
        if self._encode_fn is not None:
            return self._encode_fn(texts)
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self._model_name)
        return self._model.encode(texts, normalize_embeddings=True)

    def score(self, candidates: list[Evidence], queries: list[str]) -> list[Evidence]:
        if not candidates:
            return []

        query_texts = [q for q in queries if q.strip()] or [""]
        query_embeddings = self._encode(query_texts)
        doc_texts = [f"{e.source_title} {e.text}" for e in candidates]
        doc_embeddings = self._encode(doc_texts)

        scored: list[Evidence] = []
        for doc_embedding, evidence in zip(doc_embeddings, candidates):
            best = max(_cosine_similarity(doc_embedding, q) for q in query_embeddings)
            normalized = (best + 1.0) / 2.0  # cosine in [-1, 1] -> [0, 1], consistent with the keyword retriever
            scored.append(evidence.model_copy(update={"relevance_score": round(float(normalized), 3)}))

        scored.sort(key=lambda e: e.relevance_score or 0.0, reverse=True)
        return scored
