"""LocationResearchAgent: orchestrates the full research lifecycle.

    INPUT
      -> LOCATION RESOLUTION
      -> QUESTION UNDERSTANDING / RESEARCH PLANNING
      -> TOOL SELECTION -> RETRIEVAL -> EVIDENCE PROCESSING   (per topic, bounded)
      -> COVERAGE CHECK
      -> CLAIM EXTRACTION
      -> CLAIM VERIFICATION
      -> SYNTHESIS
      -> FINAL RESPONSE

Claim verification always runs *before* synthesis, never after — this is
deliberate and unchanged by Milestone 2's LLM-backed components. An LLM may
now draft the extraction (`LLMClaimExtractor`) or the final prose
(`LLMSynthesizer`), but it never gets to draft a full answer that is then
checked after the fact: `ClaimVerifier` is a fixed, non-LLM gate that every
claim must pass before `Synthesizer` (LLM-backed or not) ever sees it. See
docs/research-workflow.md for the full reasoning.

Every external tool call is counted against `AgentConfig.max_tool_calls` so
the loop is guaranteed to terminate.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from app.core.config import AgentConfig
from app.evidence.processing import enrich_evidence
from app.evidence.repository import EvidenceRepository
from app.models.claim import ClaimStatus
from app.models.evidence import Evidence
from app.models.location import Location
from app.models.response import ResearchResponse
from app.models.trace import ResearchTraceStep, TraceStage
from app.planning.planner import ResearchPlanner
from app.retrieval.base import EvidenceRetriever
from app.synthesis.claim_extractor import ClaimExtractor
from app.synthesis.synthesizer import Synthesizer
from app.evidence.place_profile_evidence import pick_topic, profile_to_evidence
from app.tools.base import LocationResolverTool, PageRetrievalTool, ToolExecutionError, WebSearchTool
from app.tools.google_places_tool import GooglePlacesTool
from app.tools.translation import META_ORIGINAL_TEXT
from app.verification.verifier import ClaimVerifier

# Caps concurrent outbound searches. Bounded because the far end is a rate-
# limited third-party API, not because of local CPU.
_MAX_SEARCH_WORKERS = 4


class LocationResearchAgent:
    def __init__(
        self,
        location_resolver: LocationResolverTool,
        web_search_tool: WebSearchTool,
        page_retrieval_tool: PageRetrievalTool,
        planner: ResearchPlanner,
        retriever: EvidenceRetriever,
        evidence_repository: EvidenceRepository,
        claim_extractor: ClaimExtractor,
        verifier: ClaimVerifier,
        synthesizer: Synthesizer,
        config: AgentConfig | None = None,
        place_profile_tool: GooglePlacesTool | None = None,
    ) -> None:
        self.location_resolver = location_resolver
        self.web_search_tool = web_search_tool
        self.page_retrieval_tool = page_retrieval_tool
        self.planner = planner
        self.retriever = retriever
        self.evidence_repository = evidence_repository
        self.claim_extractor = claim_extractor
        self.verifier = verifier
        self.synthesizer = synthesizer
        self.config = config or AgentConfig()
        self.place_profile_tool = place_profile_tool

    def run(self, raw_location: str | Location, question: str) -> ResearchResponse:
        """Run the full research lifecycle and always release the evidence
        repository's resources afterward (e.g. closing a SQLite connection),
        even if location resolution or a later stage raises.

        `raw_location` is usually a string resolved via `location_resolver`.
        Passing an already-resolved `Location` instead skips resolution
        entirely — used when the caller already committed to one specific
        place (e.g. the user picked one exact POI candidate from a live
        search): re-resolving its name as a fresh text query could, in
        principle, land on a *different* same-named place nearby (a
        different branch of the same chain), which would silently research
        the wrong location.
        """
        try:
            return self._run(raw_location, question)
        finally:
            self.evidence_repository.close()

    def _lookup_place_profile(
        self, location: Location, plan, limitations: list[str], log
    ) -> list[Evidence]:
        """Google Maps rating, hours and reviews for a specific business, as
        evidence. Every failure mode is recorded as a limitation, never hidden."""
        if not location.is_business or location.latitude is None or location.longitude is None:
            return []
        if self.place_profile_tool is None:
            limitations.append(
                "Google Maps ratings and reviews are not connected (set GOOGLE_PLACES_API_KEY), so review "
                "coverage for this business comes only from what the open web surfaced."
            )
            return []

        topic_id = pick_topic([t.topic_id for t in plan.topics])
        if topic_id is None:
            return []
        try:
            profile = self.place_profile_tool.lookup(
                location.name, location.latitude, location.longitude, location.city or ""
            )
        except ToolExecutionError as exc:
            limitations.append(f"The Google Maps lookup failed ({exc}); its reviews are not included.")
            return []
        if profile is None:
            limitations.append("No matching Google Maps listing was found within a few hundred meters of this pin.")
            return []

        evidence = profile_to_evidence(
            profile, topic_id, f"{location.city}, {location.region}", datetime.now(timezone.utc)
        )
        log(
            TraceStage.TOOL_SELECTION,
            f"Added Google Maps listing for '{profile.name}' ({len(profile.reviews)} review(s) of "
            f"{profile.review_count or 'unknown'} total) as evidence for '{topic_id}'",
        )
        return evidence

    def _run(self, raw_location: str | Location, question: str) -> ResearchResponse:
        trace: list[ResearchTraceStep] = []
        tool_calls_made = 0

        def log(stage: TraceStage, description: str, **details: object) -> None:
            trace.append(
                ResearchTraceStep(
                    stage=stage,
                    description=description,
                    timestamp=datetime.now(timezone.utc),
                    details={k: str(v) for k, v in details.items()},
                )
            )

        if isinstance(raw_location, Location):
            location = raw_location
            log(
                TraceStage.LOCATION_RESOLUTION,
                f"Using pre-resolved location {location.name}, {location.city}, {location.region}",
                slug=location.slug,
            )
        else:
            location = self.location_resolver.resolve(raw_location)
            log(
                TraceStage.LOCATION_RESOLUTION,
                f"Resolved '{raw_location}' to {location.name}, {location.city}, {location.region}",
                slug=location.slug,
            )

        plan = self.planner.plan(location, question)
        log(
            TraceStage.QUESTION_UNDERSTANDING,
            f"Detected intent(s): {', '.join(plan.detected_intents) or 'none'}",
        )
        log(
            TraceStage.RESEARCH_PLANNING,
            f"Planned {len(plan.topics)} topic(s): {', '.join(t.topic_id for t in plan.topics)}",
        )

        limitations: list[str] = list(plan.notes)
        profile_evidence = self._lookup_place_profile(location, plan, limitations, log)

        searchable_topics = []
        for topic in plan.topics:
            if tool_calls_made + len(searchable_topics) >= self.config.max_tool_calls:
                limitations.append(f"Research budget exhausted before investigating topic '{topic.topic_id}'.")
                log(TraceStage.COVERAGE_CHECK, f"Skipped topic '{topic.topic_id}': tool call budget exhausted.")
                continue
            searchable_topics.append(topic)

        for topic in searchable_topics:
            log(
                TraceStage.TOOL_SELECTION,
                f"Selected WebSearchTool for topic '{topic.topic_id}'",
                queries="; ".join(topic.search_queries),
            )

        # Each topic's search is an independent network round trip, so running
        # them concurrently collapses N sequential API waits into roughly one.
        # Only the searches are parallel: everything downstream (scoring,
        # enrichment, and especially the evidence repository, whose SQLite
        # connection is not thread-safe) stays on this thread, in topic order,
        # so results remain deterministic.
        if searchable_topics:
            with ThreadPoolExecutor(max_workers=min(len(searchable_topics), _MAX_SEARCH_WORKERS)) as pool:
                candidates_per_topic = list(pool.map(lambda t: self.web_search_tool.search(location, t), searchable_topics))
            tool_calls_made += len(searchable_topics)
        else:
            candidates_per_topic = []

        for topic, candidates in zip(searchable_topics, candidates_per_topic):
            if not candidates:
                log(
                    TraceStage.ADDITIONAL_RESEARCH,
                    f"No candidate sources found for '{topic.topic_id}'; nothing further to fetch in this run.",
                )

            scored = self.retriever.score(candidates, topic.search_queries)
            log(TraceStage.RETRIEVAL, f"Scored {len(scored)} candidate(s) for '{topic.topic_id}'")

            accepted_candidates = [e for e in scored if (e.relevance_score or 0.0) >= self.config.min_relevance_score]
            accepted_candidates = accepted_candidates[: self.config.max_evidence_per_topic]

            enriched: list[Evidence] = []
            for candidate in accepted_candidates:
                if tool_calls_made >= self.config.max_tool_calls:
                    limitations.append(
                        f"Research budget exhausted while fetching full text for topic '{topic.topic_id}'."
                    )
                    break
                full_text = self.page_retrieval_tool.retrieve_full_text(candidate.source_url)
                tool_calls_made += 1
                # A translated snippet must not be overwritten by the page's
                # full text, which is still in the original language.
                if full_text and META_ORIGINAL_TEXT not in candidate.metadata:
                    candidate = candidate.model_copy(update={"text": full_text})
                enriched.append(enrich_evidence(candidate))

            self.evidence_repository.add_all(enriched)
            log(
                TraceStage.EVIDENCE_PROCESSING,
                f"Accepted {len(enriched)} evidence item(s) for '{topic.topic_id}'",
                rejected=len(scored) - len(enriched),
            )

        if profile_evidence:
            self.evidence_repository.add_all([enrich_evidence(item) for item in profile_evidence])

        if location.is_business:
            web_sources = sum(1 for e in self.evidence_repository.list_all() if e.metadata.get("provider") != "google_places")
            if web_sources < 3:
                limitations.append(
                    f"Only {web_sources} web page(s) mention this specific business, so coverage of it is thin — "
                    "far less than a place's own Google Maps listing typically has."
                )

        all_evidence = self.evidence_repository.list_all()
        evidence_topic_ids = {e.topic for e in all_evidence}
        missing_topics = [t.topic_id for t in plan.topics if t.topic_id not in evidence_topic_ids]
        if missing_topics:
            log(TraceStage.COVERAGE_CHECK, f"No evidence found for: {', '.join(missing_topics)}")
        else:
            log(TraceStage.COVERAGE_CHECK, "Evidence was found for every planned topic.")

        extraction = self.claim_extractor.extract(all_evidence, plan)
        claims = extraction.claims
        limitations.extend(extraction.notes)
        log(TraceStage.CLAIM_EXTRACTION, f"Extracted {len(claims)} claim(s) from {len(all_evidence)} evidence item(s)")

        evidence_by_id = {e.evidence_id: e for e in all_evidence}
        verified_claims = self.verifier.verify(claims, evidence_by_id, self.config)
        log(
            TraceStage.CLAIM_VERIFICATION,
            f"Verified {len(verified_claims)} claim(s)",
            supported=sum(1 for c in verified_claims if c.status == ClaimStatus.SUPPORTED),
        )

        synthesis = self.synthesizer.synthesize(
            location, question, plan, verified_claims, all_evidence, evidence_topic_ids
        )
        log(TraceStage.SYNTHESIS, "Generated summary and recommendation from verified claims and evidence")

        limitations.extend(synthesis.limitations)
        seen: set[str] = set()
        unique_limitations = [item for item in limitations if not (item in seen or seen.add(item))]

        return ResearchResponse(
            location=location,
            question=question,
            summary=synthesis.summary,
            key_findings=synthesis.key_findings,
            details=synthesis.details,
            recommendation=synthesis.recommendation,
            topics=plan.topics,
            claims=verified_claims,
            evidence=all_evidence,
            limitations=unique_limitations,
            research_trace=trace,
        )
