"""Small composite tool wrappers — combining two implementations of the same
interface rather than adding branching logic to the agent itself."""

from __future__ import annotations

from app.models.location import Location
from app.tools.base import LocationNotFoundError, LocationResolverTool


class FallbackLocationResolver(LocationResolverTool):
    """Tries `primary` first; only calls `fallback` if that raises
    `LocationNotFoundError`.

    Used to try Google first (it knows businesses and plus codes) and fall
    through to OpenStreetMap when Google has nothing or isn't configured.
    """

    def __init__(self, primary: LocationResolverTool, fallback: LocationResolverTool) -> None:
        self._primary = primary
        self._fallback = fallback

    def resolve(self, raw_query: str) -> Location:
        try:
            return self._primary.resolve(raw_query)
        except LocationNotFoundError:
            return self._fallback.resolve(raw_query)
