"""LLM-backed final-answer synthesis (Milestone 2).

`LLMSynthesizer` drafts the Overview with an LLM, and — unlike the original
version of this file — gives it both the verified claims *and* the raw,
per-topic evidence excerpts, not claims alone. Gating a whole answer behind
successful atomic claim extraction meant a real, useful body of evidence
routinely produced nothing but "insufficient evidence": claim extraction is
an all-or-nothing, precisely-formatted step that a weaker model (or even a
stronger one, on messy real web text) can fail on a topic while the
underlying evidence is perfectly informative. This synthesizer instead
reasons the way a human analyst would — evidence in, reasoning, a concrete
answer out — while still never being trusted to invent a limitation, and
never being trusted with claim verification itself (`ClaimVerifier` remains
the only place a claim's status is decided, and remains non-LLM regardless
of what's enabled here).

Three things are deliberately kept out of the LLM's hands:

1. **Limitations** — coverage gaps, per-claim caveats, and the standing
   contradiction-detection note come from `deterministic_limitations()`
   (shared with `TemplateSynthesizer`), always, regardless of what the LLM
   wrote. An LLM that "forgets" to mention a gap cannot make it disappear.
2. **Claim status** — the LLM sees claims already labeled
   supported/contradicted/insufficient_evidence; it can only choose how to
   phrase around that status, never assign a different one.
3. **Absolute language** — any of `summary`/`details`/`recommendation` is
   rejected (triggering the template-based fallback) if it uses phrasing
   like "guaranteed" or "completely safe", per the project rule that this
   system never presents a claim as universally/certainly correct — this
   matters most for safety claims, where "no crime has ever happened here"
   is a much stronger statement than the evidence (an absence of hits in a
   time-boxed search) can actually support.
"""

from __future__ import annotations

from app.core.llm_json import parse_json_object
from app.core.llm_service import LLMService, LLMServiceError
from app.models.claim import Claim
from app.models.evidence import Evidence
from app.models.location import Location
from app.models.plan import ResearchPlan
from app.synthesis.synthesizer import (
    Synthesizer,
    SynthesisResult,
    TemplateSynthesizer,
    deduplicate,
    deterministic_limitations,
)

_SYSTEM_PROMPT = (
    "You are a location intelligence analyst. Answer the user's actual question using the evidence "
    "given below about the selected location: verified claims (already checked against sources, "
    "each labeled supported/contradicted/insufficient_evidence) and raw evidence excerpts (real "
    "retrieved passages, not independently verified claim-by-claim, each labeled with its source "
    "type, publisher, and date).\n\n"
    "Synthesize across sources and give the most specific, useful conclusion the evidence actually "
    "supports. Do not default to 'insufficient evidence' just because the evidence is incomplete — "
    "state what CAN be concluded, and be explicit only about the part that remains genuinely "
    "uncertain. Only say a specific part of the question is unanswered if there is truly no "
    "relevant evidence for that part.\n\n"
    "Rules:\n"
    "- Never state a fact that is not directly supported by the evidence given. Never invent a "
    "rating, price, distance, date, or statistic.\n"
    "- Prefer concrete numbers/facts when the evidence has them (a rating, a price, a walking time, "
    "a crime statistic) over vague language.\n"
    "- Treat evidence by its source type: business/directory listings and government/transit data "
    "are closer to objective fact; news reports are recent events; review/forum/blog content is "
    "subjective customer or community opinion — state opinions as opinions (e.g. 'reviewers say...', "
    "'according to community discussion...'), never as objective fact.\n"
    "- A 'contradicted' claim is unresolved disagreement between sources — present both sides, don't "
    "pick one.\n"
    "- For safety/incident/crime topics: never claim something 'has not happened', 'is safe', or "
    "'has never occurred' just because no incident was found. Say instead that recent searches of "
    "the sources checked did not surface reported incidents, and name the time window the evidence "
    "covers if it's known — absence of a search hit is not proof of absence.\n"
    "- Prefer the most recent evidence when the question is about current/recent conditions.\n"
    "- Attribute important facts to their source type inline (e.g. 'according to a local news "
    "report...', 'a business directory listing shows...').\n"
    "- Never state the recommendation as universally or definitely correct — acknowledge it depends "
    "on personal circumstances.\n"
    "- Keep prose concise: summarize, don't copy long passages verbatim.\n\n"
    "Respond with a single strict JSON object and nothing else: no markdown fences, no commentary."
)

_RESPONSE_SHAPE = (
    '{"summary": "<2-4 sentences directly answering the question>", '
    '"key_findings": ["<short finding 1>", "<short finding 2>", "..."], '
    '"details": "<a few short paragraphs organized around the question, attributing facts to source '
    'types and distinguishing fact from opinion>", '
    '"recommendation": "<1-3 sentence bottom-line takeaway>"}'
)

_ABSOLUTE_PHRASES = (
    "guaranteed",
    "without a doubt",
    "100%",
    "definitely the best",
    "always the right choice",
    "certainly the best",
    "completely safe",
    "totally safe",
    "guaranteed safe",
    "risk-free",
    "no crime has ever",
    "never happens here",
    "definitely safe",
)

_MAX_EVIDENCE_SNIPPET_FOR_SYNTHESIS = 400


def _format_claims(claims: list[Claim]) -> str:
    lines = []
    for claim in claims:
        lines.append(
            f"- topic={claim.claim_type} status={claim.status.value} "
            f"sources={len(claim.supporting_evidence_ids)}: {claim.text}"
        )
    return "\n".join(lines) if lines else "(no claims were verified)"


def _format_evidence(evidence: list[Evidence]) -> str:
    by_topic: dict[str, list[Evidence]] = {}
    for item in evidence:
        by_topic.setdefault(item.topic, []).append(item)

    lines: list[str] = []
    for topic_id, items in by_topic.items():
        lines.append(f"Topic: {topic_id}")
        for item in items:
            snippet = item.text
            if len(snippet) > _MAX_EVIDENCE_SNIPPET_FOR_SYNTHESIS:
                snippet = snippet[:_MAX_EVIDENCE_SNIPPET_FOR_SYNTHESIS].rsplit(" ", 1)[0] + "…"
            date = item.published_at.date().isoformat() if item.published_at else "date unknown"
            lines.append(f'- [{item.source_type.value}] ({item.publisher or "unknown source"}, {date}): "{snippet}"')
        lines.append("")
    return "\n".join(lines) if lines else "(no evidence was collected)"


def _contains_absolute_phrase(*texts: str) -> bool:
    combined = " ".join(texts).lower()
    return any(phrase in combined for phrase in _ABSOLUTE_PHRASES)


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
        evidence: list[Evidence],
        topics_with_evidence: set[str] | None = None,
    ) -> SynthesisResult:
        try:
            summary, key_findings, details, recommendation = self._draft_with_llm(
                location, question, claims, evidence
            )
        except (LLMServiceError, ValueError) as exc:
            fallback_result = self._fallback.synthesize(location, question, plan, claims, evidence, topics_with_evidence)
            fallback_result.limitations = deduplicate(
                fallback_result.limitations
                + [f"LLM-based synthesis failed or was rejected ({exc}); used template-based synthesis instead."]
            )
            return fallback_result

        limitations = deduplicate(deterministic_limitations(plan, claims, topics_with_evidence))
        return SynthesisResult(
            summary=summary,
            recommendation=recommendation,
            limitations=limitations,
            key_findings=key_findings,
            details=details,
        )

    def _draft_with_llm(
        self, location: Location, question: str, claims: list[Claim], evidence: list[Evidence]
    ) -> tuple[str, list[str], str, str]:
        location_label = f"{location.name}, {location.city}, {location.region}".strip(", ")
        user_prompt = (
            f"Location: {location_label}\n"
            f'Question: "{question}"\n\n'
            f"Verified claims:\n{_format_claims(claims)}\n\n"
            f"Raw evidence excerpts:\n{_format_evidence(evidence)}\n\n"
            f"Respond with JSON matching exactly this shape:\n{_RESPONSE_SHAPE}"
        )

        raw = self._llm.complete(_SYSTEM_PROMPT, user_prompt)
        parsed = parse_json_object(raw)

        summary = parsed.get("summary")
        recommendation = parsed.get("recommendation")
        key_findings = parsed.get("key_findings", [])
        details = parsed.get("details", "")

        if not summary or not isinstance(summary, str):
            raise ValueError("LLM synthesis response missing a non-empty 'summary'")
        if not recommendation or not isinstance(recommendation, str):
            raise ValueError("LLM synthesis response missing a non-empty 'recommendation'")
        if not isinstance(key_findings, list) or not all(isinstance(f, str) for f in key_findings):
            raise ValueError("LLM synthesis response 'key_findings' must be a list of strings")
        if not isinstance(details, str):
            raise ValueError("LLM synthesis response 'details' must be a string")
        if _contains_absolute_phrase(summary, recommendation, details):
            raise ValueError("LLM synthesis used disallowed absolute language")

        return summary, key_findings, details, recommendation
