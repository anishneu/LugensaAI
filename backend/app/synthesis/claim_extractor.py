"""Claim extraction: turning evidence passages into discrete, linked claims.

Milestone 1 does not use an LLM to extract claims from free text. Instead,
each fixture document is pre-annotated with the claim it was written to
support (`metadata["claim_text"]`) — a stand-in for what an LLM-based
extractor would produce from real page text. `FixtureClaimExtractor` groups
evidence that supports the same claim text within a topic, which is how
multiple independent sources end up corroborating one claim.

This is an honest placeholder, not a hidden shortcut: real free-text claim
extraction (via an LLM, using the `LLMService` interface in
`app/core/llm_service.py`) is planned for Milestone 2.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.models.claim import Claim
from app.models.evidence import Evidence
from app.models.plan import ResearchPlan


class ClaimExtractor(ABC):
    @abstractmethod
    def extract(self, evidence: list[Evidence], plan: ResearchPlan) -> list[Claim]:
        raise NotImplementedError


class FixtureClaimExtractor(ClaimExtractor):
    def extract(self, evidence: list[Evidence], plan: ResearchPlan) -> list[Claim]:
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
        return claims
