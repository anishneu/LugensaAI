"""The live feed: recent news and community conversation about a city, widening once to its region.

Also the cost rules: every search is a billed Tavily credit, so these tests count them.
"""

import threading
import time

import pytest

from app.models.location import Location
from app.tools.base import ToolExecutionError
from app.tools.tavily_tools import LIVE_FEED_WINDOW_DAYS, TavilyLiveFeedTool, _feed_scopes
from tests.test_tavily_tools import FakeTavilyClient

_DATE = "Wed, 16 Sep 2026 15:14:23 GMT"


def _taipei() -> Location:
    return Location(name="Zhongshan", city="Taipei", region="Taiwan", country="Taiwan", slug="z", raw_query="Zhongshan, Taipei", country_code="tw")


def _country() -> Location:
    return Location(name="Taiwan", country="Taiwan", slug="tw", raw_query="Taiwan", country_code="tw")


def _village() -> Location:
    return Location(name="Barchfeld", city="Barchfeld-Immelborn", region="Thuringia", country="Germany", slug="b", raw_query="Barchfeld", country_code="de")


class _ScopedClient(FakeTavilyClient):
    """Answers a query with whatever pages were registered for a word that appears in it."""

    def __init__(self, by_word: dict[str, list[dict]]) -> None:
        super().__init__()
        self._by_word = by_word

    def search(self, query, **kwargs):
        super().search(query, **kwargs)
        for word, results in self._by_word.items():
            if word.lower() in query.lower():
                return {"results": results, "images": []}
        return {"results": [], "images": []}


def _news(url: str, title: str, body: str) -> dict:
    return {"url": url, "title": title, "content": body, "published_date": _DATE}


def test_scopes_run_from_the_exact_area_to_its_region_and_never_the_whole_country():
    scopes = _feed_scopes(_village())

    assert [name for name, _ in scopes] == ["area", "region"]
    assert scopes[1][1].city is None and scopes[1][1].region == "Thuringia"


def test_a_region_that_only_repeats_the_city_is_not_searched_twice():
    tokyo = Location(name="Shibuya Crossing", city="Tokyo", region="Tokyo", country="Japan", slug="t", raw_query="Tokyo", country_code="jp")

    assert [name for name, _ in _feed_scopes(tokyo)] == ["area"]


def test_a_place_with_a_region_but_no_city_is_searched_at_the_region():
    place = Location(name="Bavarian Forest", region="Bavaria", country="Germany", slug="bf", raw_query="Bavarian Forest", country_code="de")

    assert [name for name, _ in _feed_scopes(place)] == ["region"]


def test_a_country_level_place_has_only_the_country_scope():
    scopes = _feed_scopes(_country())

    assert [name for name, _ in scopes] == ["country"]


def test_a_place_with_no_geography_at_all_is_still_searched_as_itself():
    lone = Location(name="Somewhere", slug="s", raw_query="Somewhere")

    assert [name for name, _ in _feed_scopes(lone)] == ["area"]


def test_the_window_is_thirty_days_not_seven():
    client = FakeTavilyClient(results=[])
    assert LIVE_FEED_WINDOW_DAYS == 30

    TavilyLiveFeedTool(client=client).fetch(_taipei())

    news_calls = [q for q, topic in zip(client.queries, client.topics) if topic == "news"]
    assert news_calls, "at least one news search"


def test_a_country_gets_general_wording_not_local_news_or_incident_reports():
    client = FakeTavilyClient(results=[])

    TavilyLiveFeedTool(client=client).fetch(_country())

    news_queries = [q for q, topic in zip(client.queries, client.topics) if topic == "news"]
    assert news_queries == ["Taiwan news travel culture events"]
    assert not any("police" in q or "local news" in q for q in client.queries)


def test_when_the_village_has_nothing_the_feed_widens_to_the_region_and_says_so():
    client = _ScopedClient(
        {
            "Germany": [_news("https://example.org/de", "Germany travel news for Thuringia visitors", "Germany news: new rail passes announced for tourists this week across Germany.")],
            "Thuringia": [_news("https://example.org/th", "Thuringia festival season begins", "The Thuringia festival season begins with events across Thuringia this weekend, organisers said.")],
        }
    )

    feed = TavilyLiveFeedTool(client=client).fetch(_village())

    assert {e.source_url: e.metadata["feed_scope"] for e in feed} == {"https://example.org/th": "region"}
    assert {e.location_scope for e in feed} == {"Thuringia"}
    assert not any(q.startswith("Germany") for q in client.queries), "the country is never searched for a place that has a region"


def test_a_place_with_plenty_of_local_content_never_pays_for_the_broader_searches():
    news = [_news(f"https://example.org/n{i}", f"Taipei story {i}", f"Taipei, Taiwan story number {i} about the city this week.") for i in range(8)]
    posts = [
        {"url": f"https://www.reddit.com/r/taiwan/comments/{i}", "title": f"Taipei tip {i}", "content": f"Taipei, Taiwan tip number {i} from someone who lives in Taipei, Taiwan."}
        for i in range(8)
    ]

    class Client(FakeTavilyClient):
        def search(self, query, **kwargs):
            super().search(query, **kwargs)
            return {"results": posts if kwargs.get("include_domains") else news, "images": []}

    client = Client()

    feed = TavilyLiveFeedTool(client=client).fetch(_taipei())

    kinds = [e.metadata["feed_kind"] for e in feed]
    assert kinds.count("news") == 8 and kinds.count("community") == 8
    assert all(e.metadata["feed_scope"] == "area" for e in feed)
    assert len(client.queries) == 2, "one news search and one community search, nothing broader"
    assert set(client.depths) == {"basic"}, "basic depth is one credit; advanced would be two"


def test_a_repeat_request_is_served_from_the_cache_and_costs_no_searches():
    client = _ScopedClient({"Taiwan": [_news("https://example.org/a", "Taiwan travel culture", "Taiwan travel and culture events this month across Taiwan.")]})
    tool = TavilyLiveFeedTool(client=client)

    first = tool.fetch(_country())
    calls = len(client.queries)
    second = tool.fetch(_country())

    assert second == first and len(client.queries) == calls


def test_every_search_failing_is_an_error_but_one_failing_is_not():
    with pytest.raises(ToolExecutionError):
        TavilyLiveFeedTool(client=FakeTavilyClient(raise_error=True)).fetch(_country())

    class OneFails(_ScopedClient):
        def search(self, query, **kwargs):
            if "events" in query:
                raise RuntimeError("boom")
            return super().search(query, **kwargs)

    client = OneFails({"Taiwan": [_news("https://example.org/n", "Taiwan news roundup", "Taiwan news roundup: what happened across Taiwan this week.")]})

    assert [e.source_url for e in TavilyLiveFeedTool(client=client).fetch(_country())] == ["https://example.org/n"]


def test_thin_community_alone_does_not_trigger_the_broader_searches():
    news = [_news(f"https://example.org/n{i}", f"Taipei story {i}", f"Taipei, Taiwan story number {i} about the city this week.") for i in range(8)]

    class Client(FakeTavilyClient):
        def search(self, query, **kwargs):
            super().search(query, **kwargs)
            return {"results": [] if kwargs.get("include_domains") else news, "images": []}

    client = Client()

    feed = TavilyLiveFeedTool(client=client).fetch(_taipei())

    assert len(feed) == 8 and len(client.queries) == 2


def _district(name: str) -> Location:
    return Location(name=name, city=name, region="Taipei City", country="Taiwan", slug=name.lower(), raw_query=name, country_code="tw")


def test_the_region_search_is_shared_by_every_place_in_the_same_city():
    region_page = _news("https://example.org/tp", "Taipei City opens a new MRT link", "Taipei City opened a new MRT link this week, officials in Taipei City said.")
    first = _ScopedClient({"Taipei City": [region_page]})
    TavilyLiveFeedTool(client=first).fetch(_district("Xinyi District"))
    assert len(first.queries) == 4, "area news + area community, then the region's two"

    second = _ScopedClient({"Taipei City": [region_page]})
    feed = TavilyLiveFeedTool(client=second).fetch(_district("Daan District"))

    assert len(second.queries) == 2, "only the new district's own searches; Taipei City comes from the cache"
    assert [e.source_url for e in feed] == ["https://example.org/tp"]
    assert feed[0].metadata["feed_scope"] == "region"


def test_a_cached_scope_result_is_a_copy_so_one_place_cannot_relabel_anothers_items():
    region_page = _news("https://example.org/tp", "Taipei City opens a new MRT link", "Taipei City opened a new MRT link this week, officials in Taipei City said.")
    tool = TavilyLiveFeedTool(client=_ScopedClient({"Taipei City": [region_page]}))

    first = tool.fetch(_district("Xinyi District"))
    first[0].metadata["feed_scope"] = "tampered"
    second = tool.fetch(_district("Daan District"))

    assert second[0].metadata["feed_scope"] == "region"


def test_refresh_bypasses_the_cache_and_a_plain_request_does_not():
    client = _ScopedClient({"Taiwan": [_news("https://example.org/a", "Taiwan travel culture", "Taiwan travel and culture events this month across Taiwan.")]})
    tool = TavilyLiveFeedTool(client=client)

    tool.fetch(_country())
    cold = len(client.queries)
    tool.fetch(_country())
    assert len(client.queries) == cold

    tool.fetch(_country(), refresh=True)
    assert len(client.queries) == cold * 2


def test_a_failed_search_is_not_cached_so_the_next_load_tries_again():
    class Flaky(FakeTavilyClient):
        calls = 0

        def search(self, query, **kwargs):
            Flaky.calls += 1
            if Flaky.calls <= 2:
                raise RuntimeError("boom")
            return super().search(query, **kwargs)

    tool = TavilyLiveFeedTool(client=Flaky(results=[]))
    with pytest.raises(ToolExecutionError):
        tool.fetch(_country())

    tool.fetch(_country())  # succeeds: the failures were not remembered
    assert Flaky.calls == 4


def test_two_simultaneous_loads_of_the_same_place_cost_one_set_of_searches():
    """React's dev mode mounts an effect twice and aborts the first request, but the backend still runs it."""

    class Slow(FakeTavilyClient):
        def search(self, query, **kwargs):
            time.sleep(0.05)
            return super().search(query, **kwargs)

    client = Slow(results=[])
    tool = TavilyLiveFeedTool(client=client)
    threads = [threading.Thread(target=tool.fetch, args=(_country(),)) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len(client.queries) == 2


def test_community_posts_are_dated_from_the_post_itself_and_listed_newest_first_with_undated_last():
    from app.tools.post_dates import PostDateRecovery

    reddit = "https://www.reddit.com/r/Taipei/comments/1fxbl4l/taipei_city_living"
    ptt = "https://www.ptt.cc/bbs/Taipei/M.1762748907.A.922.html"
    dcard = "https://www.dcard.tw/f/travel/p/256921269"
    posts = [
        {"url": dcard, "title": "Taipei City living", "content": "Living in Taipei City, Taiwan: my three years in the city, what I would tell a newcomer."},
        {"url": reddit, "title": "Taipei City living", "content": "Living in Taipei City, Taiwan is easy without a car; the MRT covers almost everything you need."},
        {"url": ptt, "title": "Taipei City living", "content": "Living in Taipei City, Taiwan: rent has gone up again and the MRT is still the best part."},
    ]
    feed_xml = '<feed><entry><id>t3_1fxbl4l</id><updated>2024-10-06T08:04:12+00:00</updated></entry></feed>'

    class Client(FakeTavilyClient):
        def search(self, query, **kwargs):
            super().search(query, **kwargs)
            return {"results": posts if kwargs.get("include_domains") else [], "images": []}

    client = Client()
    tool = TavilyLiveFeedTool(client=client, date_recovery=PostDateRecovery(lambda url: feed_xml if "reddit" in url else None))
    place = Location(name="Taipei City", region="Taipei City", country="Taiwan", slug="t", raw_query="Taipei City", country_code="tw")

    feed = tool.fetch(place)

    assert [e.source_url for e in feed] == [ptt, reddit, dcard], "2025 PTT, then 2024 Reddit, then the undated Dcard post"
    assert [e.metadata.get("date_source") for e in feed] == ["url", "reddit_feed", None]
    assert feed[2].published_at is None, "a post whose date cannot be read is not given one"
    assert client.domains[-1] == ["ptt.cc", "dcard.tw", "mobile01.com", "pixnet.net", "ipeen.com.tw", "reddit.com"]


def test_a_thread_that_says_taipei_counts_as_being_about_taipei_city_but_a_different_state_still_does_not():
    from app.tools.tavily_tools import _is_relevant_to_live_feed

    taipei = Location(name="Xinyi District", city="Xinyi District", region="Taipei City", country="Taiwan", slug="x", raw_query="Xinyi")
    body = "Areas to live in Taipei? I am looking at Xinyi for a year, mostly for the MRT access and the quiet streets."

    assert _is_relevant_to_live_feed("Stay in Ximending or Xinyi?", body, taipei, "https://www.reddit.com/r/Taipei/comments/1")

    kansas = Location(name="Kansas City", city="Kansas City", region="Missouri", country="United States", slug="k", raw_query="Kansas City")
    assert not _is_relevant_to_live_feed("Kansas wheat harvest", "Kansas farmers expect a strong harvest this year across Kansas.", kansas, "https://example.org/a")
