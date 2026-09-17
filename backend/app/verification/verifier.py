"""Claim verification: checking proposed claims against the evidence store.

This is the step that stops the pipeline from equating "a claim was
proposed" with "a claim is true." A claim's `status` is only ever set here,
never by the extractor or synthesizer — and this class is never LLM-backed,
regardless of which other components are (see docs/research-workflow.md).

Verification has two passes: first each claim is checked independently
against its own supporting evidence (relevance, staleness); then claims that
passed that check are compared pairwise, within the same topic, for
contradictions (Milestone 6) — see `app/verification/contradiction.py` for
what that detector can and can't catch.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from itertools import combinations

from app.core.config import AgentConfig
from app.models.claim import Claim, ClaimStatus
from app.models.evidence import Evidence
from app.verification.contradiction import claims_contradict


class ClaimVerifier(ABC):
    @abstractmethod
    def verify(self, claims: list[Claim], evidence_by_id: dict[str, Evidence], config: AgentConfig) -> list[Claim]:
        raise NotImplementedError


class EvidenceBasedClaimVerifier(ClaimVerifier):
    def verify(self, claims: list[Claim], evidence_by_id: dict[str, Evidence], config: AgentConfig) -> list[Claim]:
        checked = [self._check_evidence(claim, evidence_by_id, config) for claim in claims]
        return self._check_contradictions(checked)

    @staticmethod
    def _check_evidence(claim: Claim, evidence_by_id: dict[str, Evidence], config: AgentConfig) -> Claim:
        supporting = [evidence_by_id[eid] for eid in claim.supporting_evidence_ids if eid in evidence_by_id]
        limitations: list[str] = []

        relevant = [e for e in supporting if (e.relevance_score or 0.0) >= config.min_relevance_score]
        if not relevant:
            status = ClaimStatus.INSUFFICIENT_EVIDENCE
            limitations.append("No supporting evidence met the minimum relevance threshold.")
        else:
            status = ClaimStatus.SUPPORTED
            stale = [e for e in relevant if e.recency_days is not None and e.recency_days > config.stale_evidence_days]
            if stale:
                limitations.append(
                    f"{len(stale)} of {len(relevant)} supporting source(s) are older than "
                    f"{config.stale_evidence_days} days and may be outdated."
                )

        return claim.model_copy(update={"status": status, "limitations": limitations})

    @staticmethod
    def _check_contradictions(claims: list[Claim]) -> list[Claim]:
        contradicting_ids: dict[str, set[str]] = {claim.claim_id: set() for claim in claims}

        by_topic: dict[str, list[Claim]] = {}
        for claim in claims:
            if claim.status == ClaimStatus.SUPPORTED:
                by_topic.setdefault(claim.claim_type, []).append(claim)

        for topic_claims in by_topic.values():
            for claim_a, claim_b in combinations(topic_claims, 2):
                if claims_contradict(claim_a.text, claim_b.text):
                    contradicting_ids[claim_a.claim_id].update(claim_b.supporting_evidence_ids)
                    contradicting_ids[claim_b.claim_id].update(claim_a.supporting_evidence_ids)

        result: list[Claim] = []
        for claim in claims:
            contradictors = contradicting_ids[claim.claim_id]
            if not contradictors:
                result.append(claim)
                continue
            result.append(
                claim.model_copy(
                    update={
                        "status": ClaimStatus.CONTRADICTED,
                        "contradicting_evidence_ids": sorted(contradictors),
                        "limitations": [
                            *claim.limitations,
                            "This claim appears to contradict another claim about the same topic; both are "
                            "marked contradicted rather than one being assumed correct.",
                        ],
                    }
                )
            )
        return result
