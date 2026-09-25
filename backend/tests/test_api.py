import json

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


# ---- translating "Around this pin"


def test_translate_endpoint_is_unavailable_when_translation_is_off():
    response = client.post("/api/places/translate", json={"latitude": 35.0, "longitude": 135.8, "texts": ["円通殿"]})

    assert response.status_code == 200
    assert response.json() == {"available": False, "language": None, "translations": []}


def test_translate_endpoint_translates_by_the_language_of_the_place(monkeypatch):
    from app.api import routes
    from app.tools.locale import LocalContext
    from app.tools.translation import Translator

    class Fake(Translator):
        def detect(self, text):
            return None

        def translate_to_english(self, text, source_language):
            return {"円通殿": "Entsu Hall"}.get(text)

    class FakeLocale:
        def resolve(self, location):
            return LocalContext(country_code="jp", language="ja")

    monkeypatch.setattr(routes, "translation_enabled", lambda: True)
    monkeypatch.setattr(routes, "LocaleResolver", FakeLocale)
    monkeypatch.setattr(routes, "default_translator", lambda: Fake())

    response = client.post("/api/places/translate", json={"latitude": 35.0, "longitude": 135.8, "texts": ["円通殿", "Starbucks"]})

    assert response.json() == {"available": True, "language": "ja", "translations": ["Entsu Hall", None]}


def test_translate_endpoint_says_unavailable_where_the_place_has_no_local_language(monkeypatch):
    from app.api import routes
    from app.tools.locale import LocalContext

    class FakeLocale:
        def resolve(self, location):
            return LocalContext(country_code="us", language=None)

    monkeypatch.setattr(routes, "translation_enabled", lambda: True)
    monkeypatch.setattr(routes, "LocaleResolver", FakeLocale)

    response = client.post("/api/places/translate", json={"latitude": 42.0, "longitude": -71.0, "texts": ["x"]})

    assert response.json()["available"] is False


def test_popular_places_is_503_without_google():
    assert client.get("/api/places/popular", params={"latitude": 35.0, "longitude": 135.8}).status_code == 503


def _events(body: str) -> list[tuple[str, dict]]:
    """Parses a server-sent-events body into (event, data) pairs, ignoring comment lines."""
    import json

    parsed = []
    for block in body.split("\n\n"):
        lines = [line for line in block.split("\n") if line and not line.startswith(":")]
        if not lines:
            continue
        event = next(line[len("event: "):] for line in lines if line.startswith("event: "))
        data = next(line[len("data: "):] for line in lines if line.startswith("data: "))
        parsed.append((event, json.loads(data)))
    return parsed


def test_the_streamed_research_sends_each_step_and_then_the_same_result_as_the_plain_endpoint(monkeypatch):
    from app.api import routes
    from tests.fixture_tools import fixture_agent

    monkeypatch.setattr(routes, "build_default_agent", fixture_agent)
    payload = {"location": "Harvard Square, Cambridge, MA", "question": "Would this be a good place for a college student?"}

    response = client.post("/api/research/stream", json=payload)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    events = _events(response.text)
    kinds = [kind for kind, _ in events]
    assert kinds[-1] == "result" and kinds.count("result") == 1
    steps = [data for kind, data in events if kind == "step"]
    assert len(steps) >= 5 and all({"stage", "description", "timestamp"} <= set(step) for step in steps)

    result = events[-1][1]
    assert result["location"]["name"] == "Harvard Square" and result["claims"] and result["evidence"]
    # The steps that were streamed are the trace of the result, in the same order.
    assert [step["description"] for step in steps] == [step["description"] for step in result["research_trace"]]


def test_the_streamed_research_reports_an_unresolvable_place_as_a_404_error_event():
    response = client.post("/api/research/stream", json={"location": "Nowhereville, XX", "question": "Is it safe?"})

    assert response.status_code == 200  # the stream itself opened fine
    [(kind, data)] = _events(response.text)
    assert kind == "error" and data["status"] == 404 and "geocoding is disabled" in data["detail"]


def test_a_crash_during_a_streamed_run_is_logged_and_not_shown_to_the_reader(monkeypatch):
    from app.api import routes

    class Exploding:
        location_resolver = None

        def run(self, *args, **kwargs):
            raise RuntimeError("internal detail: /home/secret/path and an api key")

    monkeypatch.setattr(routes, "build_default_agent", lambda: Exploding())
    body = client.post(
        "/api/research/stream",
        json={"location": "Somewhere", "question": "Is it safe?", "latitude": 1.0, "longitude": 2.0},
    ).text

    [(kind, data)] = _events(body)
    assert kind == "error" and data["status"] == 500
    assert "secret" not in body and "api key" not in body
