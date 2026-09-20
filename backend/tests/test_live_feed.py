"""The live feed's topic rules, its news source, and the builder that puts them together. No network: everything is faked."""

from datetime import datetime, timedelta, timezone

import httpx
import pytest

from app.models.evidence import Evidence, SourceType
from app.models.location import Location
from app.tools import live_feed, news_rss
from app.tools.feed_topics import categorize, excluded
from app.tools.live_feed import LiveFeedTool, _is_near, _splits
from app.tools.news_rss import GoogleNewsRss, NewsItem, parse

_NOW = datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc)  # what conftest pins the clock to


@pytest.fixture(autouse=True)
def _fresh(monkeypatch):
    live_feed._FEED_CACHE.clear()
    live_feed._ADDRESS_CACHE.clear()
    news_rss._CACHE.clear()


# ------------------------------------------------------------------ what is left out, and what kind of thing is left


@pytest.mark.parametrize(
    "title",
    [
        "Results Roll In From the 2026 Massachusetts State Primary",
        "Senate votes on the budget bill",
        "Labour party conference opens in Liverpool",
        "Your legal rights explained after government announcement",
        "Prime Minister visits flood victims",
    ],
)
def test_politics_is_left_out(title):
    assert excluded(title) == "politics"


@pytest.mark.parametrize(
    "title",
    ["Where was The Drama filmed?", "Weekly horoscope for Leo", "Final score: City 2, United 1", "Shares tumble after earnings report", "Obituary: a life in Cambridge"],
)
def test_things_that_only_mention_the_place_are_left_out(title):
    assert excluded(title) == "irrelevant"


@pytest.mark.parametrize(
    "title",
    [
        "Cambridge council approves new bike lane",
        "Police investigate stabbing on Massachusetts Avenue",
        "New cafe opens near the station",
        "Storm warning for the coast this weekend",
        "MIT professor dies after bike crash at Memorial Drive intersection",
    ],
)
def test_municipal_crime_business_weather_and_accident_news_is_kept(title):
    assert excluded(title) is None


def test_personal_asks_in_a_community_are_left_out_only_for_community_posts():
    assert excluded("Roommate wanted near the square", community=True) == "irrelevant"
    assert excluded("Curly haircuts recommendations", community=True) == "irrelevant"
    assert excluded("Roommate wanted near the square", community=False) is None
    assert excluded("Abandoned bike on Richdale Ave", community=True) is None


def test_the_first_matching_kind_names_an_item_and_a_community_post_falls_back_to_community():
    assert categorize("A fire closes the road after a crash") == "Crime & safety"
    assert categorize("Two-car collision on the bridge") == "Accidents & traffic"
    assert categorize("Flood warning issued") == "Weather & alerts"
    assert categorize("New restaurant opens on the corner") == "Business"
    assert categorize("Night market this weekend") == "Events & tourism"
    assert categorize("Council approves housing development") == "Development & transport"
    assert categorize("Something happened") == "News"
    assert categorize("Something happened", community=True) == "Community"


# ------------------------------------------------------------------ the news source

_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
<item><title>Man charged after Massachusetts Avenue robbery - Patch</title><link>https://news.google.com/rss/articles/A1</link>
<pubDate>Fri, 18 Sep 2026 15:00:00 GMT</pubDate><source url="https://patch.com">Patch</source></item>
<item><title>No date on this one - Somewhere</title><link>https://news.google.com/rss/articles/A2</link><source url="https://x.example">Somewhere</source></item>
<item><title>Night market returns - Cambridge Day</title><link>https://news.google.com/rss/articles/A3</link>
<pubDate>Sat, 19 Sep 2026 09:30:00 GMT</pubDate><source url="https://cambridgeday.com">Cambridge Day</source></item>
</channel></rss>""".encode()


def test_an_rss_document_becomes_dated_headlines_without_the_outlet_suffix_and_undated_items_are_dropped():
    items = parse(_RSS)

    assert [i.title for i in items] == ["Man charged after Massachusetts Avenue robbery", "Night market returns"]
    assert items[0].publisher == "Patch" and items[0].published_at == datetime(2026, 9, 18, 15, 0, tzinfo=timezone.utc)


def test_a_document_that_declares_a_doctype_or_entities_is_refused_not_parsed():
    hostile = b'<?xml version="1.0"?><!DOCTYPE lolz [<!ENTITY a "aaaa">]><rss><channel><item><title>&a;</title></item></channel></rss>'

    assert parse(hostile) == [] and parse(b"not xml at all") == []


def test_the_search_asks_for_the_window_and_the_countrys_english_edition_and_caches_the_answer():
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(200, content=_RSS)

    tool = GoogleNewsRss(transport=httpx.MockTransport(handler))

    first = tool.search('"Massachusetts Avenue" Cambridge', 30, "gb")
    again = tool.search('"Massachusetts Avenue" Cambridge', 30, "gb")

    assert len(first) == 2 and again == first
    assert len(seen) == 1, "the repeat came from the cache"
    assert "when%3A30d" in seen[0] and "ceid=GB:en" in seen[0] and "hl=en-GB" in seen[0]


def test_a_news_source_that_fails_gives_nothing_and_no_error():
    def down(request):
        raise httpx.ConnectError("no network")

    assert GoogleNewsRss(transport=httpx.MockTransport(down)).search("x") == []
    assert GoogleNewsRss(transport=httpx.MockTransport(lambda r: httpx.Response(503))).search("y") == []


# ------------------------------------------------------------------ near, and what counts as near


def _item(title: str, publisher: str = "Patch", days_ago: float = 2, url: str | None = None) -> NewsItem:
    return NewsItem(title=title, url=url or f"https://news.google.com/rss/articles/{abs(hash(title))}", publisher=publisher, published_at=_NOW - timedelta(days=days_ago))


def test_compound_names_are_split_into_the_places_they_name():
    assert _splits("Hunts Bank & Victoria Station Approach") == ["Hunts Bank", "Victoria Station Approach"]
    assert _splits("Mass Ave / Prospect St") == ["Mass Ave", "Prospect St"]
    assert _splits("Ginkaku-ji") == ["Ginkaku-ji"]


def test_a_headline_must_name_the_street_and_the_city_to_be_near_a_street_that_shares_its_name():
    assert not _is_near(_item("Two Strangers to close on Broadway", "Broadway News"), "Broadway", "Cambridge", "Massachusetts")
    assert _is_near(_item("Cambridge police close Broadway after crash", "Patch"), "Broadway", "Cambridge", "Massachusetts")
    assert _is_near(_item("Night market returns to Harvard Square", "Cambridge Day"), "Harvard Square", "Cambridge", "Massachusetts")


def test_an_outlet_named_for_the_area_counts_without_the_city_in_the_headline():
    assert _is_near(_item("Community CPR Training Day", "harvardsquare.com"), "Harvard Square", "Cambridge", "Massachusetts")
    assert not _is_near(_item("Community CPR Training Day", "Patch"), "Harvard Square", "Cambridge", "Massachusetts")
    assert not _is_near(_item("Community CPR Training Day", "Harvard Square News"), "Harvard Square", "Cambridge", "Massachusetts"), "a name inside an outlet's name is not the area's own site"


# ------------------------------------------------------------------ the builder


class _Rss:
    def __init__(self, by_word: dict[str, list[NewsItem]] | None = None) -> None:
        self.by_word, self.queries = by_word or {}, []

    def search(self, query, days=30, country_code=None):
        self.queries.append(query)
        for word, items in self.by_word.items():
            if word.lower() in query.lower():
                return list(items)
        return []


class _Geocoder:
    def __init__(self, address: dict | None = None, fail: bool = False) -> None:
        self.address, self.fail, self.calls = address or {}, fail, 0

    def reverse(self, lat, lon, language="en", zoom=14):
        self.calls += 1
        if self.fail:
            raise RuntimeError("geocoder down")
        return {"address": self.address}


class _Archive:
    def __init__(self, posts=None, fail: bool = False) -> None:
        self.posts, self.fail = posts or [], fail

    def recent(self, location, days):
        if self.fail:
            raise RuntimeError("archive down")
        return list(self.posts)


def _post(i: int, title: str, days_ago: float = 1) -> Evidence:
    return Evidence(
        evidence_id=f"reddit_archive:live_feed:{i}", source_url=f"https://www.reddit.com/r/cambridgema/comments/{i}/a", source_title=title,
        publisher="reddit.com", source_type=SourceType.COMMUNITY_FORUM, retrieved_at=_NOW, published_at=_NOW - timedelta(days=days_ago),
        location_scope="Cambridge", text="", topic="live_feed", metadata={"provider": "reddit_archive"},
    )


def _place(**kw) -> Location:
    base = dict(name="Harvard Square", city="Cambridge", region="Massachusetts", country="United States", country_code="us", slug="h", raw_query="h", latitude=42.37, longitude=-71.12)
    return Location(**{**base, **kw})


_ADDRESS = {"road": "Massachusetts Avenue", "neighbourhood": "Mid-Cambridge", "city": "Cambridge", "country_code": "us"}


def test_the_pins_own_street_and_neighbourhood_are_searched_first_and_the_city_is_not_when_something_is_near():
    rss = _Rss({"Massachusetts Avenue": [_item("Cambridge police close Massachusetts Avenue after a crash", days_ago=1)]})

    feed = LiveFeedTool(rss=rss, geocoder=_Geocoder(_ADDRESS)).fetch(_place(name="Harvard Square"))

    assert [i.metadata["feed_place"] for i in feed] == ["Massachusetts Avenue"]
    assert feed[0].metadata["feed_scope"] == "near" and feed[0].metadata["feed_category"] == "Crime & safety"
    assert all("Harvard Square" in q or "Massachusetts Avenue" in q or "Mid-Cambridge" in q for q in rss.queries), "no city-wide search was sent"


def test_when_nothing_is_near_the_city_is_searched_with_three_facets_and_labelled_as_the_city():
    rss = _Rss({"Massachusetts": [_item("Cambridge shop opens on the square", days_ago=3)]})

    feed = LiveFeedTool(rss=rss, geocoder=_Geocoder(_ADDRESS)).fetch(_place(name="Harvard Square"))

    city_queries = [q for q in rss.queries if q.startswith('"Cambridge"')]
    assert len(city_queries) == 3 and any("police" in q for q in city_queries) and any("festival" in q for q in city_queries)
    assert [i.metadata["feed_scope"] for i in feed] == ["city"] and feed[0].metadata["feed_place"] == "Cambridge"


def test_a_pin_that_is_the_city_itself_has_no_street_and_goes_straight_to_the_city():
    rss = _Rss({"Cambridge": [_item("Cambridge fire crews rescue a family", days_ago=1)]})
    geocoder = _Geocoder({"road": "Broadway", "neighbourhood": "Mid-Cambridge"})

    feed = LiveFeedTool(rss=rss, geocoder=geocoder).fetch(_place(name="Cambridge"))

    assert not any('"Broadway"' in q for q in rss.queries), "the street at a city's centre point says nothing about the city"
    assert [i.metadata["feed_scope"] for i in feed] == ["city"]


def test_a_street_shared_with_something_famous_is_not_taken_for_it():
    rss = _Rss({"Broadway": [_item("Two Strangers to close on Broadway", "Broadway News", 2)], "Cambridge": [_item("Cambridge cafe opens", days_ago=2)]})

    feed = LiveFeedTool(rss=rss, geocoder=_Geocoder({"road": "Broadway", "city": "Cambridge"})).fetch(_place(name="A Cafe"))

    assert [i.metadata["feed_place"] for i in feed] == ["Cambridge"], "nothing near, so the city, and not New York theatre news"


def test_a_community_post_naming_the_street_is_near_and_one_that_does_not_is_the_citys():
    posts = [_post(1, "Abandoned bike on Massachusetts Avenue"), _post(2, "Best pizza tonight?")]

    near = LiveFeedTool(rss=_Rss(), geocoder=_Geocoder(_ADDRESS), reddit_archive=_Archive(posts)).fetch(_place(name="A Cafe"))

    assert [(i.metadata["feed_kind"], i.metadata["feed_scope"], i.metadata["feed_place"]) for i in near] == [("community", "near", "Massachusetts Avenue")]


def test_politics_irrelevant_old_undated_and_repeated_items_never_show_and_the_rest_is_newest_first():
    items = [
        _item("Cambridge shop opens downtown", days_ago=5, url="https://n/1"),
        _item("Cambridge shop opens downtown", "Other Outlet", 5, url="https://n/2"),  # the same headline again
        _item("Cambridge fire crews rescue a family", days_ago=0.5, url="https://n/3"),
        _item("Cambridge Senate race heats up", days_ago=1, url="https://n/4"),
        _item("Where was Cambridge filmed for the movie?", days_ago=1, url="https://n/5"),
        _item("Cambridge storm damage clean-up continues", days_ago=45, url="https://n/6"),
    ]
    rss = _Rss({"Cambridge": items})

    feed = LiveFeedTool(rss=rss).fetch(_place(name="Cambridge", latitude=None, longitude=None))

    assert [i.source_url for i in feed] == ["https://n/3", "https://n/1"]


def test_nothing_in_thirty_days_is_an_empty_feed_and_not_an_error():
    rss = _Rss({"Cambridge": [_item("Cambridge shop opens downtown", days_ago=40)]})

    assert LiveFeedTool(rss=rss).fetch(_place(name="Cambridge")) == []
    assert LiveFeedTool().fetch(_place(name="Cambridge")) == [], "and with no source at all"


def test_a_geocoder_or_archive_that_fails_never_stops_the_feed():
    rss = _Rss({"Cambridge": [_item("Cambridge shop opens downtown", days_ago=2)]})

    feed = LiveFeedTool(rss=rss, geocoder=_Geocoder(fail=True), reddit_archive=_Archive(fail=True)).fetch(_place(name="A Cafe"))

    assert [i.metadata["feed_scope"] for i in feed] == ["city"]


class _Tavily:
    def __init__(self, items) -> None:
        self.items, self.calls = items, 0

    def fetch(self, location, refresh=False):
        self.calls += 1
        return list(self.items)


def _tavily_item() -> Evidence:
    return Evidence(
        evidence_id="t1", source_url="https://example.org/a", source_title="Cambridge council approves a new bike lane", publisher="example.org",
        source_type=SourceType.NEWS, retrieved_at=_NOW, published_at=_NOW - timedelta(days=2), location_scope="Cambridge, Massachusetts",
        text="", topic="live_feed", metadata={"feed_kind": "news", "feed_scope": "area"},
    )


def test_the_billed_search_is_only_a_fallback_for_a_city_the_free_sources_say_little_about():
    busy = _Rss({"Cambridge": [_item(f"Cambridge shop {n} opens downtown", days_ago=n, url=f"https://n/{n}") for n in range(1, 5)]})
    thin = _Rss()
    tavily_busy, tavily_thin = _Tavily([_tavily_item()]), _Tavily([_tavily_item()])

    LiveFeedTool(rss=busy, tavily=tavily_busy).fetch(_place(name="Cambridge"))
    live_feed._FEED_CACHE.clear()
    feed = LiveFeedTool(rss=thin, tavily=tavily_thin).fetch(_place(name="Cambridge"))

    assert tavily_busy.calls == 0, "four free items: no credit spent"
    assert tavily_thin.calls == 1
    assert feed[0].metadata["feed_scope"] == "city" and feed[0].metadata["feed_category"] == "Development & transport"


def test_a_repeat_load_is_served_from_the_cache_and_refresh_sends_new_requests():
    rss = _Rss({"Cambridge": [_item("Cambridge shop opens downtown", days_ago=2)]})
    geocoder = _Geocoder(_ADDRESS)
    tool = LiveFeedTool(rss=rss, geocoder=geocoder)

    tool.fetch(_place(name="Cambridge"))
    sent = len(rss.queries)
    tool.fetch(_place(name="Cambridge"))
    assert len(rss.queries) == sent

    news_rss._CACHE.clear()
    tool.fetch(_place(name="Cambridge"), refresh=True)
    assert len(rss.queries) > sent
