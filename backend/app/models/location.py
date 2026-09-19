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
    slug: str = Field(..., description="Stable identifier used to key fixtures/cache entries")
    latitude: float | None = Field(default=None)
    longitude: float | None = Field(default=None)
    raw_query: str = Field(..., description="The original, unnormalized location string supplied by the user")
    is_business: bool = Field(
        default=False,
        description="True for one specific business/venue (a cafe, a hotel), False for an area or landmark. "
        "Research about a business must be about that business, not just its city.",
    )
