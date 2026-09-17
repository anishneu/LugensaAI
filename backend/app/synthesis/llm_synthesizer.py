"""LLM-backed final-answer synthesis (Milestone 2).

`LLMSynthesizer` drafts the summary and recommendation with an LLM instead
of `TemplateSynthesizer`'s fixed phrasing, but two things are deliberately
kept out of the LLM's hands:

1. **Limitations** — coverage gaps, per-claim caveats, and the standing
   contradiction-detection note come from `deterministic_limitations()`
   (shared with `TemplateSynthesizer`), always, regardless of what the LLM
   wrote. An LLM that "forgets" to mention a gap cannot make it disappear.
2. **Absolute language** — the recommendation is rejected (triggering the
   template-based fallback) if it uses phrasing like "guaranteed" or
   "without a doubt", per the project rule that a recommendation must never
   be presented as universally correct. This is a real, if narrow, check —
   not a promise that every ungrounded statement is caught.

The LLM is only ever shown already-verified claims (with their status), so
it cannot introduce a claim that skipped verification — it can only choose
how to phrase claims it was given.
"""

from __future__ import annotations

from app.core.llm_json import parse_json_object
from app.core.llm_service import LLMService, LLMServiceError
from app.models.claim import Claim
from app.models.location import Location
from app.models.plan import ResearchPlan
from app.synthesis.synthesizer import (
    Synthesizer,
    TemplateSynthesizer,
    deduplicate,
    deterministic_limitations,
)

_SYSTEM_PROMPT = (
    "You write the final summary and recommendation for a location-research report. You are "
    "given only already-verified claims, each with a status of 'supported', 'insufficient_evidence', "
    "or 'contradicted', and how many sources back it. Write a summary that reports what was found "
    "per topic, and a recommendation that answers the user's question. Rules: only use the claims "
    "given to you, do not introduce any fact not present in them; clearly note when a topic has "
    "insufficient evidence rather than treating silence as a negative signal; for a 'contradicted' "
    "claim, present it as unresolved disagreement between sources rather than picking a side; treat "
    "'community_sentiment' claims as subjective opinion, not objective fact, and say so; never "
    "state the recommendation as universally or definitely correct — acknowledge it depends on "
    "personal circumstances. Respond with a single strict JSON object and nothing else: no "
    "markdown fences, no commentary."
)

_RESPONSE_SHAPE = '{"summary": "<2-5 sentences>", "recommendation": "<2-4 sentences>"}'

_ABSOLUTE_PHRASES = (
    "guaranteed",
    "without a doubt",
    "100%",
    "definitely the best",
    "always the right choice",
    "certainly the best",
)


def _format_claims(claims: list[Claim]) -> str:
    lines = []
    for claim in claims:
        lines.append(
            f"- topic={claim.claim_type} status={claim.status.value} "
            f"sources={len(claim.supporting_evidence_ids)}: {claim.text}"
        )
    return "\n".join(lines) if lines else "(no claims — no evidence was collected)"


class LLMSynthesizer(Synthesizer):
    def __init__(self, llm: LLMService, fallback: Synthesizer | None = None) -> None:
        self._llm = llm
        self._fallback = fallback or TemplateSynthesizer()

    def synthesize(
        self,
        location: Location,
        question: str,
        plan: ResearchPlan,
        claims: list[Claim],
        topics_with_evidence: set[str] | None = None,
    ) -> tuple[str, str, list[str]]:
        try:
            summary, recommendation = self._draft_with_llm(location, question, claims)
        except (LLMServiceError, ValueError) as exc:
            summary, recommendation, fallback_limitations = self._fallback.synthesize(
                location, question, plan, claims, topics_with_evidence
            )
            limitations = deduplicate(
                fallback_limitations
                + [f"LLM-based synthesis failed or was rejected ({exc}); used template-based synthesis instead."]
            )
            return summary, recommendation, limitations

        limitations = deduplicate(deterministic_limitations(plan, claims, topics_with_evidence))
        return summary, recommendation, limitations

    def _draft_with_llm(self, location: Location, question: str, claims: list[Claim]) -> tuple[str, str]:
        location_label = f"{location.name}, {location.city}, {location.region}".strip(", ")
        user_prompt = (
            f"Location: {location_label}\n"
            f'Question: "{question}"\n\n'
            f"Verified claims:\n{_format_claims(claims)}\n\n"
            f"Respond with JSON matching exactly this shape:\n{_RESPONSE_SHAPE}"
        )

        raw = self._llm.complete(_SYSTEM_PROMPT, user_prompt)
        parsed = parse_json_object(raw)

        summary = parsed.get("summary")
        recommendation = parsed.get("recommendation")
        if not summary or not isinstance(summary, str):
            raise ValueError("LLM synthesis response missing a non-empty 'summary'")
        if not recommendation or not isinstance(recommendation, str):
            raise ValueError("LLM synthesis response missing a non-empty 'recommendation'")
        if any(phrase in recommendation.lower() for phrase in _ABSOLUTE_PHRASES):
            raise ValueError("LLM recommendation used disallowed absolute language")

        return summary, recommendation
