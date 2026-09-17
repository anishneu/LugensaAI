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
