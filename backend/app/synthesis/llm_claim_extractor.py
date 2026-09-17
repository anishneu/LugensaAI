"""LLM-backed claim extraction (Milestone 2).

Milestone 1's `FixtureClaimExtractor` only works because every fixture
document is pre-annotated with the claim it supports. `LLMClaimExtractor`
does the real thing: it reads each evidence item's actual extracted text and
asks the LLM to propose discrete, checkable claims.

The critical safeguard is that the LLM is never trusted to report which
evidence supports a claim: any `supporting_evidence_ids` it returns that
don't correspond to real evidence actually given to it are dropped, and a
claim left with zero valid supporting ids is dropped entirely. This is what
stops a hallucinated citation from silently becoming a "supported" claim
later in `ClaimVerifier` — grounding is enforced here, not assumed.
"""

from __future__ import annotations

from app.core.llm_json import parse_json_object
from app.core.llm_service import LLMService, LLMServiceError
from app.models.claim import Claim
from app.models.evidence import Evidence
from app.models.plan import ResearchPlan
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


def _format_evidence_by_topic(evidence: list[Evidence]) -> tuple[str, dict[str, set[str]]]:
    by_topic: dict[str, list[Evidence]] = {}
    for item in evidence:
        by_topic.setdefault(item.topic, []).append(item)

    lines: list[str] = []
    valid_ids_by_topic: dict[str, set[str]] = {}
    for topic_id, items in by_topic.items():
        lines.append(f"Topic: {topic_id}")
        valid_ids_by_topic[topic_id] = {item.evidence_id for item in items}
        for item in items:
            lines.append(f'- [{item.evidence_id}] ({item.publisher or item.source_type}) "{item.text}"')
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
            return self._extract_with_llm(evidence)
        except (LLMServiceError, ValueError) as exc:
            fallback_result = self._fallback.extract(evidence, plan)
            fallback_result.notes.append(
                f"LLM-based claim extraction failed ({exc}); fell back to fixture-based extraction."
            )
            return fallback_result

    def _extract_with_llm(self, evidence: list[Evidence]) -> ExtractionResult:
        evidence_text, valid_ids_by_topic = _format_evidence_by_topic(evidence)
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
            topic_id = entry.get("topic_id")
            text = entry.get("text")
            proposed_ids = entry.get("supporting_evidence_ids", [])
            if topic_id not in valid_ids_by_topic or not text or not isinstance(proposed_ids, list):
                notes.append("Dropped a proposed claim with an unrecognized topic or missing text.")
                continue

            valid_ids = [eid for eid in proposed_ids if eid in valid_ids_by_topic[topic_id]]
            if len(valid_ids) != len(proposed_ids):
                notes.append(
                    "Dropped evidence id(s) the LLM cited that don't correspond to real evidence "
                    "given to it."
                )
            if not valid_ids:
                notes.append(f"Dropped claim '{text}' — no valid supporting evidence id remained.")
                continue

            claims.append(
                Claim(
                    claim_id=f"llm-claim-{index:03d}",
                    text=str(text),
                    claim_type=str(topic_id),
                    supporting_evidence_ids=valid_ids,
                )
            )

        if not claims:
            raise ValueError("LLM claim extraction returned no valid, grounded claims")

        return ExtractionResult(claims=claims, notes=notes)
