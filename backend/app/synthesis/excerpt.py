"""Choosing which part of a long page the model gets to read.

The model only sees a few hundred characters per source. Taking the *first*
few hundred characters means it often reads site navigation, a cookie notice,
or a breadcrumb trail while the reviews sit further down the same page — which
is how an answer ends up as "it's a well-reviewed cafe" and nothing else.
`best_excerpt` instead picks the stretch of the page that talks about what the
question asked. It only selects; it never rewrites, so what the model reads is
still the source's own words.
"""

from __future__ import annotations

import re

_PROSE_WORDS = 8
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?。！？])\s+|\n+")
_WORD_RE = re.compile(r"[^\W_]+", re.UNICODE)
_STOPWORDS = frozenset(
    """the and for with that this from what how are was were have has does did can could would should about
    place good bad like near here there they their them you your its it's is a an of in on at to as be by
    or if my me i we our any some not but more most very much many just also than then too""".split()
)


def query_terms(*texts: str) -> set[str]:
    return {w for text in texts for w in _WORD_RE.findall(text.lower()) if len(w) > 2 and w not in _STOPWORDS}


def best_excerpt(text: str, terms: set[str], limit: int) -> str:
    if len(text) <= limit:
        return text

    sentences = [s.strip() for s in _SENTENCE_SPLIT_RE.split(text) if s.strip()]
    if not terms or not sentences:
        return _cut(text[:limit])

    # A match counts most, but a sentence that reads like prose (8+ words)
    # also counts a little: menus and breadcrumbs are made of short fragments,
    # and this is what lets a run of real review sentences beat them even when
    # the review doesn't repeat the question's exact words ("flat white" for
    # a question about "coffee").
    hits = [
        len(terms & set(_WORD_RE.findall(s.lower()))) + (0.3 if len(_WORD_RE.findall(s)) >= _PROSE_WORDS else 0)
        for s in sentences
    ]
    best_start, best_score = 0, -1
    for start in range(len(sentences)):
        length, score, end = 0, 0, start
        while end < len(sentences) and length + len(sentences[end]) + 1 <= limit:
            length += len(sentences[end]) + 1
            score += hits[end]
            end += 1
        # Strictly greater: on a tie the earlier window wins, so a page with
        # no signal at all still reads from its own beginning.
        if end > start and score > best_score:
            best_start, best_score = start, score

    # Start at the first sentence that actually matches, not at whatever
    # navigation happened to precede it inside the same-scoring window.
    while best_score > 0 and hits[best_start] == 0:
        best_start += 1

    window: list[str] = []
    length = 0
    for sentence in sentences[best_start:]:
        if length + len(sentence) + 1 > limit and window:
            break
        window.append(sentence)
        length += len(sentence) + 1

    excerpt = " ".join(window)
    cut_short = best_start + len(window) < len(sentences) or len(excerpt) > limit
    if len(excerpt) > limit:
        excerpt = excerpt[:limit].rsplit(" ", 1)[0]
    return ("…" if best_start > 0 else "") + excerpt + ("…" if cut_short else "")


def _cut(text: str) -> str:
    return text.rsplit(" ", 1)[0].rstrip() + "…" if " " in text else text
