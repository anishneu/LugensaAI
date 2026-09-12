"""Provider-independent tool interfaces.

Concrete implementations in `fixture_tools.py` read from local JSON fixtures
so Milestone 1 runs with no network access and no API keys. A later
milestone can add e.g. a Tavily-backed WebSearchTool or a geocoding-backed
LocationResolverTool that implement these same interfaces, and the agent's
orchestration code will not need to change.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.models.evidence import Evidence
from app.models.location import Location
from app.models.plan import ResearchTopic


class LocationNotFoundError(Exception):
    """Raised when a LocationResolverTool cannot resolve a raw query."""


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
