from __future__ import annotations

import os

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.agents.factory import build_default_agent, build_location_resolver
from app.core.config import (
    GOOGLE_PLACES_API_KEY_ENV_VAR,
    OLLAMA_MODEL,
    TAVILY_API_KEY_ENV_VAR,
    geocoding_enabled,
    ollama_enabled,
    place_profile_enabled,
    search_enabled,
    semantic_retrieval_enabled,
    translation_enabled,
)
from app.models.evidence import Evidence
from app.models.location import Location
from app.models.nearby import NearbyPlaces
from app.models.place import PlaceCandidate
from app.models.place_profile import PlaceProfile
from app.models.response import ResearchResponse
from app.retrieval.semantic_retriever import is_model_warm
from app.tools.base import LocationNotFoundError, LocationResolverTool, ToolExecutionError
from app.tools.google_places_tool import GooglePlacesTool, distance_m
from app.tools.locale import LocaleResolver
from app.tools.nominatim_tool import NominatimPlaceSearchTool, slugify
from app.tools.overpass_tool import OverpassNearbyTool
from app.tools.tavily_tools import TavilyLiveFeedTool
from app.tools.post_dates import PostDateRecovery
from app.tools.translation import default_translator

router = APIRouter()

# How long reading the local embedding model off disk adds to the first
# request after a restart. Measured on one machine at ~61s: the same research
# run took 67.4s cold and 6.3s warm. A coarse surcharge on the estimate, not a
# promise.
_MODEL_WARMUP_SECONDS = 60


class Capabilities(BaseModel):
    """What this backend currently has switched on, plus how long a research
    run is likely to take as a result.

    The estimate exists because run time varies by orders of magnitude with
    configuration — a run with no model finishes in seconds, while CPU-only
    local inference takes minutes — so a single hardcoded number in the UI
    would be wrong nearly always. These are rough observed ranges for
    orientation, not predictions: the UI shows them next to a live elapsed
    timer, so what the user actually sees is the real clock, with the range
    only setting expectations.
    """

    llm_provider: str
    llm_model: str | None = None
    live_search: bool
    live_geocoding: bool
    estimated_seconds_min: int
    estimated_seconds_max: int
    first_run_warmup: bool = False
    translation: bool = False
    place_profile: bool = False


@router.get("/capabilities", response_model=Capabilities)
def capabilities() -> Capabilities:
    if ollama_enabled():
        # Measured end to end on one laptop (i7-1255U, integrated GPU via
        # Ollama's Vulkan backend): 3.0-3.2 minutes for a business question
        # (~2.8k prompt tokens) with qwen3:30b, and roughly double for an area
        # question (~6k tokens). The same laptop CPU-only reads about 8-15
        # tokens/s, which is 15-25 minutes for the same work; a range that
        # hides that would be a lie, so the note in the UI says it.
        provider, model, low, high = "ollama", OLLAMA_MODEL, 150, 600
    else:
        provider, model, low, high = "none", None, 5, 25

    if not search_enabled():
        # No live search: nothing is fetched, so a run is quick (and says it found nothing).
        low, high = (1, 5) if provider == "none" else (low, high)

    # The embedding model is read off disk once per process. That load is
    # large enough to dominate an otherwise-fast run, so the first request
    # after a restart is quoted with it and every later one without.
    warming_up = semantic_retrieval_enabled() and not is_model_warm()
    if warming_up:
        low += _MODEL_WARMUP_SECONDS
        high += _MODEL_WARMUP_SECONDS

    return Capabilities(
        llm_provider=provider,
        llm_model=model,
        live_search=search_enabled(),
        live_geocoding=geocoding_enabled(),
        estimated_seconds_min=low,
        estimated_seconds_max=high,
        first_run_warmup=warming_up,
        translation=translation_enabled(),
        place_profile=place_profile_enabled(),
    )


class PlaceReference(BaseModel):
    """A place identified either by free text (resolved server-side) or by
    exact coordinates the caller already committed to (e.g. one specific
    candidate picked from `/places/search`) — skipping text resolution
    avoids re-geocoding landing on a different same-named place nearby."""

    location: str
    latitude: float | None = None
    longitude: float | None = None
    city: str | None = None
    region: str | None = None
    country: str | None = None
    is_business: bool = False
    is_address: bool = False

    def resolve(self, resolver: LocationResolverTool) -> Location:
        if self.latitude is not None and self.longitude is not None:
            return Location(
                name=self.location.split(",")[0].strip() or self.location,
                city=self.city,
                region=self.region,
                country=self.country,
                slug=slugify(f"{self.location}-{self.latitude}-{self.longitude}"),
                latitude=self.latitude,
                longitude=self.longitude,
                raw_query=self.location,
                is_business=self.is_business,
                is_address=self.is_address,
            )
        return resolver.resolve(self.location)


def _google_places_tool() -> GooglePlacesTool | None:
    return GooglePlacesTool(api_key=os.environ.get(GOOGLE_PLACES_API_KEY_ENV_VAR)) if place_profile_enabled() else None


def _default_location_resolver() -> LocationResolverTool:
    return build_location_resolver(_google_places_tool(), geocoding_enabled())


class ResearchRequest(PlaceReference):
    question: str


@router.post("/research", response_model=ResearchResponse)
def research(request: ResearchRequest) -> ResearchResponse:
    agent = build_default_agent()
    try:
        location = request.resolve(agent.location_resolver)
        return agent.run(location, request.question)
    except LocationNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/places/search", response_model=list[PlaceCandidate])
def search_places(q: str = "") -> list[PlaceCandidate]:
    """Live point-of-interest search — any real place, not just the two demo
    neighborhoods: a specific Starbucks, a specific address, anything
    OpenStreetMap's Nominatim has indexed.

    Returns an empty list (not an error) if live geocoding is disabled
    (`DISABLE_LIVE_GEOCODING=1`) and Google isn't configured, or the query is too short.
    """
    if len(q.strip()) < 3:
        return []

    candidates: list[PlaceCandidate] = []
    google = _google_places_tool()
    if google is not None:
        # Google first: it knows businesses and plus codes that OpenStreetMap
        # doesn't, and its coordinates are the ones Google Maps itself shows.
        try:
            candidates = google.search_places(q)
        except ToolExecutionError:
            candidates = []  # fall through to OpenStreetMap
    if geocoding_enabled():
        try:
            osm = NominatimPlaceSearchTool().search_places(q)
        except ToolExecutionError:
            # A flaky/unreachable geocoder shouldn't break autocomplete — the
            # user just sees fewer suggestions this keystroke, not an error.
            osm = []
        # Drop OSM entries that are the same spot Google already listed.
        candidates += [
            place
            for place in osm
            if not any(distance_m(place.latitude, place.longitude, c.latitude, c.longitude) < 150 for c in candidates)
        ]
    return candidates[:8]


@router.get("/places/nearby", response_model=NearbyPlaces)
def nearby_places(latitude: float, longitude: float, radius_m: int = 600) -> NearbyPlaces:
    """What OpenStreetMap lists around a pin: food, transit, groceries, health,
    police, banks — each with a computed distance. Deterministic map data, not
    LLM output and not a web-page summary, so it can't be hallucinated.

    503 if live map lookups are disabled (`DISABLE_LIVE_GEOCODING=1`), 502 if
    the public Overpass server fails — the frontend shows "unavailable" for
    either rather than pretending there is nothing nearby.
    """
    if not geocoding_enabled():
        raise HTTPException(status_code=503, detail="Live map lookups are disabled on this server.")
    try:
        return OverpassNearbyTool().nearby(latitude, longitude, min(max(radius_m, 100), 1500))
    except ToolExecutionError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/places/profile", response_model=PlaceProfile)
def place_profile(name: str, latitude: float, longitude: float, city: str = "") -> PlaceProfile:
    """Google Maps rating, review count, hours and recent reviews for one
    specific business. Opt-in (`GOOGLE_PLACES_API_KEY`): 503 when not
    configured, 404 when Google has no listing matching this name near this
    pin, 502 when Google's API fails."""
    if not place_profile_enabled():
        raise HTTPException(status_code=503, detail="Google Maps lookups are not configured on this server.")
    try:
        profile = GooglePlacesTool(api_key=os.environ.get(GOOGLE_PLACES_API_KEY_ENV_VAR)).lookup(
            name, latitude, longitude, city
        )
    except ToolExecutionError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    if profile is None:
        raise HTTPException(status_code=404, detail="No matching Google Maps listing near this pin.")
    return profile


@router.get("/live-feed", response_model=list[Evidence])
def live_feed(
    location: str,
    latitude: float | None = None,
    longitude: float | None = None,
    city: str | None = None,
    region: str | None = None,
    country: str | None = None,
    refresh: bool = False,
) -> list[Evidence]:
    """What's being said about this place lately — independent of any specific research question.

    Recent news (last 30 days) and community conversation (Reddit, Quora, regional forums) about the
    place's city, widening once to the region around it when the city has little (never to the whole
    country). Each item's metadata says which (`feed_kind`, `feed_scope`). Real web search, not derived
    from the Q&A pipeline's evidence.

    Returns an empty list (not an error) if `TAVILY_API_KEY` isn't set — there is no "live" surface at
    all without live search. A cold load is 2 to 4 billed Tavily searches; the result is cached for an hour
    (and each city's search is shared by every place in it). `refresh=true` skips the cache, for the
    refresh button: the frontend must not use it to poll (see `frontend/README.md`).
    """
    if not search_enabled():
        return []

    place = PlaceReference(
        location=location, latitude=latitude, longitude=longitude, city=city, region=region, country=country
    )
    try:
        resolved = place.resolve(_default_location_resolver())
    except LocationNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    if geocoding_enabled():
        # The country's code picks which regional forums to search (PTT and Dcard for Taiwan, and so on).
        try:
            resolved = resolved.model_copy(update={"country_code": LocaleResolver().resolve(resolved).country_code})
        except ToolExecutionError:
            pass  # only the global communities are searched

    tool = TavilyLiveFeedTool(
        api_key=os.environ.get(TAVILY_API_KEY_ENV_VAR),
        translator=default_translator() if translation_enabled() else None,
        date_recovery=PostDateRecovery(),
    )
    try:
        return tool.fetch(resolved, refresh=refresh)
    except ToolExecutionError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
