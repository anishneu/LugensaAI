from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_check():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_research_endpoint_returns_valid_response(monkeypatch):
    from app.api import routes
    from tests.fixture_tools import fixture_agent

    monkeypatch.setattr(routes, "build_default_agent", fixture_agent)
    response = client.post(
        "/api/research",
        json={"location": "Harvard Square, Cambridge, MA", "question": "Would this be a good place for a college student?"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["location"]["name"] == "Harvard Square"
    assert body["evidence"]
    assert body["claims"]
    assert body["research_trace"]


def test_an_unconfigured_install_returns_no_evidence_and_says_so():
    """A fresh clone has no keys. It must not answer from invented sources: it returns nothing, honestly.

    (Before this was fixed, this exact request returned 12 made-up sources and 8 'supported' claims from
    example.net URLs, with a confident summary and no warning.)
    """
    response = client.post(
        "/api/research",
        json={
            "location": "Harvard Square, Cambridge, MA",
            "question": "Would this be a good place for a college student?",
            "latitude": 42.3736,
            "longitude": -71.119,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["evidence"] == [] and body["claims"] == []
    assert any("TAVILY_API_KEY" in limitation for limitation in body["limitations"])
    assert not any(".example." in str(value) for value in (body["summary"], body["details"], body["recommendation"]))


def test_a_place_that_cannot_be_resolved_without_any_geocoder_is_a_404_that_says_why():
    response = client.post(
        "/api/research",
        json={"location": "Nowhereville, XX", "question": "Would this be a good place for a college student?"},
    )

    assert response.status_code == 404
    assert "geocoding is disabled" in response.json()["detail"]


def test_there_is_no_endpoint_serving_built_in_demo_places():
    assert client.get("/api/locations").status_code == 404


def test_place_search_returns_empty_when_geocoding_disabled():
    # The autouse test fixture sets DISABLE_LIVE_GEOCODING=1, so this must
    # never attempt a real network call regardless of query.
    response = client.get("/api/places/search", params={"q": "Starbucks Cambridge MA"})

    assert response.status_code == 200
    assert response.json() == []


def test_research_accepts_a_pre_resolved_place_bypassing_text_resolution():
    # A place Nominatim/fixtures have never heard of still works when the
    # caller supplies exact coordinates directly (e.g. a specific POI the
    # user picked from /places/search) — no location_resolver call needed.
    response = client.post(
        "/api/research",
        json={
            "location": "Starbucks, 36 JFK St, Cambridge, MA",
            "question": "Are there guest restrooms nearby?",
            "latitude": 42.3733,
            "longitude": -71.1195,
            "city": "Cambridge",
            "region": "MA",
            "country": "US",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["location"]["name"] == "Starbucks"
    assert body["location"]["latitude"] == 42.3733
    assert body["location"]["longitude"] == -71.1195


def test_place_search_returns_empty_for_short_query(monkeypatch):
    monkeypatch.delenv("DISABLE_LIVE_GEOCODING", raising=False)

    response = client.get("/api/places/search", params={"q": "ab"})

    assert response.status_code == 200
    assert response.json() == []


def test_live_feed_returns_empty_when_search_disabled():
    # The autouse test fixture clears TAVILY_API_KEY, so this must never
    # attempt a real network call regardless of location.
    response = client.get("/api/live-feed", params={"location": "Harvard Square, Cambridge, MA"})

    assert response.status_code == 200
    assert response.json() == []


def test_capabilities_reports_the_free_default_configuration():
    response = client.get("/api/capabilities")

    assert response.status_code == 200
    body = response.json()
    # conftest forces every key and optional feature off for the test suite.
    assert body["llm_provider"] == "none"
    assert body["live_search"] is False
    assert body["estimated_seconds_min"] < body["estimated_seconds_max"]


def test_capabilities_reports_ollama_with_a_slower_estimate(monkeypatch):
    monkeypatch.setenv("OLLAMA_ENABLED", "1")

    body = client.get("/api/capabilities").json()

    assert body["llm_provider"] == "ollama"
    assert body["llm_model"]
    # Local CPU inference is minutes, not seconds — the estimate must say so.
    assert body["estimated_seconds_min"] >= 60


def test_nearby_places_is_unavailable_when_live_lookups_are_disabled():
    response = client.get("/api/places/nearby", params={"latitude": 42.37, "longitude": -71.11})

    assert response.status_code == 503


def test_place_profile_is_unavailable_without_a_google_key():
    response = client.get("/api/places/profile", params={"name": "Cafe", "latitude": 1.0, "longitude": 2.0})

    assert response.status_code == 503


def test_place_search_uses_google_first_and_drops_the_same_spot_from_openstreetmap(monkeypatch):
    import httpx

    from app.api import routes
    from app.models.place import PlaceCandidate
    from app.tools.google_places_tool import GooglePlacesTool

    google_payload = {
        "places": [
            {
                "id": "g1",
                "displayName": {"text": "Suiran"},
                "formattedAddress": "Kurume, Fukuoka, Japan",
                "location": {"latitude": 33.32532, "longitude": 130.61537},
                "types": ["restaurant", "establishment"],
            }
        ]
    }
    google = GooglePlacesTool(api_key="k", transport=httpx.MockTransport(lambda r: httpx.Response(200, json=google_payload)))
    monkeypatch.setattr(routes, "_google_places_tool", lambda: google)
    monkeypatch.delenv("DISABLE_LIVE_GEOCODING", raising=False)

    same_spot = PlaceCandidate(
        name="Suiran (OSM)", display_name="x", category="restaurant", latitude=33.3254, longitude=130.6154
    )
    elsewhere = PlaceCandidate(name="Kurume", display_name="Kurume", category="boundary", latitude=33.3197, longitude=130.5081)

    class _FakeOsm:
        def search_places(self, query, limit=6):
            return [same_spot, elsewhere]

    monkeypatch.setattr(routes, "NominatimPlaceSearchTool", _FakeOsm)

    response = client.get("/api/places/search", params={"q": "Suiran Kurume Fukuoka"})

    assert [p["name"] for p in response.json()] == ["Suiran", "Kurume"]
    assert response.json()[0]["is_business"] is True


def test_place_search_still_works_when_google_fails(monkeypatch):
    import httpx

    from app.api import routes
    from app.tools.google_places_tool import GooglePlacesTool

    broken = GooglePlacesTool(api_key="k", transport=httpx.MockTransport(lambda r: httpx.Response(403, json={})))
    monkeypatch.setattr(routes, "_google_places_tool", lambda: broken)

    response = client.get("/api/places/search", params={"q": "Suiran Kurume Fukuoka"})

    assert response.status_code == 200
    assert response.json() == []


def test_the_frontend_may_call_the_api_from_either_dev_port():
    """The README runs Vite on 3000; Vite's own default is 5173. Both must work, or the app silently
    can't reach its backend and the browser reports only a vague CORS error."""
    for origin in ("http://localhost:3000", "http://localhost:5173", "http://127.0.0.1:5173"):
        response = client.get("/api/capabilities", headers={"Origin": origin})

        assert response.headers.get("access-control-allow-origin") == origin

    stranger = client.get("/api/capabilities", headers={"Origin": "http://evil.example"})
    assert "access-control-allow-origin" not in stranger.headers
