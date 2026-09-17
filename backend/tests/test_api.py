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
