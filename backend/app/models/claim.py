from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class ClaimStatus(StrEnum):
    SUPPORTED = "supported"
    CONTRADICTED = "contradicted"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class Claim(BaseModel):
    """A discrete, checkable statement linked explicitly to its evidence.

    `status` is assigned only by the verifier, never by the component that
    proposes the claim text — a claim is never trusted until it has been
    checked against the evidence store.
    """

    claim_id: str
    text: str
    claim_type: str = Field(..., description="Matches a research topic id, e.g. 'transportation'")
    supporting_evidence_ids: list[str] = Field(default_factory=list)
    contradicting_evidence_ids: list[str] = Field(default_factory=list)
    status: ClaimStatus = ClaimStatus.INSUFFICIENT_EVIDENCE
    limitations: list[str] = Field(default_factory=list)
    check_wording: bool = Field(
        default=False,
        description="True for claims written by a model: the verifier then also requires the claim's words and "
        "figures to appear in the sources it cites, not merely that the cited ids exist.",
    )
