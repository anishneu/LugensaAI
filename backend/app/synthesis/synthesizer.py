"""Final answer synthesis.

`TemplateSynthesizer` is deterministic and template-based, not LLM-generated
— it renders already-verified claims into prose rather than drafting new
text and checking it afterwards. An LLM-backed synthesizer (Milestone 2)
would more naturally draft first and let verification check the draft; the
docs explain why Milestone 1 orders verification before synthesis instead.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.models.claim import Claim, ClaimStatus
from app.models.location import Location
from app.models.plan import Priority, ResearchPlan

_PRIORITY_ORDER = {Priority.HIGH: 0, Priority.MEDIUM: 1, Priority.LOW: 2}


class Synthesizer(ABC):
    @abstractmethod
    def synthesize(
        self, location: Location, question: str, plan: ResearchPlan, claims: list[Claim]
    ) -> tuple[str, str, list[str]]:
        """Return (summary, recommendation, limitations)."""
        raise NotImplementedError


class TemplateSynthesizer(Synthesizer):
    def synthesize(
        self, location: Location, question: str, plan: ResearchPlan, claims: list[Claim]
    ) -> tuple[str, str, list[str]]:
        limitations: list[str] = []
        summary_lines: list[str] = []
        topics_covered = 0

        ordered_topics = sorted(plan.topics, key=lambda t: _PRIORITY_ORDER[t.priority])
        for topic in ordered_topics:
            topic_claims = [c for c in claims if c.claim_type == topic.topic_id]
            if not topic_claims:
                summary_lines.append(f"{topic.topic_id}: no evidence was found for this topic.")
                limitations.append(f"No evidence was found for planned topic '{topic.topic_id}'.")
                continue

            supported = [c for c in topic_claims if c.status == ClaimStatus.SUPPORTED]
            if supported:
                topics_covered += 1
            for claim in topic_claims:
                if claim.status == ClaimStatus.SUPPORTED:
                    summary_lines.append(
                        f"{topic.topic_id}: {claim.text} "
                        f"(supported by {len(claim.supporting_evidence_ids)} source(s))"
                    )
                else:
                    summary_lines.append(f"{topic.topic_id}: {claim.text} — not confirmed by sufficient evidence.")
                limitations.extend(claim.limitations)

        total_topics = len(plan.topics) or 1
        coverage_ratio = topics_covered / total_topics

        if coverage_ratio == 0:
            recommendation = (
                f"Insufficient evidence was collected to assess {location.name} against this question. "
                "No recommendation can be made from the current sources."
            )
        elif coverage_ratio >= 0.7:
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

        limitations.append(
            "Cross-source contradiction detection is not yet implemented; a 'supported' status reflects "
            "the evidence collected, not verification against dissenting sources."
        )

        summary = " ".join(summary_lines) if summary_lines else "No evidence was collected for this question."
        # De-duplicate limitations while preserving order.
        seen: set[str] = set()
        unique_limitations = [lim for lim in limitations if not (lim in seen or seen.add(lim))]
        return summary, recommendation, unique_limitations
