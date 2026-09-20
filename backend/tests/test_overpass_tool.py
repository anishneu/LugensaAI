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

    assert hosts[0] == hosts[-1] == "overpass-api.de" and len(set(hosts)) == 3 and len(hosts) == 4


def test_distance_is_zero_for_the_same_point():
    assert _distance_m(_LAT, _LON, _LAT, _LON) == 0


def test_falls_back_to_the_mirror_when_the_main_server_is_busy():
    seen_hosts = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_hosts.append(request.url.host)
        if request.url.host == "overpass-api.de":
            return httpx.Response(504)
        return httpx.Response(200, json={"elements": [{"type": "node", "lat": _LAT, "lon": _LON, "tags": {"amenity": "bar", "name": "Mirror Bar"}}]})

    result = OverpassNearbyTool(transport=httpx.MockTransport(handler)).nearby(_LAT, _LON)

    assert seen_hosts == ["overpass-api.de", "overpass.kumi.systems"]
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
