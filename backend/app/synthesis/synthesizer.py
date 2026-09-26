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

`topics_with_evidence` exists because evidence and claims don't line up 1:1:
a topic can have evidence but zero claims (no model configured, or none of the
proposed claims survived verification). Without this, that would render as
"no evidence was found," which is false — evidence was found, it just
didn't turn into a claim. When not provided, it defaults to the claims'
own topics.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from app.models.claim import Claim, ClaimStatus
from app.models.evidence import Evidence
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


@dataclass
class SynthesisResult:
    """A synthesizer's full output.

    `key_findings` and `details` exist alongside `summary`/`recommendation`
    so an Overview can be a real, structured research answer (a short direct
    answer, scannable bullet points, then a longer question-organized
    elaboration) rather than one undifferentiated paragraph — see
    `docs/research-workflow.md`.
    """

    summary: str
    recommendation: str
    limitations: list[str] = field(default_factory=list)
    key_findings: list[str] = field(default_factory=list)
    details: str = ""


class Synthesizer(ABC):
    @abstractmethod
    def synthesize(
        self,
        location: Location,
        question: str,
        plan: ResearchPlan,
        claims: list[Claim],
        evidence: list[Evidence],
        topics_with_evidence: set[str] | None = None,
        questions: list[str] | None = None,
    ) -> SynthesisResult:
        raise NotImplementedError


_SUBJECTIVE_SOURCE_TYPES = {"review_aggregator", "community_forum", "blog"}


class TemplateSynthesizer(Synthesizer):
    """Rule-based fallback: no reasoning, so it never infers anything beyond
    what a claim or a directly-quoted evidence excerpt already says. When a
    topic has evidence but claim extraction produced nothing for it (the
    common case without an LLM key), it quotes the single most relevant
    excerpt verbatim rather than reporting only a gap — clearly labeled as
    an unverified excerpt, since no verification ran on it, but a real
    quoted source beats an empty topic even in the free/no-LLM path.
    """

    def synthesize(
        self,
        location: Location,
        question: str,
        plan: ResearchPlan,
        claims: list[Claim],
        evidence: list[Evidence],
        topics_with_evidence: set[str] | None = None,
        questions: list[str] | None = None,
    ) -> SynthesisResult:
        evidence_by_topic: dict[str, list[Evidence]] = {}
        for item in evidence:
            evidence_by_topic.setdefault(item.topic, []).append(item)

        key_findings: list[str] = []
        detail_blocks: list[str] = []
        ordered_topics = sorted(plan.topics, key=lambda t: _PRIORITY_ORDER[t.priority])
        for topic in ordered_topics:
            label = topic.topic_id.replace("_", " ")
            topic_claims = [c for c in claims if c.claim_type == topic.topic_id]

            if topic_claims:
                lines: list[str] = []
                for claim in topic_claims:
                    if claim.status == ClaimStatus.SUPPORTED:
                        key_findings.append(f"{label}: {claim.text}")
                        lines.append(f"{claim.text} (supported by {len(claim.supporting_evidence_ids)} source(s)).")
                    elif claim.status == ClaimStatus.CONTRADICTED:
                        key_findings.append(f"{label}: sources disagree — {claim.text}")
                        lines.append(
                            f"{claim.text} — conflicts with another claim about this topic; treat as "
                            "unresolved rather than trusting either side."
                        )
                    else:
                        lines.append(f"{claim.text} — not confirmed by sufficient evidence.")
                detail_blocks.append(f"{label.title()}: " + " ".join(lines))
                continue

            topic_evidence = evidence_by_topic.get(topic.topic_id, [])
            if topic_evidence:
                # Relevance alone can pick a highly-relevant but low-quality
                # source (e.g. a marketing page classified as "other") over
                # an equally relevant but far more credible one (e.g. a
                # ".edu" page) -- blend in quality_score so credibility has
                # a real say in which single excerpt gets quoted.
                top = max(topic_evidence, key=lambda e: ((e.relevance_score or 0.0) + (e.quality_score or 0.0)) / 2)
                excerpt = top.text if len(top.text) <= 220 else top.text[:220].rsplit(" ", 1)[0] + "…"
                attribution = "customer/community opinion" if top.source_type in _SUBJECTIVE_SOURCE_TYPES else "a source"
                key_findings.append(f"{label}: an unverified excerpt from {attribution} was found but not confirmed")
                detail_blocks.append(
                    f'{label.title()}: no claim could be confirmed automatically, but {attribution} '
                    f'(published via {top.publisher or top.source_type}) said: "{excerpt}" — read the original '
                    "before treating this as settled."
                )
            else:
                key_findings.append(f"{label}: no evidence was found")
                detail_blocks.append(f"{label.title()}: no evidence was found for this topic.")

        ratio = coverage_ratio(plan, claims)
        if ratio == 0 and not evidence:
            summary = f"No evidence was collected for this question about {location.name}."
            recommendation = (
                f"Insufficient evidence was collected to assess {location.name} against this question. "
                "No recommendation can be made from the current sources."
            )
        elif ratio == 0:
            summary = (
                f"No claims could be automatically verified for {location.name} regarding this question, but "
                f"{len(evidence)} source(s) were found — see the excerpts below and the Evidence tab for the "
                "original, unprocessed material."
            )
            recommendation = (
                f"Automatic verification could not confirm any claims about {location.name} for this question. "
                "Real sources were found (see Details/Evidence) but require manual review rather than an "
                "automated recommendation."
            )
        elif ratio >= 0.7:
            summary = (
                f"Across most of the planned topics, the evidence reviewed points toward {location.name} "
                "having generally supportive conditions for this question."
            )
            recommendation = (
                "This reflects only the sources collected in this run and should not be treated as a "
                "universally correct or complete answer — personal priorities and circumstances vary."
            )
        else:
            summary = (
                f"The evidence reviewed for {location.name} is mixed or incomplete: some planned topics are "
                "well supported while others have little or no evidence."
            )
            recommendation = "Treat this as a partial assessment rather than a confident recommendation."

        details = "\n\n".join(detail_blocks)
        limitations = deduplicate(deterministic_limitations(plan, claims, topics_with_evidence))
        return SynthesisResult(
            summary=summary,
            recommendation=recommendation,
            limitations=limitations,
            key_findings=key_findings,
            details=details,
        )
