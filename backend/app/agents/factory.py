"""Wires up the Milestone 1 default agent: all fixture-backed / rule-based
concrete implementations behind the provider-independent interfaces.

This is the one place that knows about concrete implementations; the API
layer and tests depend only on this factory (or inject their own
implementations directly for isolated unit tests).
"""

from __future__ import annotations

from app.agents.location_research_agent import LocationResearchAgent
from app.core.config import AgentConfig
from app.evidence.repository import InMemoryEvidenceRepository
from app.planning.planner import KeywordResearchPlanner
from app.retrieval.keyword_retriever import KeywordEvidenceRetriever
from app.synthesis.claim_extractor import FixtureClaimExtractor
from app.synthesis.synthesizer import TemplateSynthesizer
from app.tools.fixture_tools import FixtureLocationResolver, FixturePageRetrievalTool, FixtureWebSearchTool
from app.verification.verifier import EvidenceBasedClaimVerifier


def build_default_agent(config: AgentConfig | None = None) -> LocationResearchAgent:
    return LocationResearchAgent(
        location_resolver=FixtureLocationResolver(),
        web_search_tool=FixtureWebSearchTool(),
        page_retrieval_tool=FixturePageRetrievalTool(),
        planner=KeywordResearchPlanner(),
        retriever=KeywordEvidenceRetriever(),
        evidence_repository=InMemoryEvidenceRepository(),
        claim_extractor=FixtureClaimExtractor(),
        verifier=EvidenceBasedClaimVerifier(),
        synthesizer=TemplateSynthesizer(),
        config=config,
    )
