from __future__ import annotations

from pydantic import BaseModel, Field


class PlaceCandidate(BaseModel):
    """One real-world place candidate from a live POI/address search.

    Distinct from `Location`: a search can return several of these (e.g.
    every Starbucks near "Cambridge, MA") before the user commits to one,
    which then gets resolved into a single `Location`.
    """

    name: str = Field(..., description="The place's own name, e.g. 'Starbucks'")
    display_name: str = Field(..., description="Full human-readable address/description")
    category: str = Field(..., description="Coarse OpenStreetMap category, e.g. 'cafe', 'amenity'")
    city: str | None = None
    region: str | None = None
    country: str | None = None
    latitude: float
    longitude: float
