from __future__ import annotations

from pydantic import BaseModel, Field


class NearbyItem(BaseModel):
    name: str
    kind: str = Field(..., description="Specific OSM type, e.g. 'cafe', 'bus stop', 'pharmacy'")
    distance_m: int = Field(..., description="Straight-line distance from the pin, in meters")


class NearbyGroup(BaseModel):
    label: str
    total: int = Field(..., description="How many places of this group OSM lists within the radius")
    nearest: list[NearbyItem]


class NearbyPlaces(BaseModel):
    """What OpenStreetMap lists around a coordinate.

    Deliberately not LLM-derived: every item is a real map feature with a real
    computed distance, so — unlike text summarized from web pages — it can't be
    hallucinated. It is also only as complete as OSM's volunteer mapping, which
    the response says explicitly via `source`.
    """

    latitude: float
    longitude: float
    radius_m: int
    groups: list[NearbyGroup]
    source: str = "OpenStreetMap contributors (live query)"
