"""Small composite tool wrappers — combining two implementations of the same
interface rather than adding branching logic to the agent itself."""

from __future__ import annotations

from app.models.location import Location
from app.tools.base import LocationNotFoundError, LocationResolverTool


class FallbackLocationResolver(LocationResolverTool):
    """Tries `primary` first; only calls `fallback` if that raises
    `LocationNotFoundError`.

    Used to keep the two demo neighborhoods resolving instantly and
    deterministically (no network) via `FixtureLocationResolver`, while any
    other real place falls through to live geocoding.
    """

    def __init__(self, primary: LocationResolverTool, fallback: LocationResolverTool) -> None:
        self._primary = primary
        self._fallback = fallback

    def resolve(self, raw_query: str) -> Location:
        try:
            return self._primary.resolve(raw_query)
        except LocationNotFoundError:
            return self._fallback.resolve(raw_query)
