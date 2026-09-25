"""Answer-quality metrics, all deterministic: no model judges another model here.

Three questions are asked of any answer text, whichever system wrote it (a plain model, a model handed the raw sources, or the
full pipeline), always against the *same* frozen set of sources:

1. **How much of it is backed by a source?** (`sentence_grounding`) The share of its sentences that no single source covers.
   This is the pipeline's own overview check (`app.verification.support`), so it is the measure the pipeline is built to
   pass. It is reported, but it is not the only one.
2. **Does it state specifics no source contains?** (`unsupported_specifics`) Figures and multi-word names ("Red Line",
   "Harvard University") that appear in none of the sources, the question or the place's own name. A different method from
   (1), so a system cannot satisfy both by tuning to one. "Not in the sources" is not "false": a model can know things
   the sources do not say. It is the honest claim available without a human checking every fact.
3. **Are its citations real?** (`citation_check`) For a system that cites: does each claim's cited evidence exist, and does
   the claim's own wording actually appear in it?

None of these measures whether an answer is *right* or *useful*. That needs a person; see docs/evaluation.md.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.models.claim import Claim
from app.models.evidence import Evidence
from app.verification.support import assess_sentences, content_tokens, numbers_in

_MARKUP_RE = re.compile(r"\*\*|__|`|^#{1,6}\s*|^\s*[-*]\s+", re.MULTILINE)
_CITATION_RE = re.compile(r"\[\s*\d+(?:\s*,\s*\d+)*\s*\]")
# Two or more capitalised words in a row on ONE line: a name. A single capitalised word is usually just a sentence's first,
# and a name never runs across a line break ("Harvard Square" ending one line and "Recent bike theft" starting the next).
_NAME_RE = re.compile(r"\b[A-Z][\w'’-]*(?:[ \t]+[A-Z][\w'’-]*)+\b")
# Words that start sentences and are not part of a name ("The Red Line" is "Red Line").
_LEADING_WORDS = frozenset(
    "the this that these those it its in on at as a an and but or so if while however overall also for from with by of to some many most"
    " there here one two you your they their he she we our what which who when where why how".split()
)
_LIMIT_RE = re.compile(
    r"\b(no evidence|not enough|insufficient|could not|couldn't|cannot|can't|unable|limited|thin|little information|"
    r"no sources?|not able|does not (?:say|state|show)|no information|unknown|unclear|i don't know)\b",
    re.IGNORECASE,
)


def clean(text: str) -> str:
    """The answer with formatting and citation markers removed, so only its words are judged."""
    return _CITATION_RE.sub("", _MARKUP_RE.sub("", text)).strip()


@dataclass(frozen=True)
class Grounding:
    assessed: int
    ungrounded: int

    @property
    def ungrounded_share(self) -> float | None:
        return round(self.ungrounded / self.assessed, 3) if self.assessed else None


def sentence_grounding(answer: str, source_texts: list[str]) -> Grounding:
    assessed, flagged = assess_sentences(clean(answer), source_texts)
    return Grounding(assessed=assessed, ungrounded=len(flagged))


@dataclass(frozen=True)
class Specifics:
    total: int
    unsupported: tuple[str, ...]

    @property
    def unsupported_share(self) -> float | None:
        return round(len(self.unsupported) / self.total, 3) if self.total else None


def _names_in(text: str) -> list[str]:
    names: list[str] = []
    for match in _NAME_RE.findall(text):
        words = match.split()
        while words and words[0].lower() in _LEADING_WORDS:
            words.pop(0)
        if len(words) >= 2:
            names.append(" ".join(words))
    return names


def unsupported_specifics(answer: str, source_texts: list[str], allowed_texts: list[str]) -> Specifics:
    """Figures and names in `answer` found in none of `source_texts` or `allowed_texts` (the question and the place's own
    names, which an answer may repeat without a source)."""
    text = clean(answer)
    haystack = " ".join([*source_texts, *allowed_texts]).lower()
    known_numbers: set[str] = set()
    for source in [*source_texts, *allowed_texts]:
        known_numbers |= numbers_in(source)

    numbers = sorted(numbers_in(text))
    names = list(dict.fromkeys(_names_in(text)))
    unsupported = [f"number {n}" for n in numbers if n not in known_numbers]
    unsupported += [f"name {name}" for name in names if name.lower() not in haystack]
    return Specifics(total=len(numbers) + len(names), unsupported=tuple(unsupported))


@dataclass(frozen=True)
class CitationCheck:
    claims: int
    with_real_citation: int
    worded_like_its_source: int


def citation_check(claims: list[Claim], evidence: list[Evidence], min_overlap: float = 0.5) -> CitationCheck:
    """Every claim's cited evidence must exist in the run's evidence, and the claim's wording must be mostly found in it."""
    by_id = {e.evidence_id: e for e in evidence}
    real = worded = 0
    for claim in claims:
        cited = [by_id[i] for i in claim.supporting_evidence_ids if i in by_id]
        if not cited:
            continue
        real += 1
        words = content_tokens(claim.text)
        source_words: set[str] = set()
        for item in cited:
            source_words |= content_tokens(f"{item.source_title} {item.text}")
        if words and len(words & source_words) / len(words) >= min_overlap:
            worded += 1
    return CitationCheck(claims=len(claims), with_real_citation=real, worded_like_its_source=worded)


def states_a_limit(answer: str, limitations: list[str] | None = None) -> bool:
    """Whether the answer admits what it lacks: it says so in its own words, or the system attached limitations."""
    return bool(limitations) or bool(_LIMIT_RE.search(answer))


def word_count(answer: str) -> int:
    return len(clean(answer).split())
