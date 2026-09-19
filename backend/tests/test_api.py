from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_check():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_research_endpoint_returns_valid_response():
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


def test_research_endpoint_404s_on_unknown_location():
    response = client.post(
        "/api/research",
        json={"location": "Nowhereville, XX", "question": "Would this be a good place for a college student?"},
    )

    assert response.status_code == 404


def test_locations_endpoint_returns_known_locations():
    response = client.get("/api/locations")

    assert response.status_code == 200
    names = {entry["name"] for entry in response.json()}
    assert "Harvard Square" in names
    assert "Davis Square" in names
    for entry in response.json():
        assert entry["aliases"]
        assert entry["raw_query"]


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
