from __future__ import annotations

from pydantic import BaseModel, Field


class Location(BaseModel):
    """A resolved, normalized location.

    Produced by a LocationResolverTool from a raw user-provided string.
    """

    name: str = Field(..., description="Common name of the place, e.g. 'Harvard Square'")
    city: str | None = Field(default=None)
    region: str | None = Field(default=None, description="State/province, e.g. 'MA'")
    country: str | None = Field(default=None, description="ISO-ish country name or code, e.g. 'US'")
    slug: str = Field(..., description="Stable identifier for this place, derived from its name and coordinates")
    latitude: float | None = Field(default=None)
    longitude: float | None = Field(default=None)
    raw_query: str = Field(..., description="The original, unnormalized location string supplied by the user")
    is_business: bool = Field(
        default=False,
        description="True for one specific business/venue (a cafe, a hotel), False for an area or landmark. "
        "Research about a business must be about that business, not just its city.",
    )
    is_address: bool = Field(
        default=False,
        description="True when the pin is a street address or building rather than a named place. A business "
        "often stands at such an address (the cafe at 'Unterer Graben 11'), and the agent looks it up.",
    )
    # Filled in by the agent from a reverse geocode, not by the resolver, so they work for a place that came
    # from any source (a search result, exact coordinates, Google, OpenStreetMap).
    country_code: str | None = Field(default=None, description="ISO 3166-1 alpha-2, lower-case, e.g. 'jp'")
    language: str | None = Field(
        default=None,
        description="Main written language to also search in (ISO 639-1), when English alone would miss local "
        "pages and the free translator can read it back. None for English-speaking places.",
    )
    local_name: str | None = Field(default=None, description="The place's name in that language, e.g. '翠藍'")
    local_area: str | None = Field(default=None, description="Its city's name in that language, e.g. '久留米市'")
