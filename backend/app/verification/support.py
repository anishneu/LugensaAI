"""Deterministic checks that a piece of text is actually backed by source text.

Two things need this, and both were previously taken on trust:

* A claim that cites a real evidence id. The extractor confirmed the *id*
  existed, but nothing checked that the claim's *wording* was in that source,
  so a model could attach an invented sentence to a genuine citation and it
  would be marked supported.
* The written overview. It is free model prose; nothing compared its sentences
  with the evidence, so a plausible-sounding line ("a suitable spot for tourists
  with a strong local reputation") could appear with no source behind it.

The check is lexical (shared content words, and every number must appear in the
source). That is deliberately simple and explainable, and it is conservative in
one direction only: it can reject a faithful paraphrase that shares few words,
but it cannot accept a statement whose words and figures aren't in the source.
It is not natural-language inference; see docs/architecture.md.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

# Unicode-aware on purpose: `[a-z0-9]` silently discarded every word written in Cyrillic, Arabic, Thai,
# Devanagari or Han script, so a place name or quoted phrase in any of them counted for nothing.
_TOKEN_RE = re.compile(r"[^\W_]+(?:'[^\W_]+)?")
_NUMBER_RE = re.compile(r"\d+(?:[.,]\d+)*")
_THOUSANDS_COMMA_RE = re.compile(r"(?<=\d),(?=\d)")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+|\n+")

STOPWORDS = frozenset(
    {
        "a", "an", "the", "is", "are", "was", "were", "be", "been", "being", "to", "of", "in", "on",
        "at", "for", "with", "and", "or", "but", "this", "that", "these", "those", "it", "its", "as",
        "by", "from", "has", "have", "had", "not", "no", "than", "then", "there", "their", "they",
        "you", "your", "near", "around", "about", "which", "what", "who", "will", "would", "can",
        "could", "may", "might", "if", "so", "such", "also", "more", "most", "some", "any", "all",
    }
)

# A claim must share at least this fraction of its content words with the
# sources it cites. Set well below the extractor's grounding bar (0.6) because
# here the model *did* cite the right source and is allowed to paraphrase.
MIN_CLAIM_OVERLAP = 0.5
# An overview sentence must be at least this close to some single source.
MIN_SENTENCE_OVERLAP = 0.5
# Shorter sentences ("Here is the summary.") carry too few words to judge.
_MIN_SENTENCE_TOKENS = 5


def _ascii_digits(text: str) -> str:
    """Full-width (１２３), Arabic-Indic (١٢٣) and Devanagari (१२३) digits become 0-9, so a figure
    written in the source's own numerals still matches the same figure in an English claim."""
    return "".join(str(unicodedata.digit(ch)) if ch.isdigit() and not ch.isascii() else ch for ch in text)


def content_tokens(text: str) -> set[str]:
    # Words of 1-2 letters are noise in English but whole words in Chinese, Japanese or Korean.
    return {
        t
        for t in _TOKEN_RE.findall(_ascii_digits(text).lower())
        if t not in STOPWORDS and (len(t) > 2 or not t.isascii())
    }


def numbers_in(text: str) -> set[str]:
    """Every figure in `text`, with thousands separators removed ("1,200" -> "1200")."""
    return set(_NUMBER_RE.findall(_THOUSANDS_COMMA_RE.sub("", _ascii_digits(text))))


@dataclass(frozen=True)
class WordingSupport:
    overlap: float
    missing_numbers: tuple[str, ...]

    def ok(self, min_overlap: float) -> bool:
        return not self.missing_numbers and self.overlap >= min_overlap


def wording_support(text: str, source_texts: list[str]) -> WordingSupport:
    """How well `text` is covered by `source_texts` taken together."""
    tokens = content_tokens(text)
    source_tokens: set[str] = set()
    source_numbers: set[str] = set()
    for source in source_texts:
        source_tokens |= content_tokens(source)
        source_numbers |= numbers_in(source)

    overlap = len(tokens & source_tokens) / len(tokens) if tokens else 1.0
    missing = tuple(sorted(numbers_in(text) - source_numbers))
    return WordingSupport(overlap=round(overlap, 3), missing_numbers=missing)


def untraceable_sentences(text: str, source_texts: list[str], min_overlap: float = MIN_SENTENCE_OVERLAP) -> list[str]:
    """Sentences of `text` that no single source backs.

    A sentence passes if one source covers `min_overlap` of its content words;
    judging against the union of every source would let a long page vouch for
    anything. Any figure in a sentence must appear somewhere in the sources.
    """
    per_source = [(content_tokens(s), numbers_in(s)) for s in source_texts]
    all_numbers: set[str] = set().union(*(numbers for _, numbers in per_source)) if per_source else set()

    flagged: list[str] = []
    for sentence in (s.strip() for s in _SENTENCE_SPLIT_RE.split(text)):
        tokens = content_tokens(sentence)
        if len(tokens) < _MIN_SENTENCE_TOKENS:
            continue
        best = max((len(tokens & source_tokens) / len(tokens) for source_tokens, _ in per_source), default=0.0)
        if best < min_overlap or numbers_in(sentence) - all_numbers:
            flagged.append(sentence)
    return flagged
