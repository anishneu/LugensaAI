from __future__ import annotations

import os

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.agents.factory import build_default_agent
from app.core.config import TAVILY_API_KEY_ENV_VAR, geocoding_enabled, search_enabled
from app.models.evidence import Evidence
from app.models.location import Location
from app.models.place import PlaceCandidate
from app.models.response import ResearchResponse
from app.tools.base import LocationNotFoundError, LocationResolverTool, ToolExecutionError
from app.tools.composite import FallbackLocationResolver
from app.tools.fixture_loader import load_locations
from app.tools.fixture_tools import FixtureLocationResolver
from app.tools.nominatim_tool import NominatimLocationResolverTool, NominatimPlaceSearchTool, slugify
from app.tools.tavily_tools import TavilyLiveFeedTool

router = APIRouter()


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

    tool = TavilyLiveFeedTool(api_key=os.environ.get(TAVILY_API_KEY_ENV_VAR))
    try:
        return tool.fetch(resolved)
    except ToolExecutionError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
