"""Claim extraction: turning evidence passages into discrete, linked claims.

`LLMClaimExtractor` (app/synthesis/llm_claim_extractor.py) reads real evidence text with a local model.
Without one, `UnavailableClaimExtractor` produces no claims and says so. There is deliberately no
extractor that returns pre-written claims: those existed as test fixtures and were removed from the
product because they could present invented statements as research.
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

    `notes` surfaces things like "the LLM extractor failed and no claims were
    extracted" so degraded runs are visible in the
    final response's limitations rather than silently indistinguishable from
    a fully-successful one.
    """

    claims: list[Claim]
    notes: list[str] = field(default_factory=list)


class ClaimExtractor(ABC):
    @abstractmethod
    def extract(self, evidence: list[Evidence], plan: ResearchPlan) -> ExtractionResult:
        raise NotImplementedError


class UnavailableClaimExtractor(ClaimExtractor):
    """Used when there is no language model: claims can't be read out of real pages without one, so
    none are produced, and the response says why. It never invents a claim."""

    def __init__(self, reason: str) -> None:
        self._reason = reason

    def extract(self, evidence: list[Evidence], plan: ResearchPlan) -> ExtractionResult:
        return ExtractionResult(claims=[], notes=[self._reason])
