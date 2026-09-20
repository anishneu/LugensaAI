"""Wires up the default agent: concrete implementations behind the
provider-independent interfaces.

Nothing here is a stand-in for real data. With no keys set, the agent has no way to search or to
read a page, and every response says so in its limitations rather than serving invented sources:

- `TAVILY_API_KEY` turns on live web search and page retrieval.
- `OLLAMA_ENABLED` (free, local, needs Ollama installed; see backend/README.md) turns on the LLM
  planner, claim extractor, synthesizer, research reflection and local-language query writer.
  Without it the planner is rule-based and no claims are extracted, since claims can't be read out
  of real pages without a model.
- `GOOGLE_PLACES_API_KEY` adds Google as the first place resolver and a rating/summary card.
- Geocoding (OpenStreetMap), translation and semantic retrieval are on by default when their
  packages are installed, and off with `DISABLE_LIVE_GEOCODING`, `DISABLE_TRANSLATION` and
  `DISABLE_SEMANTIC_RETRIEVAL`.

Every LLM-backed component falls back to a rule-based or empty result on any failure, and says so, so
a flaky call degrades a run rather than crashing it. This is the one place that knows about concrete
implementations; the API layer depends only on this factory, and unit tests inject their own.
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path

from app.agents.reflection import LLMReflector, Reflector, RuleBasedReflector
from app.agents.location_research_agent import LocationResearchAgent
from app.core.config import (
    TAVILY_API_KEY_ENV_VAR,
    TAVILY_MAX_RESULTS,
    AgentConfig,
    evidence_db_path,
    GOOGLE_PLACES_API_KEY_ENV_VAR,
    geocoding_enabled,
    llm_enabled,
    place_profile_enabled,
    search_enabled,
    semantic_retrieval_enabled,
    translation_enabled,
)
from app.core.llm_service import LLMService, OllamaLLMService
from app.evidence.repository import EvidenceRepository
from app.evidence.sqlite_repository import SQLiteEvidenceRepository
from app.planning.llm_planner import LLMResearchPlanner
from app.planning.planner import KeywordResearchPlanner, ResearchPlanner
from app.retrieval.base import EvidenceRetriever
from app.retrieval.hybrid_retriever import HybridEvidenceRetriever
from app.retrieval.keyword_retriever import KeywordEvidenceRetriever
from app.retrieval.semantic_retriever import SemanticEvidenceRetriever
from app.synthesis.claim_extractor import ClaimExtractor, UnavailableClaimExtractor
from app.synthesis.llm_claim_extractor import LLMClaimExtractor
from app.synthesis.llm_synthesizer import LLMSynthesizer
from app.synthesis.synthesizer import Synthesizer, TemplateSynthesizer
from app.tools.base import LocationResolverTool, PageRetrievalTool, WebSearchTool
from app.tools.composite import FallbackLocationResolver
from app.tools.google_places_tool import GooglePlacesLocationResolver, GooglePlacesTool
from app.tools.unconfigured import UnconfiguredLocationResolver, UnconfiguredPageRetrievalTool, UnconfiguredWebSearchTool
from app.tools.nominatim_tool import NominatimLocationResolverTool
from app.tools.tavily_tools import TavilyPageRetrievalTool, TavilyWebSearchTool
from app.tools.post_dates import PostDateRecovery
from app.tools.translation import default_translator
from app.tools.wiki_tool import WikiContextTool
from app.tools.community_sources import community_domains, native_query, regional_domains
from app.tools.locale import LocaleResolver
from app.planning.local_queries import LLMLocalQueryWriter, LocalQueryWriter, RuleBasedLocalQueryWriter
from app.verification.verifier import EvidenceBasedClaimVerifier


def build_location_resolver(google: GooglePlacesTool | None, use_live_geocoding: bool) -> LocationResolverTool:
    """Google first when configured (it knows businesses and plus codes that OpenStreetMap doesn't), then
    OpenStreetMap. With neither, a resolver that says why it can't resolve."""
    live: list[LocationResolverTool] = []
    if google is not None:
        live.append(GooglePlacesLocationResolver(google))
    if use_live_geocoding:
        live.append(NominatimLocationResolverTool())
    if not live:
        return UnconfiguredLocationResolver()
    chain = live[-1]
    for resolver in reversed(live[:-1]):
        chain = FallbackLocationResolver(resolver, chain)
    return chain


def build_default_agent(
    config: AgentConfig | None = None,
    use_llm: bool | None = None,
    use_live_search: bool | None = None,
    use_semantic_retrieval: bool | None = None,
    use_live_geocoding: bool | None = None,
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
    if use_live_geocoding is None:
        use_live_geocoding = geocoding_enabled()

    planner: ResearchPlanner
    claim_extractor: ClaimExtractor
    synthesizer: Synthesizer

    if use_llm:
        llm: LLMService = OllamaLLMService()
        planner = LLMResearchPlanner(llm, fallback=KeywordResearchPlanner())
        claim_extractor = LLMClaimExtractor(llm)
        synthesizer = LLMSynthesizer(llm, fallback=TemplateSynthesizer())
    else:
        planner = KeywordResearchPlanner()
        claim_extractor = UnavailableClaimExtractor(
            "No language model is configured (set OLLAMA_ENABLED=1), so no claims were extracted from the "
            "evidence found; only the sources themselves are shown."
        )
        synthesizer = TemplateSynthesizer()

    # The research loop only makes sense against live sources: with no search configured there is
    # nothing to search again. The model decides what to do next when there is one; otherwise a
    # rule-based judge does.
    reflector: Reflector | None = None
    if use_live_search:
        reflector = LLMReflector(llm, fallback=RuleBasedReflector()) if use_llm else RuleBasedReflector()

    web_search_tool: WebSearchTool
    page_retrieval_tool: PageRetrievalTool
    community_search_tool: WebSearchTool | None = None
    regional_search_tool: WebSearchTool | None = None

    if use_live_search:
        # Real dates for forum and blog posts whose search result has none (URL, Reddit's feed, page metadata).
        date_recovery = PostDateRecovery()
        tavily_search = TavilyWebSearchTool(
            api_key=os.environ.get(TAVILY_API_KEY_ENV_VAR),
            max_results=TAVILY_MAX_RESULTS,
            translator=default_translator() if translation_enabled() else None,
            date_recovery=date_recovery,
        )
        web_search_tool = tavily_search
        page_retrieval_tool = TavilyPageRetrievalTool(tavily_search.raw_content_cache)
        # Same search, restricted to forums and communities, sharing the page cache and all the relevance filters.
        # The country's own forums ride along here only when there is no native name to search them by; otherwise
        # they get their own search below, in their own language.
        community_search_tool = TavilyWebSearchTool(
            api_key=os.environ.get(TAVILY_API_KEY_ENV_VAR),
            max_results=TAVILY_MAX_RESULTS,
            translator=default_translator() if translation_enabled() else None,
            include_domains_for=lambda place: community_domains(
                place.country_code, include_regional=not (native_query(place) and regional_domains(place.country_code))
            ),
            raw_content_cache=tavily_search.raw_content_cache,
            date_recovery=date_recovery,
        )
        regional_search_tool = TavilyWebSearchTool(
            api_key=os.environ.get(TAVILY_API_KEY_ENV_VAR),
            max_results=TAVILY_MAX_RESULTS,
            translator=default_translator() if translation_enabled() else None,
            include_domains_for=lambda place: regional_domains(place.country_code),
            raw_content_cache=tavily_search.raw_content_cache,
            date_recovery=date_recovery,
        )
    else:
        web_search_tool = UnconfiguredWebSearchTool()
        page_retrieval_tool = UnconfiguredPageRetrievalTool()

    retriever: EvidenceRetriever
    if use_semantic_retrieval:
        retriever = HybridEvidenceRetriever(KeywordEvidenceRetriever(), SemanticEvidenceRetriever())
    else:
        retriever = KeywordEvidenceRetriever()

    evidence_repository: EvidenceRepository = SQLiteEvidenceRepository(
        db_path=db_path or evidence_db_path(), run_id=str(uuid.uuid4())
    )

    place_profile_tool = (
        GooglePlacesTool(api_key=os.environ.get(GOOGLE_PLACES_API_KEY_ENV_VAR)) if place_profile_enabled() else None
    )

    location_resolver = build_location_resolver(place_profile_tool, use_live_geocoding)

    # Local-language search needs live search (there is nothing to search otherwise), the free translator
    # (the results must be readable) and reverse geocoding.
    locale_resolver: LocaleResolver | None = None
    local_query_writer: LocalQueryWriter | None = None
    if use_live_search and use_live_geocoding and translation_enabled():
        locale_resolver = LocaleResolver(google=place_profile_tool)
        local_query_writer = LLMLocalQueryWriter(llm) if use_llm else RuleBasedLocalQueryWriter()

    return LocationResearchAgent(
        location_resolver=location_resolver,
        web_search_tool=web_search_tool,
        page_retrieval_tool=page_retrieval_tool,
        planner=planner,
        retriever=retriever,
        evidence_repository=evidence_repository,
        claim_extractor=claim_extractor,
        verifier=EvidenceBasedClaimVerifier(),
        synthesizer=synthesizer,
        config=config,
        place_profile_tool=place_profile_tool,
        reflector=reflector,
        wiki_tool=WikiContextTool() if (use_live_search and use_live_geocoding) else None,
        locale_resolver=locale_resolver,
        local_query_writer=local_query_writer,
        community_search_tool=community_search_tool,
        regional_search_tool=regional_search_tool,
    )
