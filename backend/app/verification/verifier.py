"""Claim verification: checking proposed claims against the evidence store.

This is the step that stops the pipeline from equating "a claim was
proposed" with "a claim is true." A claim's `status` is only ever set here,
never by the extractor or synthesizer.

Cross-source contradiction detection is out of scope for Milestone 1
(`contradicting_evidence_ids` is always empty) — flagged explicitly as a
limitation in the final response rather than silently omitted.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.core.config import AgentConfig
from app.models.claim import Claim, ClaimStatus
from app.models.evidence import Evidence


class ClaimVerifier(ABC):
    @abstractmethod
    def verify(self, claims: list[Claim], evidence_by_id: dict[str, Evidence], config: AgentConfig) -> list[Claim]:
        raise NotImplementedError


class EvidenceBasedClaimVerifier(ClaimVerifier):
    def verify(self, claims: list[Claim], evidence_by_id: dict[str, Evidence], config: AgentConfig) -> list[Claim]:
        verified: list[Claim] = []
        for claim in claims:
            supporting = [evidence_by_id[eid] for eid in claim.supporting_evidence_ids if eid in evidence_by_id]
            limitations: list[str] = []

            relevant = [e for e in supporting if (e.relevance_score or 0.0) >= config.min_relevance_score]
            if not relevant:
                status = ClaimStatus.INSUFFICIENT_EVIDENCE
                limitations.append("No supporting evidence met the minimum relevance threshold.")
            else:
                status = ClaimStatus.SUPPORTED
                stale = [
                    e for e in relevant if e.recency_days is not None and e.recency_days > config.stale_evidence_days
                ]
                if stale:
                    limitations.append(
                        f"{len(stale)} of {len(relevant)} supporting source(s) are older than "
                        f"{config.stale_evidence_days} days and may be outdated."
                    )

            verified.append(claim.model_copy(update={"status": status, "limitations": limitations}))
        return verified
