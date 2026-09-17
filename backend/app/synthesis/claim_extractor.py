"""Claim extraction: turning evidence passages into discrete, linked claims.

Milestone 1's `FixtureClaimExtractor` does not use an LLM to extract claims
from free text. Instead, each fixture document is pre-annotated with the
claim it was written to support (`metadata["claim_text"]`) — a stand-in for
what an LLM-based extractor would produce from real page text.
`FixtureClaimExtractor` groups evidence that supports the same claim text
within a topic, which is how multiple independent sources end up
corroborating one claim.

Milestone 2's `app/synthesis/llm_claim_extractor.py` replaces this with real
free-text extraction via an LLM, falling back to this fixture-based
extractor if the LLM call fails or a key isn't configured.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from app.models.claim import Claim
from app.models.evidence import Evidence
from app.models.plan import ResearchPlan


@dataclass
class ExtractionResult:
    """Claims plus transparency notes about how extraction went.

    `notes` surfaces things like "the LLM extractor failed and this run fell
    back to fixture-based extraction" so degraded runs are visible in the
    final response's limitations rather than silently indistinguishable from
    a fully-successful one.
    """

    claims: list[Claim]
    notes: list[str] = field(default_factory=list)


class ClaimExtractor(ABC):
    @abstractmethod
    def extract(self, evidence: list[Evidence], plan: ResearchPlan) -> ExtractionResult:
        raise NotImplementedError


class FixtureClaimExtractor(ClaimExtractor):
    def extract(self, evidence: list[Evidence], plan: ResearchPlan) -> ExtractionResult:
        groups: dict[tuple[str, str], list[Evidence]] = {}
        for item in evidence:
            claim_text = item.metadata.get("claim_text")
            if not claim_text:
                continue
            groups.setdefault((item.topic, claim_text), []).append(item)

        claims: list[Claim] = []
        for index, ((topic_id, claim_text), items) in enumerate(groups.items()):
            claims.append(
                Claim(
                    claim_id=f"claim-{index:03d}",
                    text=claim_text,
                    claim_type=topic_id,
                    supporting_evidence_ids=[item.evidence_id for item in items],
                )
            )
        return ExtractionResult(claims=claims)
