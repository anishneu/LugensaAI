import httpx
import pytest

from app.tools.base import LocationNotFoundError, ToolExecutionError
from app.tools.composite import FallbackLocationResolver
from app.tools.fixture_tools import FixtureLocationResolver
from app.tools.nominatim_tool import NominatimClient, NominatimLocationResolverTool, NominatimPlaceSearchTool

_STARBUCKS_RESULT = {
    "osm_id": 12345,
    "name": "Starbucks",
    "display_name": "Starbucks, 36, JFK Street, Harvard Square, Cambridge, Middlesex County, Massachusetts, 02138, United States",
    "type": "cafe",
    "class": "amenity",
    "lat": "42.3733",
    "lon": "-71.1195",
    "address": {
        "amenity": "Starbucks",
        "city": "Cambridge",
        "state": "Massachusetts",
        "country": "United States",
    },
}


def _client_returning(payload, status_code: int = 200) -> NominatimClient:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, json=payload)

    return NominatimClient(transport=httpx.MockTransport(handler))


def _client_raising() -> NominatimClient:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("simulated network failure", request=request)

    return NominatimClient(transport=httpx.MockTransport(handler))


def test_resolver_resolves_a_specific_business_not_just_a_neighborhood():
    resolver = NominatimLocationResolverTool(client=_client_returning([_STARBUCKS_RESULT]))

    location = resolver.resolve("Starbucks, 36 JFK St, Cambridge, MA")

    assert location.name == "Starbucks"
    assert location.city == "Cambridge"
    assert location.region == "Massachusetts"
    assert location.latitude == pytest.approx(42.3733)
    assert location.longitude == pytest.approx(-71.1195)
    assert location.raw_query == "Starbucks, 36 JFK St, Cambridge, MA"


def test_resolver_raises_when_nothing_found():
    resolver = NominatimLocationResolverTool(client=_client_returning([]))

    with pytest.raises(LocationNotFoundError):
        resolver.resolve("somewhere that does not exist anywhere")


def test_resolver_wraps_network_errors():
    resolver = NominatimLocationResolverTool(client=_client_raising())

    with pytest.raises(ToolExecutionError):
        resolver.resolve("Starbucks, Cambridge, MA")


def test_place_search_returns_multiple_candidates():
    second = {**_STARBUCKS_RESULT, "osm_id": 999, "lat": "42.40", "lon": "-71.12"}
    search = NominatimPlaceSearchTool(client=_client_returning([_STARBUCKS_RESULT, second]))

    candidates = search.search_places("Starbucks Cambridge MA")

    assert len(candidates) == 2
    assert all(c.name == "Starbucks" for c in candidates)
    latitudes = sorted(c.latitude for c in candidates)
    assert latitudes[0] == pytest.approx(42.3733)
    assert latitudes[1] == pytest.approx(42.40)


def test_place_search_returns_empty_for_blank_query():
    search = NominatimPlaceSearchTool(client=_client_returning([_STARBUCKS_RESULT]))

    assert search.search_places("   ") == []


def test_fallback_resolver_prefers_fixtures_then_falls_back_to_geocoding(harvard_square):
    fixture_resolver = FixtureLocationResolver()
    geocoded = NominatimLocationResolverTool(client=_client_returning([_STARBUCKS_RESULT]))
    resolver = FallbackLocationResolver(fixture_resolver, geocoded)

    # Known fixture location resolves without ever touching the geocoder.
    from_fixture = resolver.resolve("Harvard Square, Cambridge, MA")
    assert from_fixture.slug == harvard_square.slug

    # Anything else falls through to live geocoding.
    from_geocoding = resolver.resolve("Starbucks, 36 JFK St, Cambridge, MA")
    assert from_geocoding.name == "Starbucks"


def test_fallback_resolver_propagates_not_found_when_both_fail():
    empty_geocoder = NominatimLocationResolverTool(client=_client_returning([]))
    resolver = FallbackLocationResolver(FixtureLocationResolver(), empty_geocoder)

    with pytest.raises(LocationNotFoundError):
        resolver.resolve("nonsense query matching nothing")
