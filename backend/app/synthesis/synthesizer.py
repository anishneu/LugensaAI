"""Final answer synthesis.

`TemplateSynthesizer` is deterministic and template-based, not LLM-generated
— it renders already-verified claims into prose rather than drafting new
text and checking it afterwards. Milestone 2's `LLMSynthesizer`
(`app/synthesis/llm_synthesizer.py`) drafts the prose with an LLM instead,
but — deliberately — does not let the LLM decide what counts as a
limitation: coverage gaps, per-claim caveats, and the standing
contradiction-detection note are computed the same deterministic way for
both synthesizers via `deterministic_limitations()` below, so an LLM
omitting an inconvenient caveat can never make it disappear from the
response.

`topics_with_evidence` exists because evidence and claims are no longer
guaranteed to line up 1:1 once real tools are in play (Milestone 3):
`FixtureClaimExtractor` can't produce a claim from real web page text, so a
topic can have evidence but zero claims. Without this, that would render as
"no evidence was found," which is false — evidence was found, it just
didn't turn into a claim. When not provided, it defaults to the claims'
own topics, preserving Milestone 1's behavior where the two always matched.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.models.claim import Claim, ClaimStatus
from app.models.location import Location
from app.models.plan import Priority, ResearchPlan

_PRIORITY_ORDER = {Priority.HIGH: 0, Priority.MEDIUM: 1, Priority.LOW: 2}

_CONTRADICTION_NOTE = (
    "Cross-source contradiction detection uses a coarse keyword-based heuristic (see "
    "app/verification/contradiction.py), not full natural-language understanding — it catches "
    "clear opposite-sentiment phrasing but will miss subtler disagreements, so a 'supported' "
    "status is not a guarantee that no source disagrees."
)


def deterministic_limitations(
    plan: ResearchPlan, claims: list[Claim], topics_with_evidence: set[str] | None = None
) -> list[str]:
    """Limitations that are computed in code, never left to an LLM to mention or omit."""
    covered_topic_ids = {c.claim_type for c in claims}
    evidence_topic_ids = topics_with_evidence if topics_with_evidence is not None else covered_topic_ids

    limitations: list[str] = []
    for topic in plan.topics:
        if topic.topic_id not in evidence_topic_ids:
            limitations.append(f"No evidence was found for planned topic '{topic.topic_id}'.")
        elif topic.topic_id not in covered_topic_ids:
            limitations.append(
                f"Evidence was found for planned topic '{topic.topic_id}' but no claims could be "
                "extracted from it."
            )
    for claim in claims:
        limitations.extend(claim.limitations)
    limitations.append(_CONTRADICTION_NOTE)
    return limitations


def coverage_ratio(plan: ResearchPlan, claims: list[Claim]) -> float:
    total_topics = len(plan.topics) or 1
    topics_covered = len({c.claim_type for c in claims if c.status == ClaimStatus.SUPPORTED})
    return topics_covered / total_topics


def deduplicate(items: list[str]) -> list[str]:
    seen: set[str] = set()
    return [item for item in items if not (item in seen or seen.add(item))]


class Synthesizer(ABC):
    @abstractmethod
    def synthesize(
        self,
        location: Location,
        question: str,
        plan: ResearchPlan,
        claims: list[Claim],
        topics_with_evidence: set[str] | None = None,
    ) -> tuple[str, str, list[str]]:
        """Return (summary, recommendation, limitations)."""
        raise NotImplementedError


class TemplateSynthesizer(Synthesizer):
    def synthesize(
        self,
        location: Location,
        question: str,
        plan: ResearchPlan,
        claims: list[Claim],
        topics_with_evidence: set[str] | None = None,
    ) -> tuple[str, str, list[str]]:
        covered_topic_ids = {c.claim_type for c in claims}
        evidence_topic_ids = topics_with_evidence if topics_with_evidence is not None else covered_topic_ids

        summary_lines: list[str] = []
        ordered_topics = sorted(plan.topics, key=lambda t: _PRIORITY_ORDER[t.priority])
        for topic in ordered_topics:
            topic_claims = [c for c in claims if c.claim_type == topic.topic_id]
            if not topic_claims:
                if topic.topic_id in evidence_topic_ids:
                    summary_lines.append(
                        f"{topic.topic_id}: evidence was found but no claims could be extracted from it."
                    )
                else:
                    summary_lines.append(f"{topic.topic_id}: no evidence was found for this topic.")
                continue
            for claim in topic_claims:
                if claim.status == ClaimStatus.SUPPORTED:
                    summary_lines.append(
                        f"{topic.topic_id}: {claim.text} "
                        f"(supported by {len(claim.supporting_evidence_ids)} source(s))"
                    )
                elif claim.status == ClaimStatus.CONTRADICTED:
                    summary_lines.append(
                        f"{topic.topic_id}: {claim.text} — conflicts with another claim about this topic; "
                        "treat as unresolved rather than trusting either side."
                    )
                else:
                    summary_lines.append(f"{topic.topic_id}: {claim.text} — not confirmed by sufficient evidence.")

        ratio = coverage_ratio(plan, claims)
        if ratio == 0:
            recommendation = (
                f"Insufficient evidence was collected to assess {location.name} against this question. "
                "No recommendation can be made from the current sources."
            )
        elif ratio >= 0.7:
            recommendation = (
                f"Across most of the planned topics, the evidence reviewed points toward {location.name} "
                "having generally supportive conditions for this question. This reflects only the sources "
                "collected in this run and should not be treated as a universally correct or complete answer — "
                "personal priorities and circumstances vary."
            )
        else:
            recommendation = (
                f"The evidence reviewed for {location.name} is mixed or incomplete: some planned topics are "
                "well supported while others have little or no evidence. Treat this as a partial assessment "
                "rather than a confident recommendation."
            )

        summary = " ".join(summary_lines) if summary_lines else "No evidence was collected for this question."
        limitations = deduplicate(deterministic_limitations(plan, claims, topics_with_evidence))
        return summary, recommendation, limitations
