from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.agents.factory import build_default_agent
from app.models.response import ResearchResponse
from app.tools.base import LocationNotFoundError
from app.tools.fixture_loader import load_locations

router = APIRouter()


class ResearchRequest(BaseModel):
    location: str
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
        return agent.run(request.location, request.question)
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
