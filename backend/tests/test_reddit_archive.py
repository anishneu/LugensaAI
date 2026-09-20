"""The Reddit archive tool and Wikidata name variants, with the HTTP mocked: nothing here touches the network."""

from datetime import datetime, timezone

import httpx
import pytest

from app.agents.factory import build_default_agent
from app.models.evidence import Evidence, SourceType
from app.models.location import Location
from app.tools import reddit_archive
from app.tools.base import ToolExecutionError, WebSearchTool
from app.tools.reddit_archive import RedditArchiveTool, search_terms
from app.tools.tavily_tools import filter_for_place
from app.tools.wikidata_names import WikidataNameVariants, _CACHE
from tests.test_tavily_tools import _topic

_TRAIN = dict(
    name="Floating Train at Pa Sak Jolasid Dam", city="Tambon Manao Wan", region="Chang Wat Lopburi", country="Thailand",
    country_code="th", slug="p", raw_query="p", latitude=14.99, longitude=101.02, is_business=True,
)
_THREAD = {
    "id": "1ggc44p", "subreddit": "ThailandTourism", "title": "Pa Sak Jolasid Dam the floating train ",
    "selftext": "Hi guys\n\nHappy to see the announcement for the excursion train across the dam.",
    "permalink": "/r/ThailandTourism/comments/1ggc44p/pa_sak_jolasid_dam_the_floating_train/", "created_utc": 1730373746,
    "score": 1, "num_comments": 3, "over_18": False,
}


@pytest.fixture(autouse=True)
def _fresh_caches(monkeypatch):
    reddit_archive._SUBREDDIT_CACHE.clear()
    reddit_archive._POSTS_CACHE.clear()
    reddit_archive._BLOCKED_UNTIL = 0.0
    _CACHE.clear()
    monkeypatch.setattr(reddit_archive.time, "sleep", lambda _s: None)


def _place(**kw) -> Location:
    return Location(**{**_TRAIN, **kw})


def _archive(posts_by_sub: dict[str, list[dict]], subreddits: dict[str, list[dict]] | None = None, log: list | None = None) -> RedditArchiveTool:
    subreddits = subreddits or {}

    def handler(request: httpx.Request) -> httpx.Response:
        params = dict(request.url.params)
        if log is not None:
            log.append((request.url.path, params))
        if request.url.path.endswith("/subreddits/search"):
            return httpx.Response(200, json={"data": subreddits.get(params["subreddit_prefix"], [])})
        return httpx.Response(200, json={"data": posts_by_sub.get(params["subreddit"], [])})

    return RedditArchiveTool(transport=httpx.MockTransport(handler))


# ------------------------------------------------------------------ what to search for


def test_the_term_searched_is_the_rarest_long_word_of_each_name():
    assert search_terms(["Floating Train at Pa Sak Jolasid Dam"]) == ["jolasid"]
    assert search_terms(["Pa Sak Jolasid Dam", "Pasak Chonlasit Dam"]) == ["jolasid", "chonlasit"]
    assert search_terms(["Hotel Erfurt-City", "Erfurt Cathedral"]) == ["erfurt"], "'city' and 'cathedral' are common, and one term per name"
    assert search_terms(["Old Town"]) == ["town"], "when every word is common the longest still serves"
    assert search_terms(["Zoo"]) == [], "too short to search a title for"
    assert search_terms(["Hotel Erfurt-City"], frozenset({"erfurt"})) == ["erfurt city"], "a word that is only the city's name is not enough alone"
    assert search_terms(["Floating Train at Pa Sak Jolasid Dam"], frozenset({"lopburi"})) == ["jolasid"]


def test_subreddits_named_for_the_place_are_found_and_lookalikes_are_not():
    rows = {
        "erfurt": [{"display_name": "erfurt", "subscribers": 2462}, {"display_name": "erfurt_uncensored", "subscribers": 7}, {"display_name": "Erfurtsex", "subscribers": 300}],
        "germany": [{"display_name": "germany", "subscribers": 1_000_000}, {"display_name": "GermanyBarGirls", "subscribers": 6000}, {"display_name": "GermanyTourism", "subscribers": 5000}],
    }
    tool = _archive({}, rows)

    found = tool.subreddits(Location(name="Erfurt", city="Erfurt", region="Thüringen", country="Germany", slug="e", raw_query="e"))

    assert found == ["erfurt", "germany", "GermanyTourism", "travel", "solotravel", "backpacking"]


def test_a_place_with_no_subreddit_of_its_own_still_gets_the_travel_ones():
    assert _archive({}, {}).subreddits(_place()) == ["travel", "solotravel", "backpacking"]


# ------------------------------------------------------------------ the posts


def test_a_post_whose_title_names_the_place_becomes_dated_evidence_from_the_archive():
    log: list = []
    tool = _archive({"ThailandTourism": [_THREAD]}, {"thailand": [{"display_name": "ThailandTourism", "subscribers": 984888}]}, log)

    found = tool.search(_place(), _topic("community_sentiment"))

    assert len(found) == 1
    post = found[0]
    assert post.source_url == "https://www.reddit.com/r/ThailandTourism/comments/1ggc44p/pa_sak_jolasid_dam_the_floating_train/"
    assert post.source_type == SourceType.COMMUNITY_FORUM and post.publisher == "reddit.com"
    assert post.published_at == datetime(2024, 10, 31, 11, 22, 26, tzinfo=timezone.utc), "the post's own time, not a guess"
    assert post.metadata["provider"] == "reddit_archive" and post.metadata["date_source"] == "reddit_archive"
    assert "excursion train" in post.text
    searched = [p for path, p in log if path.endswith("/posts/search")]
    assert {"title": "jolasid", "subreddit": "ThailandTourism", "limit": "15"} in searched


def test_posts_about_another_place_or_marked_adult_are_dropped():
    elsewhere = {**_THREAD, "id": "x1", "title": "Best floating train tips for Bangkok markets", "permalink": "/r/ThailandTourism/comments/x1/a/"}
    adult = {**_THREAD, "id": "x2", "over_18": True, "permalink": "/r/ThailandTourism/comments/x2/a/"}
    tool = _archive({"ThailandTourism": [_THREAD, elsewhere, adult]}, {"thailand": [{"display_name": "ThailandTourism", "subscribers": 984888}]})

    found = tool.search(_place(), _topic("community_sentiment"))

    assert [e.evidence_id.split(":")[-1] for e in found] == ["1ggc44p"]


def test_a_removed_post_body_is_not_shown_and_the_title_stands_in():
    removed = {**_THREAD, "selftext": "[removed]"}
    tool = _archive({"travel": [removed]})

    (post,) = tool.search(_place(), _topic("community_sentiment"))

    assert post.text == "Pa Sak Jolasid Dam the floating train"


def test_a_variant_spelling_is_searched_and_matches():
    """Reddit says "Pasak Chonlasit Dam"; Google says "Pa Sak Jolasid Dam". Wikidata's alias bridges them."""
    post = {**_THREAD, "id": "v1", "title": "Pasak Chonlasit Dam floating train review", "selftext": "", "permalink": "/r/travel/comments/v1/a/"}
    log: list = []
    tool = _archive({"travel": [post]}, log=log)

    without = tool.search(_place(), _topic("community_sentiment"))
    with_variant = tool.search(_place(name_variants=["Pasak Chonlasit Dam"]), _topic("community_sentiment"))

    assert without == [], "no shared word: not found"
    assert [e.source_title for e in with_variant] == ["Pasak Chonlasit Dam floating train review"]
    assert "chonlasit" in [p.get("title") for path, p in log if path.endswith("/posts/search")]


def test_the_archive_being_down_gives_nothing_and_no_error():
    def down(request):
        raise httpx.ConnectError("archive unreachable")

    assert RedditArchiveTool(transport=httpx.MockTransport(down)).search(_place(), _topic("community_sentiment")) == []


def test_a_request_the_archive_refuses_for_being_heavy_is_retried_once():
    calls = {"n": 0}

    def handler(request):
        if request.url.path.endswith("/subreddits/search"):
            return httpx.Response(200, json={"data": []})
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(422, json={"data": None, "error": "Timeout. Maybe slow down a bit"})
        return httpx.Response(200, json={"data": [_THREAD]})

    found = RedditArchiveTool(transport=httpx.MockTransport(handler)).search(_place(), _topic("community_sentiment"))

    assert found and calls["n"] >= 2


def test_a_short_rate_limit_is_waited_out_and_a_long_one_stops_the_search_without_more_requests():
    calls = {"n": 0}

    def handler(reset: str):
        def inner(request):
            if request.url.path.endswith("/subreddits/search"):
                return httpx.Response(200, json={"data": []})
            calls["n"] += 1
            if calls["n"] == 1 and reset == "2":
                return httpx.Response(429, headers={"x-ratelimit-reset": reset}, json={"error": "slow down"})
            if reset != "2":
                return httpx.Response(429, headers={"x-ratelimit-reset": reset}, json={"error": "slow down"})
            return httpx.Response(200, json={"data": [_THREAD]})

        return inner

    short = RedditArchiveTool(transport=httpx.MockTransport(handler("2"))).search(_place(), _topic("community_sentiment"))
    assert short, "a 2 s refusal is waited out and the request retried"

    reddit_archive._POSTS_CACHE.clear()
    reddit_archive._BLOCKED_UNTIL = 0.0
    calls["n"] = 0
    long = RedditArchiveTool(transport=httpx.MockTransport(handler("30"))).search(_place(), _topic("community_sentiment"))

    assert long == []
    assert calls["n"] <= 2, "told to wait 30 s, it stops: the remaining searches are not sent"


def test_a_second_question_about_the_same_place_costs_no_archive_searches():
    log: list = []
    tool = _archive({"travel": [_THREAD]}, log=log)

    first = tool.search(_place(), _topic("community_sentiment"))
    searches = len([1 for path, _p in log if path.endswith("/posts/search")])
    second = tool.search(_place(), _topic("community_sentiment"))

    assert first and [e.evidence_id for e in second] == [e.evidence_id for e in first]
    assert len([1 for path, _p in log if path.endswith("/posts/search")]) == searches, "answered from the cache"


def test_no_more_requests_than_the_budget_are_sent():
    log: list = []
    tool = _archive({}, log=log)

    tool.search(_place(name_variants=["Pasak Chonlasit Dam", "Pa Sak Cholasit Dam"]), _topic("community_sentiment"))

    assert len([1 for path, _p in log if path.endswith("/posts/search")]) <= reddit_archive._MAX_REQUESTS


# ------------------------------------------------------------------ Wikidata name variants


def _wikidata(entities: dict, search_ids: list[str], log: list | None = None) -> WikidataNameVariants:
    def handler(request: httpx.Request) -> httpx.Response:
        params = dict(request.url.params)
        if log is not None:
            log.append(params)
        if params["action"] == "wbsearchentities":
            return httpx.Response(200, json={"search": [{"id": i} for i in search_ids]})
        return httpx.Response(200, json={"entities": entities})

    return WikidataNameVariants(transport=httpx.MockTransport(handler))


def _entity(label: str, aliases: list[str], lat: float, lon: float) -> dict:
    return {
        "labels": {"en": {"value": label}},
        "aliases": {"en": [{"value": a} for a in aliases]},
        "claims": {"P625": [{"mainsnak": {"datavalue": {"value": {"latitude": lat, "longitude": lon}}}}]},
    }


def test_the_label_and_aliases_of_the_entity_at_the_pin_are_its_other_names():
    tool = _wikidata({"Q1": _entity("Pa Sak Jolasid Dam", ["Pasak Chonlasit Dam", "Pa Sak Cholasit Dam"], 14.86, 101.07)}, ["Q1"])

    assert tool.variants("Floating Train at Pa Sak Jolasid Dam", 14.99, 101.02) == ["Pa Sak Jolasid Dam", "Pasak Chonlasit Dam", "Pa Sak Cholasit Dam"]


def test_an_entity_of_the_same_name_elsewhere_lends_no_names():
    tool = _wikidata({"Q9": _entity("Pa Sak Dam", ["Somewhere Else Dam"], 40.0, -3.0)}, ["Q9"])

    assert tool.variants("Pa Sak Jolasid Dam", 14.86, 101.07) == []


def test_the_part_after_at_is_looked_up_too_and_a_repeat_is_cached():
    log: list = []
    tool = _wikidata({"Q1": _entity("Pa Sak Jolasid Dam", ["Pasak Dam"], 14.86, 101.07)}, ["Q1"], log)

    tool.variants("Floating Train at Pa Sak Jolasid Dam", 14.99, 101.02)
    searched = [p["search"] for p in log if p["action"] == "wbsearchentities"]
    tool.variants("Floating Train at Pa Sak Jolasid Dam", 14.99, 101.02)

    assert searched == ["Floating Train at Pa Sak Jolasid Dam", "Pa Sak Jolasid Dam"]
    assert len(log) == 3, "the second request came from the cache"


def test_without_coordinates_or_when_wikidata_fails_there_are_no_variants():
    def down(request):
        raise httpx.ConnectError("no network")

    assert WikidataNameVariants(transport=httpx.MockTransport(down)).variants("Pa Sak Jolasid Dam", 14.86, 101.07) == []
    assert _wikidata({}, []).variants("Pa Sak Jolasid Dam", None, None) == []


# ------------------------------------------------------------------ what the variants change


def _thread(title: str) -> Evidence:
    return Evidence(
        evidence_id="t", source_url="https://www.reddit.com/r/travel/comments/1/a/", source_title=title, source_type=SourceType.COMMUNITY_FORUM,
        retrieved_at=datetime.now(timezone.utc), location_scope="x", text=title, topic="community_sentiment",
    )


def test_a_page_using_another_spelling_is_about_the_place_once_its_variants_are_known():
    page = _thread("Riding the Pasak Chonlasit Dam floating train from Bangkok")

    assert filter_for_place([page], _place()) == []
    assert filter_for_place([page], _place(name_variants=["Pasak Chonlasit Dam"])) == [page]


def test_a_business_named_for_its_city_needs_its_name_as_a_phrase_not_just_the_words():
    hotel = Location(name="Hotel Erfurt-City", city="Erfurt", region="Thuringia", country="Germany", country_code="de", slug="h", raw_query="h", is_business=True)
    junk = [
        _thread("Hey, I have a flag collection as a hobby, love this City, Erfurt was great"),
        _thread("Any weed in goth city near Erfurt?"),
        _thread("Damit ist die ICE-City Erfurt wohl erstmal auf Eis gelegt"),
    ]
    real = _thread("Stayed at Hotel Erfurt-City for two nights: clean rooms, a short walk to the old town")
    also = _thread("Erfurt City hotel review: breakfast was fine")

    assert filter_for_place(junk, hotel) == []
    assert filter_for_place([real, also], hotel) == [real, also]


def test_a_variant_that_is_common_does_not_let_unrelated_pages_in():
    other = _thread("Riding the floating train from Bangkok to a market")

    assert filter_for_place([other], _place(name_variants=["Pasak Chonlasit Dam"])) == []


# ------------------------------------------------------------------ the agent


class _FakeVariants:
    def __init__(self, names):
        self.names, self.asked = names, []

    def variants(self, name, latitude, longitude):
        self.asked.append(name)
        return self.names


class _FakeArchive(WebSearchTool):
    def __init__(self, fail: bool = False) -> None:
        self.calls = 0
        self._fail = fail

    def search(self, location, topic):
        self.calls += 1
        if self._fail:
            raise ToolExecutionError("archive down")
        return [
            Evidence(
                evidence_id="reddit_archive:c:1", source_url="https://www.reddit.com/r/travel/comments/1/zhongshan/",
                source_title="Zhongshan Taipei", publisher="reddit.com", source_type=SourceType.COMMUNITY_FORUM,
                retrieved_at=datetime.now(timezone.utc), published_at=datetime(2024, 1, 1, tzinfo=timezone.utc), location_scope="Taipei",
                text="Zhongshan Taipei is safe and walkable, quiet at night.", topic=topic.topic_id,
            )
        ]


def _taipei() -> Location:
    return Location(name="Zhongshan", city="Taipei", region="Taiwan", country="Taiwan", slug="z", latitude=25.05, longitude=121.52, raw_query="z", country_code="tw")


def test_the_agent_searches_the_reddit_archive_and_keeps_its_dated_posts():
    agent = build_default_agent()
    agent.reddit_archive_tool = _FakeArchive()

    response = agent.run(_taipei(), "Is it safe and walkable at night?")

    assert agent.reddit_archive_tool.calls == 1
    post = next(e for e in response.evidence if e.evidence_id.startswith("reddit_archive"))
    assert post.published_at == datetime(2024, 1, 1, tzinfo=timezone.utc)
    assert any("Reddit archive search" in s.description for s in response.research_trace)


def test_a_failed_archive_search_is_a_limitation_not_a_crash():
    agent = build_default_agent()
    agent.reddit_archive_tool = _FakeArchive(fail=True)

    response = agent.run(_taipei(), "Is it safe?")

    assert any("Reddit archive search failed" in lim for lim in response.limitations) and response.summary


def test_the_agent_looks_up_other_names_and_records_them_on_the_location():
    agent = build_default_agent()
    agent.name_variants_tool = _FakeVariants(["Zhongshan District", "Chungshan"])

    response = agent.run(_taipei(), "Is it safe?")

    assert response.location.name_variants == ["Zhongshan District", "Chungshan"]
    assert agent.name_variants_tool.asked == ["Zhongshan"]
    assert any("other names" in s.description for s in response.research_trace)


def test_a_failing_name_lookup_never_stops_a_run():
    class Boom:
        def variants(self, *a):
            raise RuntimeError("wikidata exploded")

    agent = build_default_agent()
    agent.name_variants_tool = Boom()

    assert agent.run(_taipei(), "Is it safe?").location.name_variants == []


# ------------------------------------------------------------------ the last N days, for the live feed


def _archive_with_recent(posts_by_sub: dict[str, list[dict]], log: list) -> RedditArchiveTool:
    subreddits = {
        "taipei": [{"display_name": "taipei", "subscribers": 100000}],
        "taiwan": [{"display_name": "taiwan", "subscribers": 500000}],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        params = dict(request.url.params)
        log.append((request.url.path, params))
        if request.url.path.endswith("/subreddits/search"):
            return httpx.Response(200, json={"data": subreddits.get(params["subreddit_prefix"], [])})
        return httpx.Response(200, json={"data": posts_by_sub.get(params["subreddit"], [])})

    return RedditArchiveTool(transport=httpx.MockTransport(handler))


def _post(post_id: str, sub: str, title: str, days_ago: float, **extra) -> dict:
    import time

    return {
        "id": post_id, "subreddit": sub, "title": title, "selftext": "Moving here soon. Which district is best for a family? We like quiet streets.",
        "permalink": f"/r/{sub}/comments/{post_id}/a/", "created_utc": int(time.time() - days_ago * 86400), "score": 5, "num_comments": 2, "over_18": False, **extra,
    }


_XINYI = dict(name="Xinyi District", city="Taipei", region="Taipei City", country="Taiwan", slug="x", raw_query="x")


def test_recent_asks_for_a_date_and_takes_every_post_from_the_places_own_subreddit_but_only_matching_titles_elsewhere():
    log: list = []
    tool = _archive_with_recent({"taipei": [_post("a", "taipei", "Best night markets?", 2)], "taiwan": [_post("b", "taiwan", "Taipei rent is up", 4)]}, log)

    found = tool.recent(Location(**_XINYI), days=30)

    searched = {p["subreddit"]: p for path, p in log if path.endswith("/posts/search")}
    assert "title" not in searched["taipei"], "in r/taipei every post is about Taipei"
    assert searched["taiwan"]["title"] == "taipei", "in r/taiwan only titles that name it"
    assert all("after" in p and p["sort"] == "desc" for p in searched.values())
    assert [e.source_title for e in found] == ["Best night markets?", "Taipei rent is up"], "newest first"


def test_recent_drops_posts_outside_the_window_adult_posts_and_undated_ones():
    posts = [
        _post("new", "taipei", "This week", 3),
        _post("old", "taipei", "Two months ago", 60),
        _post("adult", "taipei", "Adult", 2, over_18=True),
        {**_post("undated", "taipei", "No time", 1), "created_utc": None},
    ]
    tool = _archive_with_recent({"taipei": posts}, [])

    assert [e.source_title for e in tool.recent(Location(**_XINYI), days=30)] == ["This week"]


def test_a_recent_post_carries_its_own_time_and_its_opening_sentences_only():
    tool = _archive_with_recent({"taipei": [_post("a", "taipei", "Which district?", 2)]}, [])

    (post,) = tool.recent(Location(**_XINYI), days=30)

    assert post.published_at is not None and (datetime.now(timezone.utc) - post.published_at).days == 2
    assert "Which district is best for a family?" in post.text and post.metadata["provider"] == "reddit_archive"


def test_recent_is_cached_so_a_reload_sends_no_request():
    log: list = []
    tool = _archive_with_recent({"taipei": [_post("a", "taipei", "Which district?", 2)]}, log)

    tool.recent(Location(**_XINYI), days=30)
    first = len([1 for path, _p in log if path.endswith("/posts/search")])
    tool.recent(Location(**_XINYI), days=30)

    assert len([1 for path, _p in log if path.endswith("/posts/search")]) == first


# ------------------------------------------------------------------ which "Cambridge": a subreddit must describe the right place

_CAMBRIDGE = {
    "cambridge": [
        {"display_name": "cambridge", "subscribers": 94056, "title": "cambridge", "public_description": "Cambridge, England, United Kingdom."},
        {"display_name": "CambridgeMA", "subscribers": 32345, "title": "The People's Republic of Cambridge", "public_description": "For news, events, and info about the Cambridge, Massachusetts, USA.", "description": "Not the one in England: see r/cambridge."},
        {"display_name": "cambridge_uni", "subscribers": 20285, "title": "University of Cambridge", "public_description": "Student life at the University of Cambridge."},
        {"display_name": "cambridgeont", "subscribers": 9560, "title": "For Cambridge Ontario Redditors!", "public_description": "All things Cambridge, Ontario!"},
        {"display_name": "CambridgeshireHookups", "subscribers": 2400, "title": "x", "public_description": "the Cambridgeshire area (U.K.)."},
    ],
}


def test_a_city_name_shared_by_several_places_gets_only_the_subreddit_that_describes_this_one():
    tool = _archive({}, _CAMBRIDGE)
    massachusetts = Location(name="Cambridge", city="Cambridge", region="Massachusetts", country="United States", slug="m", raw_query="m")
    england = Location(name="Cambridge", city="Cambridge", region="England", country="United Kingdom", slug="e", raw_query="e")
    ontario = Location(name="Cambridge", city="Cambridge", region="Ontario", country="Canada", slug="o", raw_query="o")

    assert [n for n, level in tool.geo_subreddits(massachusetts) if level == "city"] == ["CambridgeMA"], "not r/cambridge: that one is England"
    assert [n for n, level in tool.geo_subreddits(england) if level == "city"] == ["cambridge"], "r/CambridgeMA's sidebar mentions England, its description does not"
    assert [n for n, level in tool.geo_subreddits(ontario) if level == "city"] == ["cambridgeont"]


def test_a_shared_name_with_no_subreddit_that_describes_the_place_gets_none_rather_than_a_guess():
    tool = _archive({}, _CAMBRIDGE)
    nz = Location(name="Cambridge", city="Cambridge", region="Waikato", country="New Zealand", slug="n", raw_query="n")

    assert [n for n, level in tool.geo_subreddits(nz) if level == "city"] == []


def test_a_name_no_other_place_shares_needs_no_description():
    rows = {"kyoto": [{"display_name": "Kyoto", "subscribers": 46424, "public_description": "A subreddit for people living in Kyoto."}, {"display_name": "KyotoTravel", "subscribers": 1462}, {"display_name": "KyotoProtocol", "subscribers": 3092}, {"display_name": "KyotoSwap", "subscribers": 2348, "public_description": "KyotoSwap.io: a decentralized exchange by the Kyoto Protocol Foundation."}]}
    tool = _archive({}, rows)

    found = tool.geo_subreddits(Location(name="Ginkaku-ji", city="Kyoto", region="Kyoto Prefecture", country="Japan", slug="g", raw_query="g"))

    assert [n for n, _level in found] == ["Kyoto", "KyotoTravel"], "no sibling place: KyotoSwap and KyotoProtocol are not places"


def test_a_small_adult_subreddit_with_a_short_suffix_does_not_make_a_city_look_ambiguous():
    rows = {"erfurt": [{"display_name": "erfurt", "subscribers": 2462}, {"display_name": "Erfurtsex", "subscribers": 300}]}

    found = _archive({}, rows).geo_subreddits(Location(name="Erfurt", city="Erfurt", region="Thüringen", country="Germany", slug="e", raw_query="e"))

    assert [n for n, _level in found] == ["erfurt"]
