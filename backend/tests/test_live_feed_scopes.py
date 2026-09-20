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
        {"url": f"https://www.reddit.com/r/taiwan/comments/{i}", "title": f"Taipei tip {i}", "content": f"Taipei, Taiwan tip number {i} from someone who lives in Taipei, Taiwan.", "published_date": _DATE}
        for i in range(8)
    ]

    class Client(FakeTavilyClient):
        def search(self, query, **kwargs):
            super().search(query, **kwargs)
            return {"results": news if kwargs.get("topic") == "news" else posts, "images": []}

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
            return {"results": news if kwargs.get("topic") == "news" else [], "images": []}

    client = Client()

    feed = TavilyLiveFeedTool(client=client).fetch(_taipei())

    assert len(feed) == 8
    # News, Reddit (which found nothing), then the country's forums because Reddit left the feed thin. Nothing broader.
    assert len(client.queries) == 3 and not any("Taiwan" == q for q in client.queries)


def _district(name: str) -> Location:
    return Location(name=name, city=name, region="Taipei City", country="Taiwan", slug=name.lower(), raw_query=name, country_code="tw")


def test_the_region_search_is_shared_by_every_place_in_the_same_city():
    region_page = _news("https://example.org/tp", "Taipei City opens a new MRT link", "Taipei City opened a new MRT link this week, officials in Taipei City said.")
    first = _ScopedClient({"Taipei City": [region_page]})
    TavilyLiveFeedTool(client=first).fetch(_district("Xinyi District"))
    assert len(first.queries) == 6, "the district: news, Reddit, forums; then the region's three"

    second = _ScopedClient({"Taipei City": [region_page]})
    feed = TavilyLiveFeedTool(client=second).fetch(_district("Daan District"))

    assert len(second.queries) == 3, "only the new district's own searches; Taipei City comes from the cache"
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
    assert Flaky.calls == 5, "news, Reddit, and the forums (Reddit found nothing), and none of it remembered from the failures"


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

    assert len(client.queries) == 3, "one set: news, Reddit and the forums, not two"


def test_community_posts_are_dated_from_the_post_itself_and_only_the_last_thirty_days_are_shown(monkeypatch):
    """The clock is set to 20 Nov 2025: the two PTT posts (10 and 13 Nov) are in the window, the Reddit thread (Oct 2024) is
    a year outside it, and the Dcard post has no readable date, so it cannot be shown to be inside it."""
    from datetime import datetime, timezone

    from app.tools import tavily_tools
    from app.tools.post_dates import PostDateRecovery

    monkeypatch.setattr(tavily_tools, "_now", lambda: datetime(2025, 11, 20, 12, 0, tzinfo=timezone.utc))
    reddit = "https://www.reddit.com/r/Taipei/comments/1fxbl4l/taipei_city_living"
    ptt_a = "https://www.ptt.cc/bbs/Taipei/M.1762748907.A.922.html"  # 10 Nov 2025
    ptt_b = "https://www.ptt.cc/bbs/Taipei/M.1763000000.A.111.html"  # 13 Nov 2025
    dcard = "https://www.dcard.tw/f/travel/p/256921269"
    body = "Living in Taipei City, Taiwan: rent has gone up again and the MRT is still the best part of it."
    posts = [{"url": u, "title": "Taipei City living", "content": body} for u in (dcard, reddit, ptt_a, ptt_b)]
    feed_xml = '<feed><entry><id>t3_1fxbl4l</id><updated>2024-10-06T08:04:12+00:00</updated></entry></feed>'

    class Client(FakeTavilyClient):
        def search(self, query, **kwargs):
            super().search(query, **kwargs)
            return {"results": [] if kwargs.get("topic") == "news" else posts, "images": []}

    client = Client()
    tool = TavilyLiveFeedTool(client=client, date_recovery=PostDateRecovery(lambda url: feed_xml if "reddit" in url else None))
    place = Location(name="Taipei City", region="Taipei City", country="Taiwan", slug="t", raw_query="Taipei City", country_code="tw")

    feed = tool.fetch(place)

    assert [e.source_url for e in feed] == [ptt_b, ptt_a], "newest first; a year-old thread and an undated post are not shown"
    assert [e.metadata.get("date_source") for e in feed] == ["url", "url"]
    # Reddit is asked for by name with no domain filter; the forums come second, and without reddit.com in the list.
    community = [(q, d) for q, d, t in zip(client.queries, client.domains, client.topics) if t != "news"]
    assert community[0][0].startswith("reddit ") and community[0][1] is None
    assert community[1][1] == ["ptt.cc", "dcard.tw", "mobile01.com", "pixnet.net", "ipeen.com.tw"]


def test_a_thread_that_says_taipei_counts_as_being_about_taipei_city_but_a_different_state_still_does_not():
    from app.tools.tavily_tools import _is_relevant_to_live_feed

    taipei = Location(name="Xinyi District", city="Xinyi District", region="Taipei City", country="Taiwan", slug="x", raw_query="Xinyi")
    body = "Areas to live in Taipei? I am looking at Xinyi for a year, mostly for the MRT access and the quiet streets."

    assert _is_relevant_to_live_feed("Stay in Ximending or Xinyi?", body, taipei, "https://www.reddit.com/r/Taipei/comments/1")

    kansas = Location(name="Kansas City", city="Kansas City", region="Missouri", country="United States", slug="k", raw_query="Kansas City")
    assert not _is_relevant_to_live_feed("Kansas wheat harvest", "Kansas farmers expect a strong harvest this year across Kansas.", kansas, "https://example.org/a")


def _reddit_posts(n: int) -> list[dict]:
    return [
        {"url": f"https://www.reddit.com/r/taiwan/comments/{i}/taipei", "title": f"Taipei City tip {i}", "content": f"Living in Taipei City, Taiwan, tip {i}: the MRT covers almost everything you need.", "published_date": _DATE}
        for i in range(n)
    ]


def _taipei_region() -> Location:
    return Location(name="Taipei City", region="Taipei City", country="Taiwan", slug="t", raw_query="Taipei City", country_code="tw")


def test_reddit_is_searched_by_name_with_no_domain_filter_and_only_its_own_results_are_kept():
    """Measured live: `include_domains=["reddit.com"]` returned subreddits and pages unrelated to the place."""
    mixed = _reddit_posts(3) + [
        {"url": "https://www.youtube.com/watch?v=1", "title": "Taipei City walk", "content": "Living in Taipei City, Taiwan: a video walk through the city centre and the MRT."},
        {"url": "https://www.reddit.com/r/nsfw", "title": "r/NSFW - Reddit", "content": "Adult content community with nothing about any city, any transport or any place at all."},
        {"url": "https://www.reddit.com/r/taipei/best", "title": "Taipei City", "content": "Living in Taipei City, Taiwan: the subreddit's front page, with no post of its own to read."},
    ]

    class Client(FakeTavilyClient):
        def search(self, query, **kwargs):
            super().search(query, **kwargs)
            return {"results": [] if kwargs.get("topic") == "news" else mixed, "images": []}

    client = Client()
    feed = TavilyLiveFeedTool(client=client).fetch(_taipei_region())

    urls = [e.source_url for e in feed]
    assert sorted(urls) == sorted(p["url"] for p in _reddit_posts(3)), "only the relevant Reddit threads: no video, no unrelated subreddit"
    reddit_queries = [(q, d) for q, d, t in zip(client.queries, client.domains, client.topics) if t != "news"]
    assert reddit_queries[0][0].startswith("reddit Taipei City") and reddit_queries[0][1] is None


def test_the_countrys_forums_are_searched_only_when_reddit_leaves_the_feed_thin():
    def run(reddit_count: int) -> list:
        from app.tools import tavily_tools

        tavily_tools._FEED_CACHE.clear()  # the feed is cached per city, and this runs the same city twice
        tavily_tools._SCOPE_CACHE.clear()
        class Client(FakeTavilyClient):
            def search(self, query, **kwargs):
                super().search(query, **kwargs)
                if kwargs.get("topic") == "news":
                    return {"results": [], "images": []}
                if kwargs.get("include_domains"):
                    return {"results": [{"url": "https://www.ptt.cc/bbs/Taipei/M.1762748907.A.922.html", "title": "Taipei City living", "content": "Living in Taipei City, Taiwan: rent has gone up again and the MRT is still the best part."}], "images": []}
                return {"results": _reddit_posts(reddit_count), "images": []}

        client = Client()
        TavilyLiveFeedTool(client=client).fetch(_taipei_region())
        return [d for d, t in zip(client.domains, client.topics) if t != "news" and d]

    assert run(3) == [], "Reddit alone fills the feed, so the forums cost nothing"
    thin = run(0)
    assert thin and "reddit.com" not in thin[0] and thin[0][0] == "ptt.cc"


# ------------------------------------------------------------------ the last 30 days, and the free Reddit archive first


def _recent_reddit(i: int, days_ago: int = 3):
    from datetime import datetime, timedelta, timezone

    from app.models.evidence import Evidence, SourceType

    return Evidence(
        evidence_id=f"reddit_archive:live_feed:{i}", source_url=f"https://www.reddit.com/r/taipei/comments/{i}/a", source_title=f"Taipei City thread {i}",
        publisher="reddit.com", source_type=SourceType.COMMUNITY_FORUM, retrieved_at=datetime(2026, 9, 20, tzinfo=timezone.utc),
        published_at=datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc) - timedelta(days=days_ago), location_scope="Taipei City", text="A thread from someone who lives in Taipei.",
        topic="live_feed", metadata={"provider": "reddit_archive"},
    )


class _Archive:
    def __init__(self, posts=None, fail: bool = False) -> None:
        self.posts, self.fail, self.asked = posts or [], fail, []

    def recent(self, location, days):
        self.asked.append(days)
        if self.fail:
            raise RuntimeError("archive down")
        return list(self.posts)


def test_posts_and_news_older_than_thirty_days_are_not_shown_whatever_the_search_returned():
    news = [
        _news("https://example.org/new", "Taipei story new", "Taipei, Taiwan story about the city this week."),
        {**_news("https://example.org/old", "Taipei story old", "Taipei, Taiwan story about the city long ago."), "published_date": "Mon, 03 Aug 2026 10:00:00 GMT"},
    ]
    posts = [
        {"url": "https://www.reddit.com/r/taiwan/comments/1/new", "title": "Taipei City tip new", "content": "Living in Taipei City, Taiwan, a new tip about the MRT.", "published_date": "Fri, 18 Sep 2026 10:00:00 GMT"},
        {"url": "https://www.reddit.com/r/taiwan/comments/2/old", "title": "Taipei City tip old", "content": "Living in Taipei City, Taiwan, an old tip about the MRT.", "published_date": "Mon, 03 Aug 2026 10:00:00 GMT"},
        {"url": "https://www.reddit.com/r/taiwan/comments/3/edge", "title": "Taipei City tip at the edge", "content": "Living in Taipei City, Taiwan, a tip from exactly thirty days ago.", "published_date": "Fri, 21 Aug 2026 12:00:00 GMT"},
    ]

    class Client(FakeTavilyClient):
        def search(self, query, **kwargs):
            super().search(query, **kwargs)
            return {"results": news if kwargs.get("topic") == "news" else posts, "images": []}

    feed = TavilyLiveFeedTool(client=Client()).fetch(_taipei_region())

    assert sorted(e.source_url for e in feed) == sorted(
        ["https://example.org/new", "https://www.reddit.com/r/taiwan/comments/1/new", "https://www.reddit.com/r/taiwan/comments/3/edge"]
    ), "the 3 August items are out; the one exactly thirty days old is in"


def test_when_the_archive_has_enough_recent_posts_the_billed_reddit_search_is_not_sent():
    archive = _Archive([_recent_reddit(i) for i in range(4)])

    class Client(FakeTavilyClient):
        def search(self, query, **kwargs):
            super().search(query, **kwargs)
            return {"results": [], "images": []}

    client = Client()
    feed = TavilyLiveFeedTool(client=client, reddit_archive=archive).fetch(_taipei_region())

    assert archive.asked == [30]
    assert len([e for e in feed if e.metadata["feed_kind"] == "community"]) == 4
    assert [t for t in client.topics] == ["news"], "only the news search cost a credit"


def test_when_the_archive_leaves_the_feed_thin_the_reddit_search_fills_in_without_repeats():
    archive = _Archive([_recent_reddit(1)])
    web = {"url": "https://www.reddit.com/r/taipei/comments/1/a", "title": "Taipei City thread 1", "content": "Living in Taipei City, Taiwan, again: the MRT covers almost everything you need.", "published_date": _DATE}
    other = {"url": "https://www.reddit.com/r/taiwan/comments/9/b", "title": "Taipei City thread 9", "content": "Living in Taipei City, Taiwan, another tip: the MRT covers almost everything you need.", "published_date": _DATE}

    class Client(FakeTavilyClient):
        def search(self, query, **kwargs):
            super().search(query, **kwargs)
            return {"results": [] if kwargs.get("topic") == "news" else [web, other], "images": []}

    feed = TavilyLiveFeedTool(client=Client(), reddit_archive=archive).fetch(_taipei_region())

    urls = [e.source_url for e in feed if e.metadata["feed_kind"] == "community"]
    assert sorted(urls) == ["https://www.reddit.com/r/taipei/comments/1/a", "https://www.reddit.com/r/taiwan/comments/9/b"]


def test_an_archive_that_fails_never_stops_the_feed():
    web = {"url": "https://www.reddit.com/r/taiwan/comments/9/b", "title": "Taipei City thread 9", "content": "Living in Taipei City, Taiwan, another tip: the MRT covers almost everything you need.", "published_date": _DATE}

    class Client(FakeTavilyClient):
        def search(self, query, **kwargs):
            super().search(query, **kwargs)
            return {"results": [] if kwargs.get("topic") == "news" else [web], "images": []}

    feed = TavilyLiveFeedTool(client=Client(), reddit_archive=_Archive(fail=True)).fetch(_taipei_region())

    assert [e.source_url for e in feed] == ["https://www.reddit.com/r/taiwan/comments/9/b"]
