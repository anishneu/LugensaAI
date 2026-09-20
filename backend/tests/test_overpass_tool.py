import httpx
import pytest

from app.tools.base import ToolExecutionError
from app.tools.overpass_tool import _CACHE, OverpassNearbyTool, _distance_m

_LAT, _LON = 35.6344, 139.7924


@pytest.fixture(autouse=True)
def _clear_cache():
    _CACHE.clear()


def _tool(payload, status_code: int = 200) -> OverpassNearbyTool:
    return OverpassNearbyTool(
        transport=httpx.MockTransport(lambda request: httpx.Response(status_code, json=payload))
    )


def test_groups_nearby_features_with_computed_distances_nearest_first():
    payload = {
        "elements": [
            {"type": "node", "lat": _LAT + 0.004, "lon": _LON, "tags": {"amenity": "cafe", "name": "Far Cafe"}},
            {"type": "node", "lat": _LAT + 0.001, "lon": _LON, "tags": {"amenity": "bar", "name": "Near Bar"}},
            {"type": "way", "center": {"lat": _LAT, "lon": _LON + 0.002}, "tags": {"railway": "station", "name": "Test Station"}},
            {"type": "node", "lat": _LAT, "lon": _LON, "tags": {"amenity": "cafe"}},  # unnamed: dropped
            {"type": "node", "lat": _LAT, "lon": _LON, "tags": {"amenity": "bench", "name": "Not tracked"}},
        ]
    }

    result = _tool(payload).nearby(_LAT, _LON, 600)

    by_label = {group.label: group for group in result.groups}
    assert set(by_label) == {"Food & drink", "Transit"}
    food = by_label["Food & drink"]
    assert [item.name for item in food.nearest] == ["Near Bar", "Far Cafe"]
    assert food.nearest[0].kind == "bar"
    assert 100 < food.nearest[0].distance_m < 130  # 0.001 deg latitude ~ 111 m
    assert by_label["Transit"].nearest[0].kind == "train station"
    assert result.groups[0].nearest[0].distance_m <= result.groups[-1].nearest[0].distance_m


def test_collapses_duplicate_nodes_for_the_same_stop():
    node = {"type": "node", "lat": _LAT, "lon": _LON, "tags": {"highway": "bus_stop", "name": "Main St"}}

    result = _tool({"elements": [node, dict(node)]}).nearby(_LAT, _LON)

    assert result.groups[0].total == 1


def test_empty_area_returns_no_groups_rather_than_an_error():
    assert _tool({"elements": []}).nearby(_LAT, _LON).groups == []


def test_server_failure_is_a_tool_error(monkeypatch):
    slept = []
    monkeypatch.setattr("app.tools.overpass_tool.time.sleep", slept.append)

    with pytest.raises(ToolExecutionError):
        _tool({}, status_code=504).nearby(_LAT, _LON)

    assert slept, "the primary server should be retried once after a pause"


def test_tries_every_mirror_and_then_the_primary_once_more(monkeypatch):
    monkeypatch.setattr("app.tools.overpass_tool.time.sleep", lambda s: None)
    hosts = []

    def handler(request: httpx.Request) -> httpx.Response:
        hosts.append(request.url.host)
        return httpx.Response(504, json={})

    with pytest.raises(ToolExecutionError):
        OverpassNearbyTool(transport=httpx.MockTransport(handler)).nearby(_LAT + 1, _LON + 1)

    assert hosts[0] == hosts[-1] == "lz4.overpass-api.de" and len(set(hosts)) == 5 and len(hosts) == 6


def test_distance_is_zero_for_the_same_point():
    assert _distance_m(_LAT, _LON, _LAT, _LON) == 0


def test_falls_back_to_the_mirror_when_the_main_server_is_busy():
    seen_hosts = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_hosts.append(request.url.host)
        if request.url.host == "lz4.overpass-api.de":
            return httpx.Response(504)
        return httpx.Response(200, json={"elements": [{"type": "node", "lat": _LAT, "lon": _LON, "tags": {"amenity": "bar", "name": "Mirror Bar"}}]})

    result = OverpassNearbyTool(transport=httpx.MockTransport(handler)).nearby(_LAT, _LON)

    assert seen_hosts == ["lz4.overpass-api.de", "overpass-api.de"]
    assert result.groups[0].nearest[0].name == "Mirror Bar"


def test_repeat_lookups_for_the_same_pin_hit_the_cache():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(200, json={"elements": []})

    tool = OverpassNearbyTool(transport=httpx.MockTransport(handler))
    tool.nearby(_LAT, _LON)
    tool.nearby(_LAT, _LON)

    assert len(calls) == 1


def test_keeps_what_the_map_knows_about_each_place_beyond_its_name():
    payload = {
        "elements": [
            {
                "type": "node", "lat": _LAT + 0.001, "lon": _LON,
                "tags": {
                    "amenity": "cafe", "name": "Cafe X", "opening_hours": "Mo-Fr 08:00-18:00", "contact:website": "https://cafe.example",
                    "phone": "+81 3 0000 0000", "cuisine": "coffee_shop;dessert", "addr:street": "Main St", "addr:housenumber": "12",
                    "wheelchair": "yes",
                },
            }
        ]
    }

    item = _tool(payload).nearby(_LAT, _LON).groups[0].nearest[0]

    assert item.opening_hours == "Mo-Fr 08:00-18:00" and item.website == "https://cafe.example"
    assert item.phone == "+81 3 0000 0000" and item.cuisine == "coffee shop, dessert"
    assert item.address == "Main St 12" and item.wheelchair == "yes"
    assert (item.latitude, item.longitude) == (_LAT + 0.001, _LON), "coordinates let the UI open the place on a map"


def test_a_place_with_no_extra_tags_has_none_for_them_never_an_invented_value():
    payload = {"elements": [{"type": "node", "lat": _LAT, "lon": _LON, "tags": {"amenity": "cafe", "name": "Bare Cafe"}}]}

    item = _tool(payload).nearby(_LAT, _LON).groups[0].nearest[0]

    assert (item.opening_hours, item.website, item.phone, item.cuisine, item.address, item.wheelchair) == (None,) * 6


def test_up_to_fifteen_places_per_group_are_returned_while_total_counts_them_all():
    elements = [
        {"type": "node", "lat": _LAT + i * 0.0002, "lon": _LON, "tags": {"amenity": "cafe", "name": f"Cafe {i}"}} for i in range(20)
    ]

    group = _tool({"elements": elements}).nearby(_LAT, _LON).groups[0]

    assert group.total == 20 and len(group.nearest) == 15
    assert [item.name for item in group.nearest] == [f"Cafe {i}" for i in range(15)]


def test_each_server_gets_its_own_timeout_so_a_slow_mirror_is_not_cut_off_at_the_fast_ones_limit():
    from app.tools.overpass_tool import _OVERPASS_ATTEMPTS

    timeouts = [t for _, t in _OVERPASS_ATTEMPTS]
    assert timeouts == sorted(timeouts) and timeouts[-1] >= 30, "measured: one mirror needed 24 s for a dense centre"


def test_the_query_does_not_cap_the_number_of_elements():
    from app.tools.overpass_tool import _query

    assert "out center;" in _query(_LAT, _LON, 600) and "out center 400" not in _query(_LAT, _LON, 600)


def test_when_every_server_fails_an_earlier_answer_for_the_same_spot_is_used(monkeypatch):
    monkeypatch.setattr("app.tools.overpass_tool.time.sleep", lambda s: None)
    answer = {"elements": [{"type": "node", "lat": _LAT, "lon": _LON, "tags": {"amenity": "bar", "name": "Old Bar"}}]}
    state = {"up": True}

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=answer) if state["up"] else httpx.Response(504)

    tool = OverpassNearbyTool(transport=httpx.MockTransport(handler))
    first = tool.nearby(_LAT, _LON)

    import app.tools.overpass_tool as module

    key = next(iter(module._CACHE))
    module._CACHE[key] = (module._CACHE[key][0] - module._CACHE_TTL_SECONDS - 1, first)  # expired, but not stale
    state["up"] = False

    assert tool.nearby(_LAT, _LON).groups[0].nearest[0].name == "Old Bar"

    module._CACHE[key] = (module._CACHE[key][0] - module._STALE_OK_SECONDS, first)  # too old to trust
    with pytest.raises(ToolExecutionError):
        tool.nearby(_LAT, _LON)
