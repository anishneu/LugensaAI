from __future__ import annotations

from pydantic import BaseModel, Field


class NearbyItem(BaseModel):
    name: str
    kind: str = Field(..., description="Specific OSM type, e.g. 'cafe', 'bus stop', 'pharmacy'")
    distance_m: int = Field(..., description="Straight-line distance from the pin, in meters")
    # What OpenStreetMap knows about the place beyond its name. All optional: volunteers fill these in
    # unevenly, and an absent field means "not in the map", never "doesn't have one".
    latitude: float | None = None
    longitude: float | None = None
    opening_hours: str | None = Field(default=None, description="OSM's raw opening_hours string, e.g. 'Mo-Fr 08:00-18:00'")
    website: str | None = None
    phone: str | None = None
    cuisine: str | None = None
    address: str | None = Field(default=None, description="Street and house number, from the map's own address tags")
    wheelchair: str | None = Field(default=None, description="OSM's wheelchair access value: yes, limited or no")


class NearbyGroup(BaseModel):
    label: str
    total: int = Field(..., description="How many places of this group OSM lists within the radius")
    nearest: list[NearbyItem] = Field(..., description="Up to 15 nearest places, closest first")


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
