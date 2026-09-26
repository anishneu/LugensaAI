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
only actually scoring does. Once loaded it is cached per process rather than
per instance (`_MODEL_CACHE`), because a fresh retriever is built for every
research run and re-reading the model off disk each time dominated run time.

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

# Loading a SentenceTransformer reads a real model off disk and takes tens of
# seconds. A new retriever is constructed per research run (see
# `build_default_agent()`, which the API layer calls per request), so caching
# on the instance alone meant paying that load on *every* request. The model
# is immutable once loaded and `encode` is safe to share, so it's cached per
# process and keyed by model name.
_MODEL_CACHE: dict[str, object] = {}


def is_model_warm(model_name: str = SEMANTIC_MODEL_NAME) -> bool:
    """Whether the embedding model is already in memory for this process.

    Exposed so the API can tell callers that the *first* run after a restart
    pays a one-time load the rest don't — the difference is large enough that
    a single duration estimate would be misleading either way.
    """
    return model_name in _MODEL_CACHE


def _load_model(model_name: str) -> object:
    model = _MODEL_CACHE.get(model_name)
    if model is None:
        from sentence_transformers import SentenceTransformer

        try:  # a progress bar for a 0.2-second load is only noise in the server's log
            from transformers.utils import logging as transformers_logging

            transformers_logging.disable_progress_bar()
        except Exception:  # noqa: BLE001 - cosmetic: never a reason to fail
            pass
        try:
            # A model already on this machine is loaded from it, without contacting Hugging Face: no network check on every
            # start, and none of the "unauthenticated requests to the HF Hub" warning that check prints.
            model = SentenceTransformer(model_name, local_files_only=True)
        except Exception:  # noqa: BLE001 - not downloaded yet (the first run ever): fetch it once
            model = SentenceTransformer(model_name)
        _MODEL_CACHE[model_name] = model
    return model


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
            self._model = _load_model(self._model_name)
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
