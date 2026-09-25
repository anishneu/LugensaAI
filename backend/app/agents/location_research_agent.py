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

import re
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from urllib.parse import urlparse

from app.core.config import AgentConfig
from app.evidence.processing import enrich_evidence
from app.evidence.repository import EvidenceRepository
from app.models.claim import ClaimStatus
from app.models.evidence import Evidence, SourceType
from app.models.location import Location
from app.models.place_profile import PlaceProfile
from app.models.response import ResearchResponse
from app.models.trace import ResearchTraceStep, TraceStage
from app.planning.planner import ResearchPlanner
from app.retrieval.base import EvidenceRetriever
from app.synthesis.claim_extractor import ClaimExtractor
from app.synthesis.synthesizer import Synthesizer
from app.agents.reflection import Reflector
from app.planning.local_queries import LocalQueryWriter
from app.tools.community_sources import base_name, community_query, native_query, regional_domains
from app.tools.locale import LocaleResolver
from app.evidence.place_profile_evidence import pick_topic, profile_to_evidence
from app.tools.base import LocationResolverTool, PageRetrievalTool, ToolExecutionError, WebSearchTool
from app.tools.google_places_tool import GooglePlacesTool
from app.tools.translation import META_ORIGINAL_TEXT
from app.tools.wiki_tool import WikiContextTool
from app.tools.wikidata_names import WikidataNameVariants
from app.verification.support import untraceable_sentences
from app.verification.verifier import ClaimVerifier

# Caps concurrent outbound searches. Bounded because the far end is a rate-
# limited third-party API, not because of local CPU.
_MAX_SEARCH_WORKERS = 4

# At most this many of the sources kept for one topic may come from the same site, unless too few sites are left to fill it.
_MAX_PER_SITE = 2
_SECOND_LEVEL_LABELS = frozenset({"co", "com", "org", "net", "gov", "edu", "ac"})


def _site_of(url: str) -> str:
    """The site a URL belongs to, so "ca.trip.com" and "www.trip.com" count as one: its last two labels ("bbc.co.uk": three)."""
    labels = (urlparse(url).hostname or "").lower().split(".")
    keep = 3 if len(labels) >= 3 and labels[-2] in _SECOND_LEVEL_LABELS else 2
    return ".".join(labels[-keep:])


# Social networks and video sites are classed as community sources, but a post or a video there is rarely something to read
# (mostly behind a login); a forum thread is. Within the community search, threads come first.
_SOCIAL_SITES = frozenset({"facebook.com", "instagram.com", "tiktok.com", "youtube.com", "x.com", "twitter.com"})


def _community_rank(item: Evidence) -> int:
    """0 for a forum thread (Reddit, a country's forum), 1 for a social or video post, 2 for anything else."""
    if item.source_type != SourceType.COMMUNITY_FORUM:
        return 2
    return 1 if _site_of(item.source_url) in _SOCIAL_SITES else 0


def _spread_across_sites(items: list[Evidence], limit: int) -> list[Evidence]:
    """The best `limit` items, but no more than `_MAX_PER_SITE` from one site while others remain (the list is already in
    order of preference). Without it, four listings from one travel site can fill a topic and leave out a Reddit thread that
    scored just below them, which is what Community Voices then has nothing of."""
    chosen: list[Evidence] = []
    overflow: list[Evidence] = []
    per_site: dict[str, int] = {}
    for item in items:
        site = _site_of(item.source_url)
        if len(chosen) < limit and per_site.get(site, 0) < _MAX_PER_SITE:
            chosen.append(item)
            per_site[site] = per_site.get(site, 0) + 1
        else:
            overflow.append(item)
    return chosen + overflow[: max(0, limit - len(chosen))]



# How close a listed place must be to an address pin to be taken as what stands there.
_ADDRESS_VENUE_RADIUS_M = 60.0


def _names_something(question: str) -> bool:
    """Whether a question looks like it names a place or business: a capitalized word that does not merely
    start a sentence (and is not "I")."""
    for sentence in re.split(r"[.?!]+", question):
        words = sentence.replace(",", " ").split()
        if any(w[:1].isupper() and w not in {"I", "I'm", "I'd", "I've", "I'll"} for w in words[1:]):
            return True
    return False


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
        reflector: Reflector | None = None,
        wiki_tool: WikiContextTool | None = None,
        locale_resolver: LocaleResolver | None = None,
        local_query_writer: LocalQueryWriter | None = None,
        community_search_tool: WebSearchTool | None = None,
        regional_search_tool: WebSearchTool | None = None,
        reddit_archive_tool: WebSearchTool | None = None,
        name_variants_tool: WikidataNameVariants | None = None,
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
        # Optional: without a reflector the run is the single fixed pass (no live search
        # configured means there is nothing to search again).
        self.reflector = reflector
        self.wiki_tool = wiki_tool
        # Optional, for research outside English-speaking countries: also search in the local language.
        self.locale_resolver = locale_resolver
        self.local_query_writer = local_query_writer
        # Forums, Reddit, Quora and regional communities: what people say, as opposed to what pages say.
        self.community_search_tool = community_search_tool
        # The country's own forums (PTT, Dcard, Naver, ...) searched in their own language, by the place's native name.
        self.regional_search_tool = regional_search_tool
        # Reddit's own archive, searched by words in a post's title: free, and not a sample the way a web search is.
        self.reddit_archive_tool = reddit_archive_tool
        # Other English spellings of the place's name (Wikidata), for matching pages and searching the archive.
        self.name_variants_tool = name_variants_tool

    def _add_name_variants(self, location: Location, log) -> Location:
        """Other English names of the place (Wikidata), so a page or post that spells it differently still counts.
        Best effort: nothing found, or any failure, leaves the location as it was."""
        if self.name_variants_tool is None:
            return location
        try:
            found = self.name_variants_tool.variants(base_name(location.name), location.latitude, location.longitude)
        except Exception:  # noqa: BLE001 - a name lookup must never stop a research run
            return location
        variants = [v for v in found if base_name(v).lower() != base_name(location.name).lower()]
        if not variants:
            return location
        log(TraceStage.LOCATION_RESOLUTION, f"Wikidata lists other names for this place: {', '.join(variants)}")
        return location.model_copy(update={"name_variants": variants})

    def _regional_is_separate(self, location: Location) -> bool:
        """Whether the country's forums get their own local-language search instead of riding along in the English one."""
        return bool(
            self.regional_search_tool is not None
            and native_query(location)
            and regional_domains(location.country_code)
        )

    def run(
        self,
        raw_location: str | Location,
        question: str,
        on_step: Callable[[ResearchTraceStep], None] | None = None,
    ) -> ResearchResponse:
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

        `on_step`, when given, is called with each trace step the moment it is recorded, so a caller can show progress
        while the run is still going. It never changes the run: an exception it raises is swallowed.
        """
        try:
            return self._run(raw_location, question, on_step)
        finally:
            self.evidence_repository.close()

    def _lookup_place_profile(
        self, location: Location, plan, limitations: list[str], log
    ) -> tuple[list[Evidence], PlaceProfile | None]:
        """Google Maps rating, hours and reviews for a specific business, as
        evidence. Every failure mode is recorded as a limitation, never hidden.

        A pin that is not a business (a temple or a museum picked from search, which Google lists as an attraction)
        is looked up too, quietly and only on an exact name match, so a tourist question about it gets Google's
        rating and reviews as well. An area never matches, and nothing is said about it when nothing does."""
        if location.latitude is None or location.longitude is None:
            return [], None
        if not location.is_business:
            return self._lookup_landmark_profile(location, plan, log)
        if self.place_profile_tool is None:
            limitations.append(
                "Google Maps ratings and reviews are not connected (set GOOGLE_PLACES_API_KEY), so review "
                "coverage for this business comes only from what the open web surfaced."
            )
            return [], None

        topic_id = pick_topic([t.topic_id for t in plan.topics])
        if topic_id is None:
            return [], None
        try:
            profile = self.place_profile_tool.lookup(
                location.name, location.latitude, location.longitude, location.city or ""
            )
        except ToolExecutionError as exc:
            limitations.append(f"The Google Maps lookup failed ({exc}); its reviews are not included.")
            return [], None
        if profile is None:
            limitations.append("No matching Google Maps listing was found within a few hundred meters of this pin.")
            return [], None

        evidence = profile_to_evidence(
            profile, topic_id, f"{location.city}, {location.region}", datetime.now(timezone.utc)
        )
        log(
            TraceStage.TOOL_SELECTION,
            f"Added Google Maps listing for '{profile.name}' ({len(profile.reviews)} review(s) of "
            f"{profile.review_count or 'unknown'} total) as evidence for '{topic_id}'",
        )
        return evidence, profile

    def _lookup_landmark_profile(self, location: Location, plan, log) -> tuple[list[Evidence], PlaceProfile | None]:
        """Google's listing for a pin that is a named place but not a business, on an exact name match only."""
        if self.place_profile_tool is None or location.is_address:
            return [], None
        topic_id = pick_topic([t.topic_id for t in plan.topics])
        if topic_id is None:
            return [], None
        try:
            profile = self.place_profile_tool.lookup(
                location.name, location.latitude, location.longitude, location.city or "", exact=True
            )
        except ToolExecutionError:
            return [], None
        if profile is None:
            return [], None
        evidence = profile_to_evidence(
            profile, topic_id, f"{location.city}, {location.region}", datetime.now(timezone.utc)
        )
        log(
            TraceStage.TOOL_SELECTION,
            f"Added Google Maps listing for '{profile.name}' ({len(profile.reviews)} review(s) of "
            f"{profile.review_count or 'unknown'} total) as evidence for '{topic_id}'",
        )
        return evidence, profile

    def _adopt_business_at_address(self, location: Location, limitations: list[str], log) -> Location:
        """A street address usually means the business standing at it.

        Someone who pastes "Unterer Graben 11" and asks "how is the cafe at this location?" wants
        Cafe Pustekuchen. The geocoder only knows a building, so without this the agent researched
        an anonymous address and never asked Google about the cafe (4.7 stars, 126 reviews) that was
        right there. When Google lists a business within 40 m of an address pin, that business
        becomes the subject, and the response says so."""
        if (
            not location.is_address
            or location.is_business
            or self.place_profile_tool is None
            or location.latitude is None
            or location.longitude is None
        ):
            return location
        try:
            # Landmarks count as well as shops: the address of Ginkaku-ji is a temple, which Google lists as a tourist
            # attraction, not a business, and it has the ratings and reviews a tourist question is after. Most popular
            # first: by distance the nearest "places" at that address were a hand basin and the abbot's quarters, which
            # are parts of the temple, and the temple itself (18 m away) came after them.
            venues = self.place_profile_tool.venues_at(
                location.latitude,
                location.longitude,
                radius_m=_ADDRESS_VENUE_RADIUS_M,
                rank="POPULARITY",
                businesses_only=False,
            )
        except ToolExecutionError as exc:
            limitations.append(f"Could not check whether a business stands at this address ({exc}).")
            return location
        if not venues:
            return location

        venue = venues[0]
        others = [v.name for v in venues[1:]]
        limitations.append(
            f"This is a street address; Google Maps lists {venue.name} there, so it was researched as that business."
            + (f" Other places at the same address: {', '.join(others)}." if others else "")
        )
        log(
            TraceStage.LOCATION_RESOLUTION,
            f"Address matched to the business '{venue.name}' listed there on Google Maps",
            others=", ".join(others) or "none",
        )
        return location.model_copy(
            update={
                "name": venue.name,
                "is_business": True,
                "is_address": False,
                "latitude": venue.latitude,
                "longitude": venue.longitude,
                "city": location.city or venue.city,
                "region": location.region or venue.region,
                "country": location.country or venue.country,
            }
        )

    def _adopt_venue_named_in_question(self, location: Location, question: str, limitations: list[str], log) -> Location:
        """The question names a business that stands near the pin: research that business.

        A pin dropped on "Hunts Bank & Victoria Station Approach" is not a business, so Google Maps was never
        asked about the arena beside it, however plainly the question said "the reviews of this AO Arena".
        When Google lists a business within a few hundred meters whose whole distinguishing name is in the
        question, that business becomes the subject (its ratings and reviews are fetched, and the response
        says so). Only asked when the question looks like it names something, to spare the API call."""
        if (
            location.is_business
            or self.place_profile_tool is None
            or location.latitude is None
            or location.longitude is None
            or not _names_something(question)
        ):
            return location
        try:
            venue = self.place_profile_tool.venue_named_in(question, location.latitude, location.longitude)
        except ToolExecutionError as exc:
            limitations.append(f"Could not check Google Maps for a business named in the question ({exc}).")
            return location
        if venue is None:
            return location

        limitations.append(
            f"The question names {venue.name}, which Google Maps lists near this pin, so it was researched as that "
            "business, with its Google Maps ratings and reviews."
        )
        log(TraceStage.LOCATION_RESOLUTION, f"Question names '{venue.name}', a business listed near the pin on Google Maps")
        return location.model_copy(
            update={
                "name": venue.name,
                "is_business": True,
                "is_address": False,
                "latitude": venue.latitude,
                "longitude": venue.longitude,
                "city": location.city or venue.city,
                "region": location.region or venue.region,
                "country": location.country or venue.country,
            }
        )

    def _add_local_language(self, location: Location, plan, limitations: list[str], log):
        """For a place in a country whose web is written in another language, find what its people call it
        and add one local-language query per top topic. Every failure leaves the English-only plan in place
        and says so; it never blocks the research."""
        if self.locale_resolver is None:
            return location, plan
        try:
            context = self.locale_resolver.resolve(location)
        except ToolExecutionError as exc:
            limitations.append(f"Could not determine the local language of this place ({exc}); searched in English only.")
            return location, plan

        location = location.model_copy(
            update={
                "country_code": context.country_code,
                "language": context.language,
                "local_name": context.local_name,
                "local_area": context.local_area,
            }
        )
        if context.language is None:
            log(TraceStage.RESEARCH_PLANNING, "English is the working language for this place; no local-language search.")
            return location, plan

        queries = self.local_query_writer.write(location, plan) if self.local_query_writer else {}
        for topic in plan.topics:
            if topic.topic_id in queries:
                topic.local_queries = [queries[topic.topic_id]]
        log(
            TraceStage.RESEARCH_PLANNING,
            f"Also searching in the local language ({context.language}): {len(queries)} local query(ies)",
            local_name=context.local_name or "unknown",
            local_area=context.local_area or "unknown",
            queries="; ".join(queries.values()),
        )
        if not queries:
            limitations.append(
                f"This place is in a country where most web pages are in {context.language}, but no local-language "
                "query could be built for it, so only English sources were searched."
            )
        return location, plan

    def _run(
        self,
        raw_location: str | Location,
        question: str,
        on_step: Callable[[ResearchTraceStep], None] | None = None,
    ) -> ResearchResponse:
        trace: list[ResearchTraceStep] = []
        tool_calls_made = 0

        def log(stage: TraceStage, description: str, **details: object) -> None:
            step = ResearchTraceStep(
                stage=stage,
                description=description,
                timestamp=datetime.now(timezone.utc),
                details={k: str(v) for k, v in details.items()},
            )
            trace.append(step)
            if on_step is not None:
                try:
                    on_step(step)
                except Exception:  # a progress display must never break the research
                    pass

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

        limitations: list[str] = []
        location = self._adopt_business_at_address(location, limitations, log)
        location = self._adopt_venue_named_in_question(location, question, limitations, log)
        location = self._add_name_variants(location, log)

        log(TraceStage.RESEARCH_PLANNING, "Working out which topics the question needs")
        plan = self.planner.plan(location, question)
        log(
            TraceStage.QUESTION_UNDERSTANDING,
            f"Detected intent(s): {', '.join(plan.detected_intents) or 'none'}",
        )
        log(
            TraceStage.RESEARCH_PLANNING,
            f"Planned {len(plan.topics)} topic(s): {', '.join(t.topic_id for t in plan.topics)}",
        )

        limitations.extend(plan.notes)
        unconfigured = getattr(self.web_search_tool, "unconfigured_reason", None)
        if unconfigured:
            limitations.append(unconfigured)
        location, plan = self._add_local_language(location, plan, limitations, log)
        profile_evidence, place_profile = self._lookup_place_profile(location, plan, limitations, log)

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

        def ingest(
            topic, candidates: list[Evidence], queries: list[str], fetch_full_text: bool = True, forums_first: bool = False
        ) -> int:
            """Score, filter, enrich and store one batch of candidates. Shared by
            the first pass and every later research round so both apply exactly
            the same relevance bar and budget. `forums_first` is for the community search, whose purpose is what
            people said: its forum threads are kept ahead of social posts and the travel-site pages that outscore them."""
            nonlocal tool_calls_made
            scored = self.retriever.score(candidates, queries)
            log(TraceStage.RETRIEVAL, f"Scored {len(scored)} candidate(s) for '{topic.topic_id}'")

            accepted_candidates = [e for e in scored if (e.relevance_score or 0.0) >= self.config.min_relevance_score]
            # English is primary and other languages secondary: a source in the reader's language comes
            # first, and a translated one only fills the places English sources didn't. Within each, the
            # best-matching source wins (forum threads first, for the community search).
            accepted_candidates.sort(
                key=lambda e: (
                    e.metadata.get("language") not in (None, "en"),
                    _community_rank(e) if forums_first else 0,
                    -(e.relevance_score or 0.0),
                )
            )
            accepted_candidates = _spread_across_sites(accepted_candidates, self.config.max_evidence_per_topic)

            enriched: list[Evidence] = []
            for candidate in accepted_candidates:
                if fetch_full_text:
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
            return len(enriched)

        for topic, candidates in zip(searchable_topics, candidates_per_topic):
            if not candidates:
                log(
                    TraceStage.ADDITIONAL_RESEARCH,
                    f"No candidate sources found for '{topic.topic_id}' in the first pass.",
                )
            ingest(topic, candidates, topic.search_queries)

        if self.community_search_tool is not None and plan.topics and tool_calls_made < self.config.max_tool_calls:
            community_topic = next((t for t in plan.topics if t.topic_id == "community_sentiment"), plan.topics[0])
            query = community_query(location, question)
            probe = community_topic.model_copy(update={"search_queries": [query], "local_queries": []})
            log(
                TraceStage.TOOL_SELECTION,
                f"Selected community search for '{community_topic.topic_id}' (Reddit, forums, Quora, review sites: steered by "
                "the query, not restricted to a list of sites)",
                query=query,
            )
            try:
                found = self.community_search_tool.search(location, probe)
                tool_calls_made += 1
                seen_urls = {e.source_url for e in self.evidence_repository.list_all()}
                ingest(
                    community_topic,
                    [c for c in found if c.source_url not in seen_urls],
                    [question, location.name],
                    forums_first=True,
                )
            except ToolExecutionError as exc:
                limitations.append(f"Community search failed ({exc}); forum and social-media sources are not included.")

        if self.reddit_archive_tool is not None and plan.topics and tool_calls_made < self.config.max_tool_calls:
            reddit_topic = next((t for t in plan.topics if t.topic_id == "community_sentiment"), plan.topics[0])
            log(
                TraceStage.TOOL_SELECTION,
                f"Selected Reddit archive search for '{reddit_topic.topic_id}' (posts whose title names the place, in its "
                "own, its country's and the big travel subreddits; no search credit)",
            )
            try:
                found = self.reddit_archive_tool.search(location, reddit_topic)
                tool_calls_made += 1
                seen_urls = {e.source_url for e in self.evidence_repository.list_all()}
                ingest(
                    reddit_topic,
                    [c for c in found if c.source_url not in seen_urls],
                    [question, location.name],
                    fetch_full_text=False,  # the archive returns the post's own text
                    forums_first=True,
                )
            except ToolExecutionError as exc:
                limitations.append(f"Reddit archive search failed ({exc}); some Reddit posts may be missing.")

        # The country's own forums, in their own language. An English query never reaches them, so this is a
        # separate search by the place's native name, run only where there is one and the country has such forums.
        if plan.topics and self._regional_is_separate(location) and tool_calls_made < self.config.max_tool_calls:
            regional_topic = next((t for t in plan.topics if t.topic_id == "community_sentiment"), plan.topics[0])
            # A query about the place *and* the topic ("台北101 觀景台 心得") finds threads about it; the name alone
            # finds threads that merely mention it (measured: 8 of 8 relevant against a scatter of unrelated
            # posts). The local-language queries the plan already has are exactly that, so use the first.
            native = next(
                (q for t in [regional_topic, *plan.topics] for q in t.local_queries if q), native_query(location)
            )
            probe = regional_topic.model_copy(update={"search_queries": [native], "local_queries": []})
            log(
                TraceStage.TOOL_SELECTION,
                f"Selected regional forum search in the local language ({location.country_code}): {native}",
                query=native,
                domains=", ".join(regional_domains(location.country_code)[:8]),
            )
            try:
                found = self.regional_search_tool.search(location, probe)  # type: ignore[union-attr]
                tool_calls_made += 1
                seen_urls = {e.source_url for e in self.evidence_repository.list_all()}
                ingest(regional_topic, [c for c in found if c.source_url not in seen_urls], [question, location.name])
            except ToolExecutionError as exc:
                limitations.append(f"Regional forum search failed ({exc}); local forums are not included.")

        if profile_evidence:
            self.evidence_repository.add_all([enrich_evidence(item) for item in profile_evidence])

        if self.reflector is not None:
            tried_queries = {q for topic in plan.topics for q in topic.search_queries}
            available_tools = {"web_search"} | ({"wikimedia"} if self.wiki_tool is not None else set())
            for round_no in range(1, self.config.max_research_rounds + 1):
                if tool_calls_made >= self.config.max_tool_calls:
                    limitations.append("Research budget exhausted before follow-up research could run.")
                    break
                log(TraceStage.ADDITIONAL_RESEARCH, f"Checking whether the evidence so far answers the question (pass {round_no})")
                reflection = self.reflector.reflect(
                    question,
                    location,
                    plan,
                    self.evidence_repository.list_all(),
                    tried_queries,
                    available_tools,
                    round_no,
                )
                limitations.extend(reflection.notes)
                log(
                    TraceStage.ADDITIONAL_RESEARCH,
                    f"Round {round_no} decision: {reflection.rationale}",
                    enough=reflection.enough,
                    actions="; ".join(f"{a.tool}({a.query or a.topic_id})" for a in reflection.actions) or "none",
                )
                if reflection.enough or not reflection.actions:
                    break

                known_urls = {e.source_url for e in self.evidence_repository.list_all()}
                for action in reflection.actions[: self.config.max_actions_per_round]:
                    topic = next((t for t in plan.topics if t.topic_id == action.topic_id), plan.topics[0])
                    try:
                        if action.tool == "web_search":
                            probe = topic.model_copy(update={"search_queries": [action.query]})
                            tried_queries.add(action.query)
                            found = self.web_search_tool.search(location, probe)
                            tool_calls_made += 1
                            fresh = [c for c in found if c.source_url not in known_urls]
                            stored = ingest(topic, fresh, [action.query, *topic.search_queries])
                        elif action.tool == "wikimedia" and self.wiki_tool is not None:
                            available_tools.discard("wikimedia")
                            found = self.wiki_tool.lookup(location, question, topic.topic_id)
                            tool_calls_made += 1
                            fresh = [c for c in found if c.source_url not in known_urls]
                            stored = ingest(topic, fresh, [question, location.name], fetch_full_text=False)
                        else:
                            continue
                    except ToolExecutionError as exc:
                        limitations.append(f"Follow-up research with {action.tool} failed ({exc}).")
                        continue
                    known_urls.update(c.source_url for c in fresh)
                    log(
                        TraceStage.ADDITIONAL_RESEARCH,
                        f"Ran {action.tool} for '{topic.topic_id}': kept {stored} of {len(fresh)} new source(s)",
                        reason=action.reason,
                    )

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

        log(TraceStage.CLAIM_EXTRACTION, f"Reading {len(all_evidence)} evidence item(s) to extract claims")
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

        log(TraceStage.SYNTHESIS, "Writing the overview from the verified claims and evidence")
        synthesis = self.synthesizer.synthesize(
            location, question, plan, verified_claims, all_evidence, evidence_topic_ids
        )
        log(TraceStage.SYNTHESIS, "Generated summary and recommendation from verified claims and evidence")

        key_findings = list(synthesis.key_findings)
        if place_profile is not None and place_profile.rating is not None and not any(
            f"{place_profile.rating:.1f}" in finding and "Google" in finding for finding in key_findings
        ):
            # Google's own rating is a fact the model may or may not mention; a question about a business's
            # reviews should always open with it, stated from the listing rather than from anyone's prose.
            count = f" from {place_profile.review_count:,} reviews" if place_profile.review_count else ""
            key_findings.insert(
                0, f"Google Maps rates {place_profile.name} {place_profile.rating:.1f} out of 5{count}."
            )

        limitations.extend(synthesis.limitations)
        if getattr(self.synthesizer, "writes_free_text", False):
            sources = [f"{e.source_title} {e.text}" for e in all_evidence]
            # A sentence that merges several verified claims is backed by them even though no single
            # source contains all of its words. Claims were already checked against their sources.
            sources.append(" ".join(c.text for c in verified_claims if c.status == ClaimStatus.SUPPORTED))
            untraced = untraceable_sentences(f"{synthesis.summary} {synthesis.recommendation}", sources)
            if untraced:
                limitations.append(
                    f"{len(untraced)} sentence(s) in the overview could not be confirmed against any retrieved source "
                    "or verified claim (a word-overlap check, so a loose paraphrase can be flagged too); treat "
                    "them as the model's own synthesis rather than sourced fact: "
                    + " | ".join(f"\u201c{s}\u201d" for s in untraced[:3])
                )
                log(TraceStage.SYNTHESIS, f"Flagged {len(untraced)} overview sentence(s) with no matching source")
        seen: set[str] = set()
        unique_limitations = [item for item in limitations if not (item in seen or seen.add(item))]

        return ResearchResponse(
            location=location,
            question=question,
            summary=synthesis.summary,
            key_findings=key_findings,
            details=synthesis.details,
            recommendation=synthesis.recommendation,
            topics=plan.topics,
            claims=verified_claims,
            evidence=all_evidence,
            limitations=unique_limitations,
            research_trace=trace,
        )
