import httpx
import pytest

from app.tools.base import LocationNotFoundError, ToolExecutionError
from app.tools.composite import FallbackLocationResolver
from tests.fixture_tools import FixtureLocationResolver
from app.tools.nominatim_tool import (
    NominatimClient,
    NominatimLocationResolverTool,
    NominatimPlaceSearchTool,
    _detect_country_code,
)

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


_ERICSSON_RESULT = {
    "osm_id": 999,
    "name": "20",
    "display_name": "20, Ericsson Street, Dorchester, Boston, Suffolk County, Massachusetts, 02122, United States",
    "type": "house",
    "class": "place",
    "lat": "42.2917582",
    "lon": "-71.0403677",
    "address": {
        "house_number": "20",
        "road": "Ericsson Street",
        "city": "Boston",
        "state": "Massachusetts",
        "country": "United States",
    },
}


def _recording_client(responder) -> tuple[NominatimClient, list[httpx.Request]]:
    """A client that answers per-request and records what was asked."""
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=responder(request))

    return NominatimClient(transport=httpx.MockTransport(handler)), seen


def test_resolver_falls_back_to_the_address_when_the_business_name_finds_nothing():
    """Regression test for a real failure: OSM knows the address but not the
    business at it, so 'Venezuela, 20 Ericsson St, Boston, MA 02122' returned
    nothing while the address alone resolved exactly."""

    def responder(request: httpx.Request) -> list:
        query = request.url.params.get("q", "")
        return [] if query.lower().startswith("venezuela") else [_ERICSSON_RESULT]

    client, seen = _recording_client(responder)

    location = NominatimLocationResolverTool(client=client).resolve(
        "Venezuela, 20 Ericsson St, Boston, MA 02122"
    )

    assert location.city == "Boston"
    assert location.region == "Massachusetts"
    assert location.latitude == pytest.approx(42.2917582)
    # The name the user typed survives — showing the house number "20" where
    # they wrote "Venezuela" would look broken even with right coordinates.
    assert location.name == "Venezuela"
    assert len(seen) == 2, "expected a retry after the full query came back empty"


def test_search_constrains_to_the_us_when_the_query_names_a_state():
    """Without this, a business name that is also a country name hijacks the
    geocode: 'Venezuela, Boston, MA' resolved to a street in Venezuela."""
    client, seen = _recording_client(lambda _r: [_ERICSSON_RESULT])

    NominatimLocationResolverTool(client=client).resolve("Venezuela, Boston, MA")

    assert seen[0].url.params.get("countrycodes") == "us"


def test_search_is_left_unconstrained_when_no_us_state_is_named():
    client, seen = _recording_client(lambda _r: [_STARBUCKS_RESULT])

    NominatimLocationResolverTool(client=client).resolve("Eiffel Tower, Paris")

    assert "countrycodes" not in seen[0].url.params


def test_place_search_keeps_the_typed_name_when_it_falls_back_to_the_address():
    def responder(request: httpx.Request) -> list:
        query = request.url.params.get("q", "")
        return [] if query.lower().startswith("venezuela") else [_ERICSSON_RESULT]

    client, _seen = _recording_client(responder)

    candidates = NominatimPlaceSearchTool(client=client).search_places(
        "Venezuela, 20 Ericsson St, Boston, MA 02122"
    )

    assert [c.name for c in candidates] == ["Venezuela"]
    assert "Ericsson Street" in candidates[0].display_name


def test_query_variants_only_ever_drops_leading_segments():
    from app.tools.nominatim_tool import _query_variants

    variants = _query_variants("Venezuela, 20 Ericsson St, Boston, MA 02122")

    assert variants[0] == "Venezuela, 20 Ericsson St, Boston, MA 02122"
    assert "20 Ericsson St, Boston, MA 02122" in variants
    # The geography must never be the part that gets dropped.
    assert all("Boston" in v for v in variants)


@pytest.mark.parametrize(
    "query",
    ["Venezuela, 20 Ericsson St, Boston, MA 02122", "Starbucks, Cambridge MA", "Harvard Square, Cambridge, Massachusetts", "Diner, Concord, New Hampshire"],
)
def test_detect_country_code_reads_a_trailing_us_state(query):
    assert _detect_country_code(query) == "us"


@pytest.mark.parametrize(
    "query",
    ["hotel in Tokyo", "cafe near me", "bar or pub in Paris", "Tokyo Bay Shiomi Prince Hotel", "la boqueria, Barcelona"],
)
def test_detect_country_code_ignores_ordinary_words_that_are_also_state_codes(query):
    """Regression test: "hotel in Tokyo" read "in" as Indiana, forced a
    US-only search, and returned hotels in New York."""
    assert _detect_country_code(query) is None


_TOKYO_RESULT = {
    "osm_id": 999,
    "name": "Henn na Hotel Tokyo Ginza",
    "display_name": "Henn na Hotel Tokyo Ginza, Tsukuda Ohashi-dori, Tsukiji, Chuo, Tokyo, 104-0045, Japan",
    "type": "hotel",
    "class": "tourism",
    "lat": "35.6689",
    "lon": "139.7747",
    "address": {"tourism": "Henn na Hotel Tokyo Ginza", "city": "Chuo", "postcode": "104-0045", "country": "Japan"},
}


def test_region_is_recovered_from_the_display_name_when_nominatim_omits_state():
    """Regression test: a Tokyo address has no `state`, so downstream searches
    anchored on the bare ward name "Chuo" and returned a university and a train line."""
    tool = NominatimPlaceSearchTool(client=_client_returning([_TOKYO_RESULT]))

    place = tool.search_places("Henn na Hotel Tokyo Ginza")[0]

    assert place.city == "Chuo"
    assert place.region == "Tokyo"
    assert place.country == "Japan"


def test_search_asks_nominatim_for_english_names():
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(dict(request.url.params))
        return httpx.Response(200, json=[])

    NominatimClient(transport=httpx.MockTransport(handler)).search("Tokyo Station", 3)

    assert seen["accept-language"] == "en"


def test_a_cafe_is_a_business_and_a_neighbourhood_is_not():
    cafe = NominatimPlaceSearchTool(client=_client_returning([_STARBUCKS_RESULT])).search_places("starbucks")[0]
    area = NominatimPlaceSearchTool(
        client=_client_returning([{**_STARBUCKS_RESULT, "category": "place", "class": "place", "type": "neighbourhood", "name": "Harvard Square"}])
    ).search_places("harvard square")[0]

    assert cafe.is_business is True
    assert area.is_business is False


def test_business_is_detected_from_the_jsonv2_category_field():
    """Regression test: real jsonv2 responses carry `category` and no `class`,
    so reading only `class` marked every real place as not-a-business."""
    craft = {**_STARBUCKS_RESULT, "name": "SR Coffee Roaster & Bar", "category": "craft", "type": "coffee_roaster"}
    craft.pop("class")

    assert NominatimPlaceSearchTool(client=_client_returning([craft])).search_places("sr")[0].is_business is True


def test_parks_viewpoints_and_places_of_worship_are_not_businesses():
    from app.tools.nominatim_tool import _is_business

    assert not _is_business({"category": "leisure", "type": "park"})
    assert not _is_business({"category": "tourism", "type": "viewpoint"})
    assert not _is_business({"category": "amenity", "type": "place_of_worship"})
    assert _is_business({"category": "amenity", "type": "cafe"})
    assert _is_business({"category": "tourism", "type": "hotel"})


def test_a_building_is_an_address_but_a_business_or_an_area_is_not():
    """'Unterer Graben 11' comes back as a bare building, with a cafe standing in it."""
    from app.tools.nominatim_tool import _is_address

    assert _is_address({"category": "building", "type": "yes", "addresstype": "building"})
    assert _is_address({"category": "place", "type": "house", "addresstype": "house"})
    assert not _is_address({"category": "amenity", "type": "cafe", "addresstype": "amenity"})
    assert not _is_address({"category": "boundary", "type": "administrative", "addresstype": "suburb"})
    assert not _is_address({"category": "highway", "type": "residential", "addresstype": "road"})


def test_detect_country_code_is_not_slowed_by_a_long_run_of_spaces():
    # The zip-code pattern used to start with `\s*`, which made it quadratic on a query like this one.
    import time

    hostile = "Boston, MA" + " " * 200_000 + "1234x, Somewhere"
    started = time.perf_counter()
    assert _detect_country_code(hostile) is None
    assert time.perf_counter() - started < 2.0


@pytest.mark.parametrize("query", ["Cambridge, MA 02138", "Cambridge, MA 02138-4321", "Cambridge, MA02138"])
def test_detect_country_code_still_ignores_a_trailing_zip_code(query):
    assert _detect_country_code(query) == "us"
