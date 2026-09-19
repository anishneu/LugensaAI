"""LLM-backed claim extraction (Milestone 2).

Milestone 1's `FixtureClaimExtractor` only works because every fixture
document is pre-annotated with the claim it supports. `LLMClaimExtractor`
does the real thing: it reads each evidence item's actual extracted text and
asks the LLM to propose discrete, checkable claims.

The critical safeguard is that the LLM is never trusted to report which
evidence supports a claim. The LLM is asked to cite the evidence id and
topic id verbatim, and when it does so correctly, that citation is used
directly (after checking the id/topic actually exist). But smaller models
reliably fail this exact instruction — observed in practice: a model that
extracts a perfectly accurate claim but cites a source name it noticed
inside the passage (e.g. "FBI Uniform Crime Reporting data") instead of the
literal `[evidence_id]` token it was shown, or invents a free-text topic
label instead of a real topic id. Rather than dropping every claim a weaker
model produces, `_best_matching_evidence()` recovers grounding
deterministically: it checks the claim's own wording against the actual
evidence text via lexical overlap, independent of whatever id/topic the LLM
claimed. A claim is kept only if either the model's citation validates
directly, or this independent text match clears a high bar — never on the
LLM's self-report alone. This is what stops a hallucinated or mislabeled
citation from silently becoming a "supported" claim later in
`ClaimVerifier` — grounding is enforced here, not assumed.
"""

from __future__ import annotations

import re

from app.core.llm_json import parse_json_object
from app.core.llm_service import LLMService, LLMServiceError
from app.models.claim import Claim
from app.models.evidence import Evidence
from app.models.plan import ResearchPlan
from app.synthesis.excerpt import best_excerpt, query_terms
from app.synthesis.claim_extractor import ClaimExtractor, ExtractionResult, FixtureClaimExtractor

_SYSTEM_PROMPT = (
    "You extract discrete, checkable factual or clearly-labeled-subjective claims from research "
    "evidence passages, grouped by research topic.\n\n"
    "Each evidence line looks like this:\n"
    '- [tavily:safety:982ec06c37ea] (Publisher Name) "Some quoted passage text."\n\n'
    "The evidence id is ONLY the exact string inside the square brackets (here, "
    '"tavily:safety:982ec06c37ea") — never the publisher name in parentheses, and never a source '
    'name mentioned inside the quoted text itself (e.g. "FBI" or "CrimeGrades" if those appear in '
    "the passage's own wording). Every claim you propose must be directly supported by one or "
    "more evidence passages, and supporting_evidence_ids must contain ONLY those exact bracketed "
    "id strings, copied verbatim — never invented, never a publisher/source name. Do not propose "
    "a claim with no valid supporting evidence id. Keep each claim to one sentence.\n\n"
    "Example:\n"
    "Evidence:\n"
    "Topic: safety\n"
    '- [tavily:safety:abc123] (CrimeGrades) "Overall crime in Elmwood is rated a C, with property '
    'crime higher than the national average."\n\n'
    "Correct response:\n"
    '{"claims": [{"topic_id": "safety", "text": "Elmwood has higher-than-average property crime.", '
    '"supporting_evidence_ids": ["tavily:safety:abc123"]}]}\n\n'
    "Respond with a single strict JSON object and nothing else: no markdown fences, no commentary."
)

_RESPONSE_SHAPE = (
    '{"claims": [{"topic_id": "<topic id from the evidence given>", '
    '"text": "<one-sentence claim>", "supporting_evidence_ids": ["<evidence id>", ...]}, ...]}'
)

_TOKEN_RE = re.compile(r"[a-z0-9']+")
_STOPWORDS = {
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being", "to", "of", "in", "on",
    "at", "for", "with", "and", "or", "but", "this", "that", "these", "those", "it", "its", "as",
    "by", "from", "has", "have", "had", "not", "no", "than", "then", "there", "their", "they",
    "you", "your", "near", "around", "about", "which", "what", "who", "will", "would", "can",
    "could", "may", "might", "if", "so", "such", "also", "more", "most", "some", "any", "all",
}
# High bar, deliberately: this is a text-similarity fallback standing in for
# an exact id citation, so it should only fire when a claim is unmistakably
# a close paraphrase of one specific evidence item, not merely on the same
# general subject as several.
_MIN_GROUNDING_OVERLAP = 0.6
_MIN_GROUNDING_SHARED_TOKENS = 3


def _content_tokens(text: str) -> set[str]:
    return {t for t in _TOKEN_RE.findall(text.lower()) if t not in _STOPWORDS and len(t) > 2}


def _best_matching_evidence(claim_text: str, evidence: list[Evidence]) -> Evidence | None:
    """Find the evidence item whose own text best supports `claim_text`,
    purely by lexical overlap — no LLM involved. Used only when the LLM's
    self-reported evidence id/topic didn't validate directly, so a claim can
    still be grounded (and correctly attributed to its real topic) as long
    as its wording is a genuine, verifiable extract of some real passage."""
    claim_tokens = _content_tokens(claim_text)
    if len(claim_tokens) < _MIN_GROUNDING_SHARED_TOKENS:
        return None

    best_evidence: Evidence | None = None
    best_overlap = 0
    for item in evidence:
        doc_tokens = _content_tokens(f"{item.source_title} {item.text}")
        shared = len(claim_tokens & doc_tokens)
        if shared > best_overlap:
            best_overlap = shared
            best_evidence = item

    if best_evidence is None:
        return None
    if best_overlap < _MIN_GROUNDING_SHARED_TOKENS:
        return None
    if best_overlap / len(claim_tokens) < _MIN_GROUNDING_OVERLAP:
        return None
    return best_evidence


# Evidence text reaching this point can be a full page extract (up to
# _MAX_FULL_TEXT_LENGTH in app/tools/tavily_tools.py), and every character is
# paid for twice: once in prompt-evaluation latency, once in the model's
# ability to stay on task. Prompt evaluation measurably dominates runtime on
# CPU-only local inference, and claims worth extracting sit near the top of a
# passage rather than buried thousands of characters in, so each item is
# capped here. The full text remains intact on the Evidence itself for the
# UI, the synthesizer, and grounding checks — this cap applies only to what
# the extraction prompt carries.
_MAX_EVIDENCE_CHARS_FOR_EXTRACTION = 600


def _format_evidence_by_topic(evidence: list[Evidence], question: str = "") -> tuple[str, dict[str, set[str]]]:
    by_topic: dict[str, list[Evidence]] = {}
    for item in evidence:
        by_topic.setdefault(item.topic, []).append(item)

    terms = query_terms(question)
    lines: list[str] = []
    valid_ids_by_topic: dict[str, set[str]] = {}
    for topic_id, items in by_topic.items():
        lines.append(f"Topic: {topic_id}")
        valid_ids_by_topic[topic_id] = {item.evidence_id for item in items}
        for item in items:
            snippet = best_excerpt(item.text, terms, _MAX_EVIDENCE_CHARS_FOR_EXTRACTION)
            lines.append(f'- [{item.evidence_id}] ({item.publisher or item.source_type}) "{snippet}"')
        lines.append("")
    return "\n".join(lines), valid_ids_by_topic


class LLMClaimExtractor(ClaimExtractor):
    def __init__(self, llm: LLMService, fallback: ClaimExtractor | None = None) -> None:
        self._llm = llm
        self._fallback = fallback or FixtureClaimExtractor()

    def extract(self, evidence: list[Evidence], plan: ResearchPlan) -> ExtractionResult:
        if not evidence:
            return ExtractionResult(claims=[])

        try:
            return self._extract_with_llm(evidence, plan.question)
        except (LLMServiceError, ValueError) as exc:
            fallback_result = self._fallback.extract(evidence, plan)
            fallback_result.notes.append(
                f"LLM-based claim extraction failed ({exc}); fell back to fixture-based extraction."
            )
            return fallback_result

    def _extract_with_llm(self, evidence: list[Evidence], question: str = "") -> ExtractionResult:
        evidence_text, valid_ids_by_topic = _format_evidence_by_topic(evidence, question)
        user_prompt = (
            f"Evidence, grouped by topic:\n\n{evidence_text}\n"
            f"Respond with JSON matching exactly this shape:\n{_RESPONSE_SHAPE}"
        )

        raw = self._llm.complete(_SYSTEM_PROMPT, user_prompt)
        parsed = parse_json_object(raw)

        raw_claims = parsed.get("claims", [])
        if not isinstance(raw_claims, list):
            raise ValueError("'claims' must be a list")

        notes: list[str] = []
        claims: list[Claim] = []
        for index, entry in enumerate(raw_claims):
            if not isinstance(entry, dict):
                continue
            text = entry.get("text")
            if not text or not isinstance(text, str):
                notes.append("Dropped a proposed claim with no text.")
                continue

            topic_id = entry.get("topic_id")
            proposed_ids = entry.get("supporting_evidence_ids", [])
            valid_ids: list[str] = []
            if topic_id in valid_ids_by_topic and isinstance(proposed_ids, list):
                valid_ids = [eid for eid in proposed_ids if eid in valid_ids_by_topic[topic_id]]
                if len(valid_ids) != len(proposed_ids):
                    notes.append(
                        "Dropped evidence id(s) the LLM cited that don't correspond to real evidence "
                        "given to it."
                    )

            resolved_topic_id = topic_id if topic_id in valid_ids_by_topic else None

            if not valid_ids:
                match = _best_matching_evidence(text, evidence)
                if match is None:
                    notes.append(f"Dropped claim '{text}' — could not be grounded in any real evidence.")
                    continue
                notes.append(
                    f"Claim '{text}' was grounded by matching its wording against evidence text — the "
                    "LLM's own cited evidence id/topic didn't correspond to real evidence given to it."
                )
                valid_ids = [match.evidence_id]
                resolved_topic_id = match.topic

            claims.append(
                Claim(
                    claim_id=f"llm-claim-{index:03d}",
                    text=str(text),
                    claim_type=str(resolved_topic_id),
                    supporting_evidence_ids=valid_ids,
                )
            )

        if not claims:
            raise ValueError("LLM claim extraction returned no valid, grounded claims")

        return ExtractionResult(claims=claims, notes=notes)
