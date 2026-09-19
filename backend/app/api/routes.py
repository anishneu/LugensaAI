from __future__ import annotations

import os

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.agents.factory import build_default_agent
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
from app.tools.composite import FallbackLocationResolver
from app.tools.fixture_loader import load_locations
from app.tools.fixture_tools import FixtureLocationResolver
from app.tools.google_places_tool import GooglePlacesTool
from app.tools.nominatim_tool import NominatimLocationResolverTool, NominatimPlaceSearchTool, slugify
from app.tools.overpass_tool import OverpassNearbyTool
from app.tools.tavily_tools import TavilyLiveFeedTool
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
    configuration — a fixture-only run finishes in seconds, while CPU-only
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
        # Fixture-only: no network in the research path at all.
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
            )
        return resolver.resolve(self.location)


def _default_location_resolver() -> LocationResolverTool:
    if geocoding_enabled():
        return FallbackLocationResolver(FixtureLocationResolver(), NominatimLocationResolverTool())
    return FixtureLocationResolver()


class ResearchRequest(PlaceReference):
    question: str


class LocationSuggestion(BaseModel):
    name: str
    city: str | None
    region: str | None
    country: str | None
    raw_query: str
    aliases: list[str]
    latitude: float | None
    longitude: float | None


@router.post("/research", response_model=ResearchResponse)
def research(request: ResearchRequest) -> ResearchResponse:
    agent = build_default_agent()
    try:
        location = request.resolve(agent.location_resolver)
        return agent.run(location, request.question)
    except LocationNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/locations", response_model=list[LocationSuggestion])
def list_locations() -> list[LocationSuggestion]:
    """Known, resolvable locations — for search-box autocomplete.

    Backed by the same `fixtures/locations.json` `FixtureLocationResolver` uses,
    so a suggestion picked from here is always guaranteed to resolve.
    """
    entries = load_locations()
    return [
        LocationSuggestion(
            name=entry["name"],
            city=entry.get("city"),
            region=entry.get("region"),
            country=entry.get("country"),
            raw_query=f"{entry['name']}, {entry.get('city', '')}, {entry.get('region', '')}".strip(", "),
            aliases=entry["aliases"],
            latitude=entry.get("latitude"),
            longitude=entry.get("longitude"),
        )
        for entry in entries
    ]


@router.get("/places/search", response_model=list[PlaceCandidate])
def search_places(q: str = "") -> list[PlaceCandidate]:
    """Live point-of-interest search — any real place, not just the two demo
    neighborhoods: a specific Starbucks, a specific address, anything
    OpenStreetMap's Nominatim has indexed.

    Returns an empty list (not an error) if live geocoding is disabled
    (`DISABLE_LIVE_GEOCODING=1`) or the query is too short — the frontend
    autocomplete falls back to the static `/locations` fixture list either way.
    """
    if not geocoding_enabled() or len(q.strip()) < 3:
        return []
    try:
        return NominatimPlaceSearchTool().search_places(q)
    except ToolExecutionError:
        # A flaky/unreachable geocoder shouldn't break autocomplete — the
        # user just sees fewer suggestions this keystroke, not an error.
        return []


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
) -> list[Evidence]:
    """What's currently being said about this place — independent of any
    specific research question. Real, recency-biased web search (Reddit,
    news, review sites, etc.), not derived from the Q&A pipeline's evidence.

    Returns an empty list (not an error) if `TAVILY_API_KEY` isn't set —
    there is no "live" surface at all without live search. Every call here
    is a real, billed Tavily search; the frontend should not poll this
    aggressively (see `frontend/README.md`).
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

    tool = TavilyLiveFeedTool(
        api_key=os.environ.get(TAVILY_API_KEY_ENV_VAR),
        translator=default_translator() if translation_enabled() else None,
    )
    try:
        return tool.fetch(resolved)
    except ToolExecutionError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
