import json
from datetime import datetime, timezone

import httpx
import pytest

from app.agents.factory import build_default_agent
from app.evidence.place_profile_evidence import pick_topic, profile_to_evidence
from app.models.location import Location
from app.tools.base import ToolConfigurationError, ToolExecutionError
from app.tools.google_places_tool import _CACHE, GooglePlacesTool

_LAT, _LON = 35.6871, 139.7757
_JAPANESE = "濃厚なバスクチーズケーキとラテアートが最高。"

_PLACE = {
    "id": "ChIJabc123",
    "displayName": {"text": "SR Coffee Roaster", "languageCode": "en"},
    "formattedAddress": "1-2-3 Nihonbashi, Chuo City, Tokyo",
    "location": {"latitude": _LAT + 0.0003, "longitude": _LON},
    "rating": 4.2,
    "userRatingCount": 257,
    "priceLevel": "PRICE_LEVEL_MODERATE",
    "googleMapsUri": "https://maps.google.com/?cid=1",
    "editorialSummary": {"text": "Specialty coffee and Basque cheesecake."},
    "currentOpeningHours": {"openNow": True},
    "regularOpeningHours": {"weekdayDescriptions": ["Monday: 8:00 AM - 6:00 PM"]},
    "reviews": [
        {
            "rating": 5,
            "text": {"text": "Rich Basque cheesecake and great latte art.", "languageCode": "en"},
            "originalText": {"text": _JAPANESE, "languageCode": "ja"},
            "publishTime": "2026-08-20T10:15:00Z",
            "relativePublishTimeDescription": "a month ago",
            "authorAttribution": {"displayName": "Yuki"},
        },
        {
            "rating": 3,
            "text": {"text": "Good coffee but very crowded on weekends.", "languageCode": "en"},
            "originalText": {"text": "Good coffee but very crowded on weekends.", "languageCode": "en"},
            "publishTime": "2026-07-02T08:00:00Z",
            "authorAttribution": {"displayName": "Sam"},
        },
    ],
}


def _business() -> Location:
    return Location(
        name="SR Coffee Roaster & Bar",
        city="Chuo",
        region="Tokyo",
        country="Japan",
        slug="sr",
        latitude=_LAT,
        longitude=_LON,
        raw_query="SR Coffee Roaster & Bar",
        is_business=True,
    )


@pytest.fixture(autouse=True)
def _clear_cache():
    _CACHE.clear()


def _tool(payload, status_code: int = 200) -> GooglePlacesTool:
    return GooglePlacesTool(
        api_key="test-key", transport=httpx.MockTransport(lambda request: httpx.Response(status_code, json=payload))
    )


def test_requires_an_api_key():
    with pytest.raises(ToolConfigurationError):
        GooglePlacesTool(api_key=None)


def test_parses_rating_reviews_and_keeps_the_original_of_translated_reviews():
    profile = _tool({"places": [_PLACE]}).lookup("SR Coffee Roaster & Bar", _LAT, _LON, "Chuo")

    assert profile is not None
    assert (profile.rating, profile.review_count, profile.price_level) == (4.2, 257, "$$")
    assert profile.open_now is True
    assert profile.opening_hours == ["Monday: 8:00 AM - 6:00 PM"]
    translated, english = profile.reviews
    assert translated.text.startswith("Rich Basque cheesecake")
    assert translated.original_language == "ja" and translated.original_text == _JAPANESE
    assert translated.published_at is not None and translated.published_at.year == 2026
    assert english.original_text is None  # already English: nothing to label


def test_sends_the_pin_as_a_location_bias_and_asks_for_english():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        seen["mask"] = request.headers["X-Goog-FieldMask"]
        seen["key"] = request.headers["X-Goog-Api-Key"]
        return httpx.Response(200, json={"places": []})

    GooglePlacesTool(api_key="k", transport=httpx.MockTransport(handler)).lookup("Cafe X", _LAT, _LON, "Tokyo")

    assert seen["body"]["languageCode"] == "en"
    assert seen["body"]["locationBias"]["circle"]["center"] == {"latitude": _LAT, "longitude": _LON}
    assert "places.reviews" in seen["mask"] and seen["key"] == "k"


def test_a_different_business_nearby_is_not_a_match():
    other = {**_PLACE, "displayName": {"text": "LEAVES Coffee Roasters"}}

    assert _tool({"places": [other]}).lookup("SR Coffee Roaster & Bar", _LAT, _LON) is None


def test_the_right_name_far_from_the_pin_is_not_a_match():
    far = {**_PLACE, "location": {"latitude": _LAT + 0.05, "longitude": _LON}}

    assert _tool({"places": [far]}).lookup("SR Coffee Roaster & Bar", _LAT, _LON) is None


def test_api_failure_is_a_tool_error():
    with pytest.raises(ToolExecutionError):
        _tool({}, status_code=403).lookup("SR Coffee Roaster", _LAT, _LON)


def test_repeat_lookups_are_cached_so_they_bill_once():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(200, json={"places": [_PLACE]})

    tool = GooglePlacesTool(api_key="k", transport=httpx.MockTransport(handler))
    tool.lookup("SR Coffee Roaster", _LAT, _LON)
    tool.lookup("SR Coffee Roaster", _LAT, _LON)

    assert len(calls) == 1


def test_profile_becomes_dated_cited_evidence_with_translation_labels():
    profile = _tool({"places": [_PLACE]}).lookup("SR Coffee Roaster", _LAT, _LON)

    evidence = profile_to_evidence(profile, "community_sentiment", "Chuo, Tokyo", datetime.now(timezone.utc))

    headline, translated, english = evidence
    assert "4.2 out of 5 from 257 reviews" in headline.text
    assert translated.published_at is not None and english.published_at is not None
    assert translated.metadata["language"] == "ja" and translated.metadata["original_text"] == _JAPANESE
    assert "language" not in english.metadata
    assert all(e.publisher == "Google Maps" and e.topic == "community_sentiment" for e in evidence)


_SUMMARY_PLACE = {
    **_PLACE,
    "reviews": [],
    "reviewSummary": {
        "text": {"text": "Diners like the rich Basque cheesecake and latte art.", "languageCode": "en-US"},
        "disclosureText": {"text": "Summarized with Gemini", "languageCode": "en-US"},
        "flagContentUri": "https://www.google.com/local/content/rap/report?postId=abc",
    },
}


def test_keeps_googles_review_summary_when_the_reviews_field_is_absent():
    """Live finding: `reviews` came back missing while `reviewSummary` was present."""
    profile = _tool({"places": [_SUMMARY_PLACE]}).lookup("SR Coffee Roaster", _LAT, _LON)

    assert profile.reviews == []
    assert profile.review_summary.startswith("Diners like the rich Basque cheesecake")
    assert profile.review_summary_disclosure == "Summarized with Gemini"
    assert profile.review_summary_report_url.startswith("https://www.google.com/local/content/rap/report")


def test_review_summary_becomes_evidence_labeled_as_googles_ai_summary():
    profile = _tool({"places": [_SUMMARY_PLACE]}).lookup("SR Coffee Roaster", _LAT, _LON)

    evidence = profile_to_evidence(profile, "community_sentiment", "Chuo, Tokyo", datetime.now(timezone.utc))

    summary = next(e for e in evidence if e.evidence_id.endswith(":reviewsummary"))
    assert "Summarized with Gemini" in summary.text
    assert "Basque cheesecake" in summary.text
    assert "257" in summary.text and summary.metadata["generated_by"] == "Summarized with Gemini"
    assert summary.publisher == "Google Maps" and summary.published_at is None


def test_pick_topic_prefers_reviews_and_falls_back_to_the_first_planned_topic():
    assert pick_topic(["safety", "food", "community_sentiment"]) == "community_sentiment"
    assert pick_topic(["safety", "housing"]) == "safety"
    assert pick_topic([]) is None


def test_agent_adds_google_reviews_as_evidence_for_a_business():
    agent = build_default_agent()
    agent.place_profile_tool = _tool({"places": [_PLACE]})

    response = agent.run(_business(), "How is the coffee and what do reviews say?")

    google = [e for e in response.evidence if e.publisher == "Google Maps"]
    assert len(google) == 3
    assert any(e.published_at is not None for e in google)


def test_agent_says_so_when_google_maps_is_not_connected_for_a_business():
    response = build_default_agent().run(_business(), "How is the coffee and what do reviews say?")

    assert any("GOOGLE_PLACES_API_KEY" in lim for lim in response.limitations)
    assert any("thin" in lim for lim in response.limitations)
