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


# ---- resolving places through Google (businesses and plus codes) ----

from app.tools.base import LocationNotFoundError  # noqa: E402
from app.tools.google_places_tool import (  # noqa: E402
    _SEARCH_CACHE,
    GooglePlacesLocationResolver,
    looks_like_plus_code,
)

_SUIRAN = {
    "id": "ChIJsuiran",
    "displayName": {"text": "Suiran", "languageCode": "en"},
    "formattedAddress": "Iida-1279-3 Zendojimachi, Kurume, Fukuoka 839-0824, Japan",
    "addressComponents": [
        {"longText": "Kurume", "types": ["locality", "political"]},
        {"longText": "Fukuoka", "types": ["administrative_area_level_1", "political"]},
        {"longText": "Japan", "types": ["country", "political"]},
    ],
    "location": {"latitude": 33.32532, "longitude": 130.61537},
    "types": ["seafood_restaurant", "restaurant", "food", "point_of_interest", "establishment"],
    "primaryTypeDisplayName": {"text": "Seafood restaurant", "languageCode": "en"},
}
_PLUS_CODE_POINT = {
    "id": "plus",
    "displayName": {"text": "8JG8+44"},
    "formattedAddress": "8JG8+44 Kurume, Fukuoka, Japan",
    "location": {"latitude": 33.32531, "longitude": 130.61531},
    "types": ["plus_code"],
}


@pytest.fixture(autouse=True)
def _clear_search_cache():
    _SEARCH_CACHE.clear()


def _routed(routes: dict[str, dict]) -> GooglePlacesTool:
    def handler(request: httpx.Request) -> httpx.Response:
        for suffix, payload in routes.items():
            if str(request.url).endswith(suffix):
                return httpx.Response(200, json=payload)
        return httpx.Response(404, json={})

    return GooglePlacesTool(api_key="k", transport=httpx.MockTransport(handler))


def test_recognises_pasted_plus_codes_but_not_ordinary_queries():
    assert looks_like_plus_code("8JG8+44 Kurume")
    assert looks_like_plus_code("8jg8+44")
    assert looks_like_plus_code("8Q7XMJ8G+Q7")
    assert not looks_like_plus_code("Suiran Kurume")
    assert not looks_like_plus_code("Cafe 7+8 Tokyo")


def test_search_returns_a_business_with_its_city_region_and_country():
    (candidate,) = _routed({":searchText": {"places": [_SUIRAN]}}).search_places("Suiran Kurume Fukuoka")

    assert candidate.name == "Suiran"
    assert (candidate.city, candidate.region, candidate.country) == ("Kurume", "Fukuoka", "Japan")
    assert candidate.is_business is True
    assert candidate.category == "Seafood restaurant"
    # Kept so the UI's "open in Google Maps" opens this exact listing, not a search that can land on a results list.
    assert candidate.google_place_id == "ChIJsuiran"


def test_a_plus_code_lists_the_business_standing_on_it_first():
    tool = _routed({":searchText": {"places": [_PLUS_CODE_POINT]}, ":searchNearby": {"places": [_SUIRAN]}})

    candidates = tool.search_places("8JG8+44 Kurume")

    assert [c.name for c in candidates] == ["Suiran", "8JG8+44"]
    assert candidates[0].is_business and not candidates[1].is_business


def test_a_plus_code_with_no_business_on_it_stays_a_plain_point():
    tool = _routed({":searchText": {"places": [_PLUS_CODE_POINT]}, ":searchNearby": {"places": []}})

    assert [c.name for c in tool.search_places("8JG8+44 Kurume")] == ["8JG8+44"]


def test_repeated_searches_are_cached_so_they_bill_once():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(200, json={"places": [_SUIRAN]})

    tool = GooglePlacesTool(api_key="k", transport=httpx.MockTransport(handler))
    tool.search_places("Suiran Kurume Fukuoka")
    tool.search_places("suiran kurume fukuoka")

    assert len(calls) == 1


def test_search_asks_only_for_the_cheap_identifying_fields():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["mask"] = request.headers["X-Goog-FieldMask"]
        return httpx.Response(200, json={"places": []})

    GooglePlacesTool(api_key="k", transport=httpx.MockTransport(handler)).search_places("Suiran Kurume")

    assert "places.location" in seen["mask"]
    assert "places.reviews" not in seen["mask"] and "places.rating" not in seen["mask"]


def test_resolver_builds_a_business_location_from_the_top_result():
    location = GooglePlacesLocationResolver(_routed({":searchText": {"places": [_SUIRAN]}})).resolve("Suiran Kurume Fukuoka")

    assert (location.name, location.city, location.is_business) == ("Suiran", "Kurume", True)
    assert (location.latitude, location.longitude) == (33.32532, 130.61537)


def test_resolver_reports_not_found_for_no_results_and_for_a_google_error():
    with pytest.raises(LocationNotFoundError):
        GooglePlacesLocationResolver(_routed({":searchText": {"places": []}})).resolve("zzzz nowhere")
    failing = GooglePlacesTool(api_key="k", transport=httpx.MockTransport(lambda r: httpx.Response(403, json={})))
    with pytest.raises(LocationNotFoundError):
        GooglePlacesLocationResolver(failing).resolve("Suiran")


# ---- places that are not businesses, and locality-aware ranking (found testing 15 places worldwide)

from app.tools.google_places_tool import _prefer_locality, is_venue  # noqa: E402


def test_islands_beaches_parks_and_monuments_are_places_not_businesses():
    """Google tags all of these `establishment`; researching them as a cafe finds nothing."""
    assert not is_venue({"island", "natural_feature", "establishment"})  # Victoria Island, Lagos
    assert not is_venue({"beach", "natural_feature", "establishment"})  # Bondi Beach
    assert not is_venue({"park", "tourist_attraction", "point_of_interest", "establishment"})  # Central Park
    assert not is_venue({"historical_landmark", "monument", "point_of_interest", "establishment"})  # Eiffel Tower
    assert not is_venue({"locality", "political"})
    assert is_venue({"seafood_restaurant", "restaurant", "food", "point_of_interest", "establishment"})
    assert is_venue({"hotel", "lodging", "point_of_interest", "establishment"})


def _candidate_at(name: str, address: str):
    from app.models.place import PlaceCandidate

    return PlaceCandidate(name=name, display_name=f"{name}, {address}", category="x", latitude=0, longitude=0)


def test_results_in_the_locality_the_user_typed_are_ranked_first_but_none_are_dropped():
    road = _candidate_at("Sukhumvit Road", "Chonburi, Thailand")
    district = _candidate_at("Sukhumvit", "Khlong Toei, Bangkok, Thailand")

    ranked = _prefer_locality([road, district], "Sukhumvit, Bangkok")

    assert ranked == [district, road]


def test_locality_ranking_ignores_accents_and_single_segment_queries():
    a = _candidate_at("Vila Madalena", "Sao Paulo, Brazil")
    b = _candidate_at("Vila Madalena", "Curitiba, Brazil")

    assert _prefer_locality([b, a], "Vila Madalena, São Paulo") == [a, b]
    assert _prefer_locality([b, a], "Vila Madalena") == [b, a]


def test_searches_again_around_the_typed_locality_when_google_returns_something_far_away():
    """'Sukhumvit, Bangkok' first returned a road 158 km from Bangkok and nothing else."""
    seen = []
    far = {"id": "far", "displayName": {"text": "Sukhumvit Road"}, "formattedAddress": "Rayong, Thailand",
           "location": {"latitude": 12.78, "longitude": 101.65}, "types": ["route"]}
    near = {"id": "near", "displayName": {"text": "Sukhumvit Road"}, "formattedAddress": "Khlong Toei, Bangkok, Thailand",
            "location": {"latitude": 13.725, "longitude": 100.578}, "types": ["route"]}
    bangkok = {"id": "bkk", "displayName": {"text": "Bangkok"}, "formattedAddress": "Bangkok, Thailand",
               "location": {"latitude": 13.756, "longitude": 100.502}, "types": ["locality"]}

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        seen.append(body)
        if "locationBias" in body:
            return httpx.Response(200, json={"places": [near]})
        return httpx.Response(200, json={"places": [bangkok] if body["textQuery"] == "Bangkok" else [far]})

    candidates = GooglePlacesTool(api_key="k", transport=httpx.MockTransport(handler)).search_places("Sukhumvit, Bangkok")

    assert candidates[0].latitude == 13.725
    biased = next(b for b in seen if "locationBias" in b)
    assert biased["textQuery"] == "Sukhumvit"
    assert biased["locationBias"]["circle"]["center"] == {"latitude": 13.756, "longitude": 100.502}


def test_no_extra_calls_when_the_first_result_is_already_in_the_typed_locality():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(200, json={"places": [_SUIRAN]})

    GooglePlacesTool(api_key="k", transport=httpx.MockTransport(handler)).search_places("Suiran, Kurume")

    assert len(calls) == 1


# ---- a business standing at a street address (the cafe at 'Unterer Graben 11')

_CAFE = {
    "id": "cafe1",
    "displayName": {"text": "Café Pustekuchen"},
    "formattedAddress": "Unterer Graben 11, 36456 Barchfeld-Immelborn, Germany",
    "location": {"latitude": 50.80061, "longitude": 10.30015},
    "types": ["cafe", "food", "point_of_interest", "establishment"],
}
_PARK = {**_CAFE, "id": "park", "displayName": {"text": "Town Park"}, "types": ["park", "point_of_interest", "establishment"]}


def test_a_street_address_and_a_bare_plus_code_are_addresses_not_places():
    from app.tools.google_places_tool import is_address_only

    assert is_address_only({"premise", "street_address"})
    assert is_address_only({"plus_code"})
    assert not is_address_only({"cafe", "food", "point_of_interest", "establishment"})
    assert not is_address_only({"locality", "political"})


def test_venues_at_a_point_lists_businesses_nearest_first_and_skips_parks():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"places": [_PARK, _CAFE]})

    venues = GooglePlacesTool(api_key="k", transport=httpx.MockTransport(handler)).venues_at(50.80061, 10.30015)

    assert [v.name for v in venues] == ["Café Pustekuchen"]
    assert seen["body"]["locationRestriction"]["circle"]["radius"] == 40.0
    assert seen["body"]["rankPreference"] == "DISTANCE"


_KIOSK = {**_CAFE, "id": "kiosk", "displayName": {"text": "TopGift Mobile Phone Accessories"}, "types": ["point_of_interest", "establishment"]}
_ARENA = {
    "id": "arena1", "displayName": {"text": "AO Arena"}, "formattedAddress": "Victoria Station Approach, Manchester M3 1AR, UK",
    "location": {"latitude": 53.4880, "longitude": -2.2440}, "types": ["arena", "performing_arts_theater", "point_of_interest"],
}
_CATHEDRAL = {**_ARENA, "id": "cath", "displayName": {"text": "Manchester Cathedral"}, "types": ["tourist_attraction", "church", "place_of_worship"]}
_STREET = {**_ARENA, "id": "street", "displayName": {"text": "Victoria Street"}, "types": ["route"]}


def test_a_venue_named_in_the_question_is_found_by_popularity_not_distance():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"places": [_KIOSK, _ARENA]})

    tool = GooglePlacesTool(api_key="k", transport=httpx.MockTransport(handler))

    venue = tool.venue_named_in("How are the reviews of this AO Arena?", 53.4873, -2.2430)

    assert venue is not None and venue.name == "AO Arena"
    body = seen["body"]
    assert body["rankPreference"] == "POPULARITY" and body["maxResultCount"] == 20 and body["locationRestriction"]["circle"]["radius"] == 300.0


def test_a_landmark_that_is_not_a_shop_can_be_named_but_a_street_cannot():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"places": [_STREET, _CATHEDRAL]})

    tool = GooglePlacesTool(api_key="k", transport=httpx.MockTransport(handler))

    assert tool.venue_named_in("What is Manchester Cathedral like?", 53.4873, -2.2430).name == "Manchester Cathedral"
    assert tool.venue_named_in("Is Victoria Street busy?", 53.4873, -2.2430) is None


def test_a_place_the_question_does_not_name_is_not_picked():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"places": [_KIOSK, _ARENA]})

    tool = GooglePlacesTool(api_key="k", transport=httpx.MockTransport(handler))

    assert tool.venue_named_in("is it a good place to visit?", 53.4873, -2.2430) is None


def _rated(name: str, rating, count, types, **extra) -> dict:
    return {**_ARENA, "id": name, "displayName": {"text": name}, "types": types, "rating": rating, "userRatingCount": count,
            "googleMapsUri": f"https://maps.google.com/?cid={name}", **extra}


def test_popular_places_lists_rated_places_by_popularity_and_skips_streets_and_unrated_ones():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        seen["mask"] = request.headers["X-Goog-FieldMask"]
        return httpx.Response(
            200,
            json={
                "places": [
                    _rated("Silver Pavilion", 4.6, 21_004, ["tourist_attraction", "point_of_interest"]),
                    _rated("Philosopher's Path", None, None, ["park"]),
                    _rated("Kinkakuji Street", 4.0, 12, ["route"]),
                    _rated("Cafe Kiln", 4.3, 866, ["cafe", "food"]),
                ]
            },
        )

    tool = GooglePlacesTool(api_key="k", transport=httpx.MockTransport(handler))

    places = tool.popular_places(53.4873, -2.2430, limit=5)

    assert [p.name for p in places] == ["Silver Pavilion", "Cafe Kiln"]
    assert places[0].rating == 4.6 and places[0].review_count == 21_004 and places[0].maps_url
    assert seen["body"]["rankPreference"] == "POPULARITY"
    assert "places.rating" in seen["mask"] and "places.userRatingCount" in seen["mask"]


def test_popular_places_respects_its_limit():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"places": [_rated(f"P{i}", 4.0, 10, ["cafe"]) for i in range(10)]})

    tool = GooglePlacesTool(api_key="k", transport=httpx.MockTransport(handler))

    assert len(tool.popular_places(1.0, 1.0, limit=3)) == 3


def test_same_place_name_ignores_case_accents_and_punctuation_but_not_an_extra_word():
    from app.tools.google_places_tool import same_place_name

    assert same_place_name("Ginkaku-ji", "ginkaku ji") and same_place_name("Café Pustekuchen", "Cafe Pustekuchen")
    assert same_place_name("Taipei 101", "101 Taipei")
    assert not same_place_name("Shibuya Station", "Shibuya") and not same_place_name("", "")


def _listing(name: str) -> dict:
    return {**_ARENA, "id": name, "displayName": {"text": name}, "location": {"latitude": 35.0270, "longitude": 135.7982}}


def test_an_exact_lookup_gives_an_area_no_listing_but_a_landmark_its_own():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"places": [_listing("Shibuya Station"), _listing("Ginkaku-ji")]})

    tool = GooglePlacesTool(api_key="k", transport=httpx.MockTransport(handler))

    assert tool.lookup("Shibuya", 35.0270, 135.7982, "Tokyo", exact=True) is None
    assert tool.lookup("Shibuya", 35.0270, 135.7982, "Tokyo").name == "Shibuya Station", "the looser test is for a known business"
    assert tool.lookup("Ginkaku-ji", 35.0270, 135.7982, "Kyoto", exact=True).name == "Ginkaku-ji"


def test_the_price_is_googles_real_range_in_the_local_currency_when_it_has_one():
    """Google Maps shows '€10–20' for a cafe in Germany; '$$' would read as dollars."""
    from app.tools.google_places_tool import _price_text

    euro = {"priceLevel": "PRICE_LEVEL_MODERATE", "priceRange": {"startPrice": {"currencyCode": "EUR", "units": "10"}, "endPrice": {"currencyCode": "EUR", "units": "20"}}}
    yen = {"priceRange": {"startPrice": {"currencyCode": "JPY", "units": "1000"}, "endPrice": {"currencyCode": "JPY", "units": "2000"}}}
    open_ended = {"priceRange": {"startPrice": {"currencyCode": "EUR", "units": "50"}}}

    assert _price_text(euro) == "€10–20"
    assert _price_text(yen) == "¥1000–2000"
    assert _price_text(open_ended) == "€50+"
    assert _price_text({"priceLevel": "PRICE_LEVEL_MODERATE"}) == "$$"  # no range: fall back to the level
    assert _price_text({}) is None


def test_a_street_address_is_not_repeated_in_its_own_display_name():
    from app.tools.google_places_tool import _display_name

    assert _display_name("Unterer Graben 11", "Unterer Graben 11, 36456 Barchfeld-Immelborn, Germany") == "Unterer Graben 11, 36456 Barchfeld-Immelborn, Germany"
    assert _display_name("Café Pustekuchen", "Unterer Graben 11, 36456 Barchfeld-Immelborn") == "Café Pustekuchen, Unterer Graben 11, 36456 Barchfeld-Immelborn"
    assert _display_name("Suiran", None) == "Suiran"
