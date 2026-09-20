from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class PlaceReview(BaseModel):
    author: str | None = None
    rating: int | None = Field(default=None, ge=1, le=5)
    text: str = Field(..., description="Review text, in English (translated by Google if it wasn't written in English)")
    original_text: str | None = Field(default=None, description="The review as written, when it wasn't English")
    original_language: str | None = None
    published_at: datetime | None = Field(default=None, description="When the reviewer actually posted it")
    relative_time: str | None = Field(default=None, description="Google's own phrasing, e.g. 'a month ago'")


class PlaceProfile(BaseModel):
    """What Google Maps lists for one specific business.

    Everything here is Google's data, shown live with attribution and never
    presented as anything else. Google returns at most five reviews per place
    through the API, so `review_count` (the true total) can be far larger than
    `len(reviews)`; the UI says so.
    """

    place_id: str
    name: str
    address: str | None = None
    rating: float | None = None
    review_count: int | None = None
    price_level: str | None = None
    summary: str | None = Field(default=None, description="Google's short editorial description, if it has one")
    review_summary: str | None = Field(
        default=None,
        description="Google's own AI-written summary of ALL of the place's reviews. Google's words, not a "
        "reviewer's; always shown with its disclosure.",
    )
    review_summary_disclosure: str | None = Field(default=None, description='e.g. "Summarized with Gemini"')
    review_summary_report_url: str | None = Field(default=None, description="Google's link to flag the summary")
    open_now: bool | None = None
    opening_hours: list[str] = Field(default_factory=list)
    website: str | None = None
    phone: str | None = None
    maps_url: str | None = None
    reviews: list[PlaceReview] = Field(default_factory=list)
    source: str = "Google Maps"
