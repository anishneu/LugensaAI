"""Wires up the default agent: concrete implementations behind the
provider-independent interfaces.

With no API keys and no optional packages installed, this returns the exact
Milestone 1 agent: fixture-backed tools, rule-based planning, fixture-
annotated claim extraction, template-based synthesis, keyword-only
retrieval, in-process evidence storage backed by a local SQLite file. Zero
network calls, zero API cost.

Setting `ANTHROPIC_API_KEY` swaps the planner, claim extractor, and
synthesizer for their LLM-backed Milestone 2 counterparts. Setting
`TAVILY_API_KEY` swaps the web search and page retrieval tools for their
live Milestone 3 counterparts. Either can be set independently, but real
search without an LLM key means evidence is collected without being turned
into claims — `FixtureClaimExtractor` can't extract from real page text
(see backend/README.md) — so `build_default_agent()` logs nothing special
for that combination, it's just an honest, documented limitation rather
than something the factory tries to paper over. Having `sentence-transformers`
installed enables hybrid (keyword + semantic) retrieval automatically
(Milestone 4); `DISABLE_SEMANTIC_RETRIEVAL=1` forces keyword-only regardless.

Every LLM-backed component falls back to its Milestone 1 equivalent on any
failure, so a flaky API call degrades a run rather than crashing it. This is
the one place that knows about concrete implementations; the API layer and
most tests depend only on this factory (or inject their own implementations
directly for isolated unit tests).
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path

from app.agents.location_research_agent import LocationResearchAgent
from app.core.config import (
    TAVILY_API_KEY_ENV_VAR,
    TAVILY_MAX_RESULTS,
    AgentConfig,
    evidence_db_path,
    llm_enabled,
    search_enabled,
    semantic_retrieval_enabled,
)
from app.core.llm_service import AnthropicLLMService, LLMService
from app.evidence.repository import EvidenceRepository
from app.evidence.sqlite_repository import SQLiteEvidenceRepository
from app.planning.llm_planner import LLMResearchPlanner
from app.planning.planner import KeywordResearchPlanner, ResearchPlanner
from app.retrieval.base import EvidenceRetriever
from app.retrieval.hybrid_retriever import HybridEvidenceRetriever
from app.retrieval.keyword_retriever import KeywordEvidenceRetriever
from app.retrieval.semantic_retriever import SemanticEvidenceRetriever
from app.synthesis.claim_extractor import ClaimExtractor, FixtureClaimExtractor
from app.synthesis.llm_claim_extractor import LLMClaimExtractor
from app.synthesis.llm_synthesizer import LLMSynthesizer
from app.synthesis.synthesizer import Synthesizer, TemplateSynthesizer
from app.tools.base import PageRetrievalTool, WebSearchTool
from app.tools.fixture_tools import FixtureLocationResolver, FixturePageRetrievalTool, FixtureWebSearchTool
from app.tools.tavily_tools import TavilyPageRetrievalTool, TavilyWebSearchTool
from app.verification.verifier import EvidenceBasedClaimVerifier


def build_default_agent(
    config: AgentConfig | None = None,
    use_llm: bool | None = None,
    use_live_search: bool | None = None,
    use_semantic_retrieval: bool | None = None,
    db_path: Path | None = None,
) -> LocationResearchAgent:
    """Build the default agent.

    Every `use_*=None` (default) auto-detects from the environment; pass
    True/False to override. `db_path=None` uses the real project evidence
    database (`EVIDENCE_DB_PATH`, see app/core/config.py); a fresh, unique
    `run_id` is generated per call either way, so concurrent/successive runs
    never see each other's evidence.
    """
    if use_llm is None:
        use_llm = llm_enabled()
    if use_live_search is None:
        use_live_search = search_enabled()
    if use_semantic_retrieval is None:
        use_semantic_retrieval = semantic_retrieval_enabled()

    planner: ResearchPlanner
    claim_extractor: ClaimExtractor
    synthesizer: Synthesizer

    if use_llm:
        llm: LLMService = AnthropicLLMService()
        planner = LLMResearchPlanner(llm, fallback=KeywordResearchPlanner())
        claim_extractor = LLMClaimExtractor(llm, fallback=FixtureClaimExtractor())
        synthesizer = LLMSynthesizer(llm, fallback=TemplateSynthesizer())
    else:
        planner = KeywordResearchPlanner()
        claim_extractor = FixtureClaimExtractor()
        synthesizer = TemplateSynthesizer()

    web_search_tool: WebSearchTool
    page_retrieval_tool: PageRetrievalTool

    if use_live_search:
        tavily_search = TavilyWebSearchTool(
            api_key=os.environ.get(TAVILY_API_KEY_ENV_VAR), max_results=TAVILY_MAX_RESULTS
        )
        web_search_tool = tavily_search
        page_retrieval_tool = TavilyPageRetrievalTool(tavily_search.raw_content_cache)
    else:
        web_search_tool = FixtureWebSearchTool()
        page_retrieval_tool = FixturePageRetrievalTool()

    retriever: EvidenceRetriever
    if use_semantic_retrieval:
        retriever = HybridEvidenceRetriever(KeywordEvidenceRetriever(), SemanticEvidenceRetriever())
    else:
        retriever = KeywordEvidenceRetriever()

    evidence_repository: EvidenceRepository = SQLiteEvidenceRepository(
        db_path=db_path or evidence_db_path(), run_id=str(uuid.uuid4())
    )

    return LocationResearchAgent(
        location_resolver=FixtureLocationResolver(),
        web_search_tool=web_search_tool,
        page_retrieval_tool=page_retrieval_tool,
        planner=planner,
        retriever=retriever,
        evidence_repository=evidence_repository,
        claim_extractor=claim_extractor,
        verifier=EvidenceBasedClaimVerifier(),
        synthesizer=synthesizer,
        config=config,
    )
