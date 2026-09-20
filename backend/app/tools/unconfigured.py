"""What the product does when a service is not configured: nothing, and it says so.

Previously an unconfigured install fell back to invented "fixture" sources and claims for two demo
neighborhoods and presented them as real research, with no warning. That is worse than an empty
answer, so these stand-ins return no evidence and carry the reason, which the agent reports as a
limitation of the response.
"""

from __future__ import annotations

from app.models.evidence import Evidence
from app.models.location import Location
from app.models.plan import ResearchTopic
from app.tools.base import LocationNotFoundError, LocationResolverTool, PageRetrievalTool, WebSearchTool


class UnconfiguredWebSearchTool(WebSearchTool):
    unconfigured_reason = (
        "Live web search is not configured (set TAVILY_API_KEY in backend/.env), so no sources were searched "
        "and this answer has no evidence behind it."
    )

    def search(self, location: Location, topic: ResearchTopic) -> list[Evidence]:
        return []


class UnconfiguredPageRetrievalTool(PageRetrievalTool):
    def retrieve_full_text(self, source_url: str) -> str | None:
        return None


class UnconfiguredLocationResolver(LocationResolverTool):
    def resolve(self, raw_query: str) -> Location:
        raise LocationNotFoundError(
            f"Could not resolve {raw_query!r}: live geocoding is disabled (DISABLE_LIVE_GEOCODING) and no "
            "Google Places key is set."
        )
