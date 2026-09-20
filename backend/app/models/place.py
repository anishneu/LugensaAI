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
    is_business: bool = Field(default=False, description="A specific business/venue rather than an area")
    is_address: bool = Field(default=False, description="A street address or building, not a named place")
    google_place_id: str | None = Field(
        default=None, description="Google's id for the place, when the candidate came from Google Maps: it opens the exact listing"
    )


class PopularPlace(BaseModel):
    """A well-known place near a pin, with Google's own rating. Google's data, shown with attribution."""

    name: str
    category: str
    rating: float
    review_count: int | None = None
    distance_m: int
    maps_url: str | None = None
    latitude: float
    longitude: float
