"""Provider-independent tool interfaces.

The agent depends only on these interfaces (Tavily, Google Places and OpenStreetMap implement them
in app/tools/), so a provider can be swapped without touching the orchestration code. The
"unconfigured" implementations in app/tools/unconfigured.py return nothing and say so.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.models.evidence import Evidence
from app.models.location import Location
from app.models.plan import ResearchTopic


class LocationNotFoundError(Exception):
    """Raised when a LocationResolverTool cannot resolve a raw query."""


class ToolConfigurationError(Exception):
    """Raised at construction time when a real tool is missing required config (e.g. an API key)."""


class ToolExecutionError(Exception):
    """Raised when a real tool's external call fails (network error, API error, timeout)."""


class LocationResolverTool(ABC):
    @abstractmethod
    def resolve(self, raw_query: str) -> Location:
        """Normalize a raw user-supplied location string into a Location.

        Raises LocationNotFoundError if the location cannot be resolved.
        """
        raise NotImplementedError


class WebSearchTool(ABC):
    @abstractmethod
    def search(self, location: Location, topic: ResearchTopic) -> list[Evidence]:
        """Return candidate evidence for a topic's search queries.

        Returned Evidence has `text` set to a short snippet (as a real search
        API would return) and `relevance_score`/`quality_score`/`recency_days`
        left unset — those are filled in by later pipeline stages.
        """
        raise NotImplementedError


class PageRetrievalTool(ABC):
    @abstractmethod
    def retrieve_full_text(self, source_url: str) -> str | None:
        """Fetch the full extracted text for a previously-found source URL.

        Returns None if the page cannot be retrieved.
        """
        raise NotImplementedError
