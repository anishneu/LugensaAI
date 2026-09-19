import pytest

from app.models.location import Location
from app.models.plan import Priority, ResearchTopic
from app.tools.base import ToolConfigurationError, ToolExecutionError
from app.tools.tavily_tools import (
    TavilyLiveFeedTool,
    TavilyPageRetrievalTool,
    TavilyWebSearchTool,
    _classify_source_type,
    _clean_text,
    _extract_published_date_from_text,
    _is_relevant_to_community_voice,
    _is_relevant_to_live_feed,
    _is_relevant_to_location,
    _mentions_business,
    _mentions_place_context,
    _truncate_for_display,
)


class FakeTavilyClient:
    def __init__(
        self,
        results: list[dict] | None = None,
        raise_error: bool = False,
        images: list | None = None,
        results_sequence: list[list[dict]] | None = None,
    ) -> None:
        self._results = results or []
        self._raise_error = raise_error
        self._images = images or []
        self._results_sequence = results_sequence
        self.queries: list[str] = []
        self.topics: list[str | None] = []

    def search(
        self,
        query: str,
        max_results: int,
        include_raw_content: bool,
        include_images: bool,
        time_range: str | None = None,
        topic: str | None = None,
        days: int | None = None,
    ) -> dict:
        self.queries.append(query)
        self.topics.append(topic)
        if self._raise_error:
            raise RuntimeError("simulated network failure")
        if self._results_sequence is not None:
            call_index = min(len(self.queries) - 1, len(self._results_sequence) - 1)
            return {"results": self._results_sequence[call_index], "images": self._images}
        return {"results": self._results, "images": self._images}


def _topic(topic_id: str = "housing") -> ResearchTopic:
    return ResearchTopic(
        topic_id=topic_id,
        reason="r",
        search_queries=["Harvard Square housing"],
        preferred_source_types=[],
        expected_evidence="e",
        priority=Priority.HIGH,
        completion_criteria="c",
    )


def test_search_returns_evidence_and_caches_raw_content(harvard_square):
    client = FakeTavilyClient(
        results=[
            {
                "url": "https://cambridgema.gov/housing-info",
                "title": "Cambridge Housing Info",
                "content": "Short snippet about housing near Harvard Square today.",
                "raw_content": "Much longer full page text about housing near Harvard Square.",
                "published_date": "2025-06-01",
            }
        ]
    )
    tool = TavilyWebSearchTool(client=client)

    evidence = tool.search(harvard_square, _topic())

    assert len(evidence) == 1
    item = evidence[0]
    assert item.source_url == "https://cambridgema.gov/housing-info"
    assert item.text == "Short snippet about housing near Harvard Square today."
    assert item.topic == "housing"
    assert item.metadata["provider"] == "tavily"
    assert tool.raw_content_cache[item.source_url] == "Much longer full page text about housing near Harvard Square."
    assert client.queries == ["Harvard Square housing"]


def test_page_retrieval_reads_from_shared_cache(harvard_square):
    client = FakeTavilyClient(
        results=[
            {
                "url": "https://example.org/a",
                "title": "Harvard Square guide",
                "content": "A reasonably long snippet about Harvard Square for testing the cache.",
                "raw_content": "A reasonably long full text body about Harvard Square used to test the cache.",
            }
        ]
    )
    search_tool = TavilyWebSearchTool(client=client)
    search_tool.search(harvard_square, _topic())
    retrieval_tool = TavilyPageRetrievalTool(search_tool.raw_content_cache)

    assert (
        retrieval_tool.retrieve_full_text("https://example.org/a")
        == "A reasonably long full text body about Harvard Square used to test the cache."
    )
    assert retrieval_tool.retrieve_full_text("https://example.org/unknown") is None


def test_search_wraps_client_errors(harvard_square):
    tool = TavilyWebSearchTool(client=FakeTavilyClient(raise_error=True))

    with pytest.raises(ToolExecutionError):
        tool.search(harvard_square, _topic())


def test_missing_api_key_and_client_raises_configuration_error():
    with pytest.raises(ToolConfigurationError):
        TavilyWebSearchTool()


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://cambridgema.gov/page", "local_government"),
        ("https://harvard.edu/page", "academic"),
        ("https://www.reddit.com/r/boston", "community_forum"),
        ("https://www.yelp.com/biz/x", "review_aggregator"),
        ("https://someblog.medium.com/post", "blog"),
        ("https://randomsite.example.com/page", "other"),
    ],
)
def test_classify_source_type(url, expected):
    assert _classify_source_type(url).value == expected


def test_clean_text_strips_markdown_and_boilerplate_noise():
    dirty = (
        "![alt text](https://example.com/pic.png)\n"
        "### Chapters\n"
        "[0:00] Intro\n"
        "[Get our App](https://apps.apple.com/app/id123)\n"
        "[Learn more](https://example.com) about the neighborhood.\n\n\n"
        "This   has  extra   spaces."
    )

    cleaned = _clean_text(dirty)

    assert "![" not in cleaned
    assert "###" not in cleaned
    assert "[0:00]" not in cleaned
    assert "apps.apple.com" not in cleaned
    assert "Learn more about the neighborhood." in cleaned
    assert "This has extra spaces." in cleaned


def test_clean_text_strips_nav_menu_lines():
    dirty = (
        "Renting Tools | Renter University | Apartment Life | Rentals Near Me | Find Your Perfect Place\n"
        "Student Apartments for Rent in the Harvard Square Neighborhood of Cambridge, MA (136 Rentals)"
    )

    cleaned = _clean_text(dirty)

    assert "Renting Tools" not in cleaned
    assert "Student Apartments for Rent in the Harvard Square Neighborhood" in cleaned


def test_clean_text_strips_bullet_nav_footer_blocks():
    dirty = (
        "Real article content about the neighborhood goes here.\n\n"
        "* About\n* News\n* Media Assets\n* Investor Relations\n* Blog\n* Careers\n* Help"
    )

    cleaned = _clean_text(dirty)

    assert "Real article content about the neighborhood goes here." in cleaned
    assert "Investor Relations" not in cleaned


def test_truncate_for_display_leaves_short_text_untouched():
    assert _truncate_for_display("short text") == "short text"


def test_truncate_for_display_caps_long_text_with_ellipsis():
    long_text = "word " * 500

    truncated = _truncate_for_display(long_text, limit=100)

    assert len(truncated) <= 102
    assert truncated.endswith("…")


def test_clean_text_drops_known_platform_ui_chrome():
    dirty = (
        "Real safety commentary about the neighborhood.\n"
        "Log In\n"
        "Log In\n"
        "Forgot Account?\n"
        "Video Home\n"
        "Live Reels\n"
        "Explore More\n"
    )

    cleaned = _clean_text(dirty)

    assert "Real safety commentary about the neighborhood." in cleaned
    assert "Log In" not in cleaned
    assert "Live Reels" not in cleaned


def test_clean_text_drops_tripadvisor_style_breadcrumb_nav():
    """Regression test for a real bug found live: a TripAdvisor-style review
    aggregator page's whole top nav (Skip to main content, Plan with AI,
    Rewards, Discover, Review, USD, Sign in, and a breadcrumb of category
    links glued together with inconsistent spacing) was rendered directly
    inside a Community card instead of being stripped."""
    dirty = (
        "Real, specific customer commentary about the cafe's coffee and staff.\n"
        "Skip to main content\n\n"
        "Plan with AI\n\n"
        "Rewards\n\n"
        "Discover\n\n"
        "Review\n\n"
        "USD\n\n"
        "Sign in\n\n"
        "BostonThings to DoHotelsRestaurantsCruisesForums\n\n"
        "United States\n"
    )

    cleaned = _clean_text(dirty)

    assert "Real, specific customer commentary about the cafe's coffee and staff." in cleaned
    assert "Skip to main content" not in cleaned
    assert "Plan with AI" not in cleaned
    assert "Rewards" not in cleaned
    assert "Sign in" not in cleaned
    assert "ThingsToDo" not in cleaned.replace(" ", "")
    assert "HotelsRestaurantsCruisesForums" not in cleaned


def test_clean_text_drops_tourism_site_and_social_share_boilerplate():
    """Regression test for a real bug found live: a Boston tourism site's
    browser-compatibility notice, e-newsletter/store nag lines, and a
    social-share widget's link labels were rendered directly inside a
    quoted evidence excerpt instead of being stripped."""
    dirty = (
        "Your browser is not supported for this experience.\n"
        "We recommend using Chrome, Firefox, Edge, or Safari.\n\n"
        "Skip navigation\n\n"
        "Getting Around Boston is easy with the T subway system and buses.\n\n"
        "Share\n\n"
        "Share on Facebook\n\n"
        "Share on Twitter\n\n"
        "Share on Linkedin\n"
    )

    cleaned = _clean_text(dirty)

    assert "Getting Around Boston is easy with the T subway system and buses." in cleaned
    assert "not supported for this experience" not in cleaned
    assert "Skip navigation" not in cleaned
    assert "Share on Facebook" not in cleaned


def test_clean_text_deduplicates_repeated_paragraphs():
    dirty = (
        "16 friendliest neighborhood to live in Cambridge, MA\n\n"
        "Where is this data from?\n\n"
        "16 friendliest neighborhood to live in Cambridge, MA\n\n"
        "A unique closing paragraph that only appears once."
    )

    cleaned = _clean_text(dirty)

    assert cleaned.count("16 friendliest neighborhood to live in Cambridge, MA") == 1
    assert "A unique closing paragraph that only appears once." in cleaned


def test_clean_text_does_not_strip_legitimate_short_data_lines():
    """Regression guard: a crime-statistics table is short lines of real,
    safety-relevant data — exactly what this project wants surfaced, and
    must not be caught by the junk-line or nav heuristics."""
    table = "Location\nOverall\nViolent\nProperty\nCambridge\n0\n0\n0\nMassachusetts\n21.56\n10.85\n10.71"

    cleaned = _clean_text(table)

    assert "Massachusetts" in cleaned
    assert "21.56" in cleaned


def test_is_relevant_to_location_matches_name_or_city(harvard_square):
    assert _is_relevant_to_location("Living near Harvard Square is great", harvard_square)
    assert _is_relevant_to_location("Cambridge apartments for rent", harvard_square)
    assert not _is_relevant_to_location("Why Living Past 115 Is Almost Impossible", harvard_square)


def test_search_drops_results_that_never_mention_the_location(harvard_square):
    client = FakeTavilyClient(
        results=[
            {
                "url": "https://example.org/on-topic",
                "title": "Harvard Square apartment guide",
                "content": "Rentals near Harvard Square, Cambridge, typically range from $1,800 to $3,200 per month.",
            },
            {
                "url": "https://example.org/off-topic",
                "title": "Why Living Past 115 Is Almost Impossible",
                "content": "Longevity clinics and Gompertz law explained.",
            },
        ]
    )
    tool = TavilyWebSearchTool(client=client)

    evidence = tool.search(harvard_square, _topic())

    assert {e.source_url for e in evidence} == {"https://example.org/on-topic"}


def test_search_keeps_everything_if_nothing_mentions_the_location(harvard_square):
    """A topic with zero evidence is more honest than one with silently-swapped
    off-topic evidence — but only as a last resort when literally nothing matched."""
    client = FakeTavilyClient(
        results=[
            {
                "url": "https://example.org/unrelated",
                "title": "Totally unrelated",
                "content": "Nothing to do with it at all, completely unrelated content here.",
            }
        ]
    )
    tool = TavilyWebSearchTool(client=client)

    evidence = tool.search(harvard_square, _topic())

    assert len(evidence) == 1
    assert evidence[0].metadata.get("location_match") == "false"


def test_search_pairs_images_with_results_by_position(harvard_square):
    client = FakeTavilyClient(
        results=[
            {
                "url": "https://example.org/a",
                "title": "Harvard Square guide",
                "content": "About Harvard Square and its many local attractions.",
            },
            {
                "url": "https://example.org/b",
                "title": "Harvard Square news",
                "content": "More Harvard Square info for visitors and residents alike.",
            },
        ],
        images=["https://example.org/img-a.jpg", {"url": "https://example.org/img-b.jpg"}],
    )
    tool = TavilyWebSearchTool(client=client)

    evidence = tool.search(harvard_square, _topic())

    by_url = {e.source_url: e for e in evidence}
    assert by_url["https://example.org/a"].image_url == "https://example.org/img-a.jpg"
    assert by_url["https://example.org/b"].image_url == "https://example.org/img-b.jpg"


def test_live_feed_requests_recency_and_labels_topic_live_feed(harvard_square):
    client = FakeTavilyClient(
        results=[
            {
                "url": "https://example.org/recent-post",
                "title": "Cambridge community roundup",
                "content": "A recent discussion thread about goings-on in Cambridge, MA, posted this week.",
                "published_date": "Wed, 16 Sep 2026 15:14:23 GMT",
            }
        ]
    )
    tool = TavilyLiveFeedTool(client=client)

    feed = tool.fetch(harvard_square)

    assert len(feed) == 1
    assert feed[0].topic == "live_feed"
    assert feed[0].published_at is not None
    assert "Cambridge" in client.queries[0]
    # The news topic is what actually returns real publication timestamps.
    assert client.topics[0] == "news"


def test_live_feed_drops_results_with_no_real_publication_date(harvard_square):
    """A feed whose whole claim is recency must not backfill an unknown post
    time with the time it happened to be fetched. Undated results are also,
    in practice, the evergreen city landing pages rather than real posts."""
    client = FakeTavilyClient(
        results=[
            {
                "url": "https://example.org/evergreen-landing-page",
                "title": "Community Events in Cambridge, MA - Local Gatherings & Activities",
                "content": "Browse upcoming community events and activities happening in Cambridge all year.",
            },
            {
                "url": "https://example.org/real-article",
                "title": "Cambridge council approves new bike lane",
                "content": "The Cambridge, MA city council voted on Tuesday to approve a protected bike lane.",
                "published_date": "Wed, 16 Sep 2026 15:14:23 GMT",
            },
        ]
    )
    tool = TavilyLiveFeedTool(client=client)

    feed = tool.fetch(harvard_square)

    assert [e.source_url for e in feed] == ["https://example.org/real-article"]


def test_live_feed_keeps_local_reporting_whose_headline_omits_the_city(harvard_square):
    """Regional coverage often names only a neighborhood in the headline
    ("Arlington puts bid for Red Line extension"). The publisher/URL carries
    the regional signal in that case, and dropping those would gut exactly
    the local reporting this feed exists to surface."""
    client = FakeTavilyClient(
        results=[
            {
                "url": "https://www.nbccambridge.com/news/politics/arlington-red-line-bid",
                "title": "Arlington puts bid for Red Line extension",
                "content": "Town officials in MA submitted a funding request for the transit extension this week.",
                "published_date": "Thu, 17 Sep 2026 09:00:00 GMT",
            }
        ]
    )
    tool = TavilyLiveFeedTool(client=client)

    feed = tool.fetch(harvard_square)

    assert len(feed) == 1


def test_live_feed_always_queries_the_region_not_the_specific_poi(starbucks_cambridge):
    """The feed reports on the broader region, not the exact selected place
    -- the query itself should never key off a POI's own (often generic,
    e.g. a chain business) name."""
    client = FakeTavilyClient(results=[])

    TavilyLiveFeedTool(client=client).fetch(starbucks_cambridge)

    assert client.queries, "expected at least one regional query"
    for query in client.queries:
        assert "Starbucks" not in query
        assert "Cambridge" in query


def test_live_feed_region_is_derived_dynamically_not_hardcoded():
    """Regional scope must come from whatever location was actually
    selected -- not hardcoded to any one city."""
    seattle = Location(
        name="Pike Place Market",
        city="Seattle",
        region="WA",
        country="US",
        slug="pike-place-seattle-wa",
        raw_query="Pike Place Market, Seattle, WA",
    )
    client = FakeTavilyClient(results=[])

    TavilyLiveFeedTool(client=client).fetch(seattle)

    assert "Seattle" in client.queries[0]
    assert "Boston" not in client.queries[0]
    assert "Cambridge" not in client.queries[0]


def test_live_feed_sorts_newest_first(harvard_square):
    client = FakeTavilyClient(
        results=[
            {
                "url": "https://example.org/older",
                "title": "Older Cambridge news",
                "content": "An older discussion thread about the Cambridge, MA area from a while back.",
                "published_date": "Mon, 06 Jan 2025 10:00:00 GMT",
            },
            {
                "url": "https://example.org/newer",
                "title": "Newer Cambridge news",
                "content": "A brand new discussion thread about the Cambridge, MA area posted recently.",
                "published_date": "Tue, 15 Sep 2026 10:00:00 GMT",
            },
        ]
    )
    tool = TavilyLiveFeedTool(client=client)

    feed = tool.fetch(harvard_square)

    assert [e.source_url for e in feed] == ["https://example.org/newer", "https://example.org/older"]


def test_live_feed_drops_results_that_never_mention_the_region():
    """Unlike per-topic research search, the live feed has no verified
    pipeline downstream to catch a bad match — the location filter here is
    not soft."""
    client = FakeTavilyClient(
        results=[
            {
                "url": "https://example.org/unrelated",
                "title": "Totally unrelated post",
                "content": "This discussion thread has nothing to do with the place in question.",
                "published_date": "Tue, 15 Sep 2026 10:00:00 GMT",
            }
        ]
    )
    tool = TavilyLiveFeedTool(client=client)

    assert tool.fetch(Location(
        name="Harvard Square", city="Cambridge", region="MA", country="US",
        slug="harvard-square-cambridge-ma", raw_query="Harvard Square, Cambridge, MA",
    )) == []


def test_live_feed_drops_a_result_where_the_region_is_only_a_passing_mention():
    """Regression test for a real bug found live: a broad regional query
    surfaced a completely unrelated hockey-forum thread and an off-topic
    court case article, each of which happened to name-check "Boston" once
    in passing -- neither is actually regional activity."""
    boston = Location(
        name="McKenna's Cafe", city="Boston", region="MA", country="US",
        slug="mckennas-cafe-boston-ma", raw_query="McKenna's Cafe, Boston, MA",
    )
    client = FakeTavilyClient(
        results=[
            {
                "url": "https://example.org/hockey-thread",
                "title": "Daily Free Talk / Armchair GM Thread: r/leafs",
                "content": "Boston has a good defense this year but our forwards need work heading into the playoffs.",
                "published_date": "Tue, 15 Sep 2026 10:00:00 GMT",
            },
            {
                "url": "https://example.org/boston-news",
                "title": "New development planned near South Boston waterfront",
                "content": "Boston, MA city officials announced a new development proposal for South Boston this week.",
                "published_date": "Wed, 16 Sep 2026 10:00:00 GMT",
            },
        ]
    )
    tool = TavilyLiveFeedTool(client=client)

    feed = tool.fetch(boston)

    assert [e.source_url for e in feed] == ["https://example.org/boston-news"]


def test_live_feed_deduplicates_repeated_urls():
    boston = Location(
        name="McKenna's Cafe", city="Boston", region="MA", country="US",
        slug="mckennas-cafe-boston-ma", raw_query="McKenna's Cafe, Boston, MA",
    )
    client = FakeTavilyClient(
        results=[
            {
                "url": "https://example.org/dup",
                "title": "Boston news roundup",
                "content": "Boston, MA recent local activity roundup for this week in Boston.",
                "published_date": "Wed, 16 Sep 2026 10:00:00 GMT",
            },
            {
                "url": "https://example.org/dup",
                "title": "Boston news roundup",
                "content": "Boston, MA recent local activity roundup for this week in Boston.",
                "published_date": "Wed, 16 Sep 2026 10:00:00 GMT",
            },
        ]
    )
    tool = TavilyLiveFeedTool(client=client)

    feed = tool.fetch(boston)

    assert len(feed) == 1


def test_is_relevant_to_live_feed_accepts_a_hyper_local_outlet_outright(starbucks_cambridge):
    """A city's own .gov site or local paper rarely names its state — the
    domain itself is the strongest locality signal there is."""
    assert _is_relevant_to_live_feed(
        "City responds to federal funding changes",
        "The city announced its response this week.",
        starbucks_cambridge,
        source="https://www.cambridgema.gov/news/2026/09/response",
    )
    assert _is_relevant_to_live_feed(
        "Zoning rethink; fall sports; turkeys",
        "A roundup of this week's local stories.",
        starbucks_cambridge,
        source="https://www.cambridgeday.com/2026/09/17/roundup",
    )


def test_is_relevant_to_live_feed_requires_the_state_for_non_local_outlets(starbucks_cambridge):
    """Regression test for a real false positive: a Cambridge, MA query
    surfaced a New York State Police report, because there is also a
    Cambridge, New York."""
    assert not _is_relevant_to_live_feed(
        "New York State Police Public Information Report",
        "Troopers responded to an incident in Cambridge over the weekend.",
        starbucks_cambridge,
        source="https://publicapps.troopers.ny.gov/reports/weekly.pdf",
    )
    assert _is_relevant_to_live_feed(
        "2nd man arrested on murder charge in killing of Cambridge worker",
        "Police in Cambridge, MA said the suspect was arrested Wednesday.",
        starbucks_cambridge,
        source="https://www.masslive.com/news/2026/09/arrest.html",
    )


def test_live_feed_drops_job_listings(harvard_square):
    """Regression test for real results: a company careers page names the
    city its office is in and carries a real posted date, so it passes both
    the date and locality checks — but an open role isn't local activity."""
    client = FakeTavilyClient(
        results=[
            {
                "url": "https://jobs.example.com/head-marketing-cambridge",
                "title": "Head of Marketing, Cambridge MA",
                "content": "A role based in our Cambridge, MA office.",
                "published_date": "Wed, 16 Sep 2026 15:14:23 GMT",
            },
            {
                "url": "https://www.masslive.com/news/2026/09/hiring.html",
                "title": "Cambridge biotech announces 200 new hires",
                "content": "The Cambridge, MA company said it would expand its workforce.",
                "published_date": "Wed, 16 Sep 2026 16:00:00 GMT",
            },
        ]
    )

    feed = TavilyLiveFeedTool(client=client).fetch(harvard_square)

    assert [e.source_url for e in feed] == ["https://www.masslive.com/news/2026/09/hiring.html"]


def test_is_relevant_to_live_feed_rejects_a_passing_mention(starbucks_cambridge):
    assert not _is_relevant_to_live_feed(
        "I love my local Starbucks", "mentioned Cambridge once", starbucks_cambridge, source="https://example.org/x"
    )


def test_live_feed_wraps_client_errors(harvard_square):
    tool = TavilyLiveFeedTool(client=FakeTavilyClient(raise_error=True))

    with pytest.raises(ToolExecutionError):
        tool.fetch(harvard_square)


def test_live_feed_survives_one_facet_query_failing(harvard_square):
    """The feed issues several complementary searches; one failing should
    degrade the result, not blank the whole sidebar."""

    class FlakyClient(FakeTavilyClient):
        def search(self, query: str, **kwargs):
            if "police" in query:
                raise RuntimeError("simulated failure for one facet")
            return super().search(query, **kwargs)

    client = FlakyClient(
        results=[
            {
                "url": "https://example.org/article",
                "title": "Cambridge council approves new bike lane",
                "content": "The Cambridge, MA city council voted on Tuesday to approve a protected bike lane.",
                "published_date": "Wed, 16 Sep 2026 15:14:23 GMT",
            }
        ]
    )

    feed = TavilyLiveFeedTool(client=client).fetch(harvard_square)

    assert [e.source_url for e in feed] == ["https://example.org/article"]


def test_live_feed_missing_api_key_and_client_raises_configuration_error():
    with pytest.raises(ToolConfigurationError):
        TavilyLiveFeedTool()


def test_live_feed_sorts_results_that_mix_date_formats(harvard_square):
    """Tavily returns bare ISO dates from one topic and RFC-2822 from another.
    A naive datetime among aware ones makes any comparison raise TypeError, so
    a mixed feed would crash the sort rather than merely look untidy."""
    client = FakeTavilyClient(
        results=[
            {
                "url": "https://example.org/iso-dated",
                "title": "Cambridge council approves new bike lane",
                "content": "The Cambridge, MA city council voted to approve a protected bike lane.",
                "published_date": "2026-09-14",
            },
            {
                "url": "https://example.org/rfc-dated",
                "title": "Cambridge fire department hosts CPR training",
                "content": "The Cambridge, MA fire department announced a training day.",
                "published_date": "Wed, 16 Sep 2026 15:14:23 GMT",
            },
        ]
    )

    feed = TavilyLiveFeedTool(client=client).fetch(harvard_square)

    assert [e.source_url for e in feed] == [
        "https://example.org/rfc-dated",
        "https://example.org/iso-dated",
    ]
    assert all(e.published_at.tzinfo is not None for e in feed)


def test_clean_text_strips_skip_links_and_markdown_escape_artifacts():
    r"""Found while testing a markdown-converting scraper: such extractors leave stray
    backslash escapes behind, and run accessibility skip-links together inline
    ("Skip navigation Skip to main content") where a whole-line denylist
    can't reach them."""
    dirty = r"Skip navigation Skip to main content \ \ Real reporting about the neighborhood follows here."

    cleaned = _clean_text(dirty)

    assert "Real reporting about the neighborhood follows here." in cleaned
    assert "Skip navigation" not in cleaned
    assert "Skip to main content" not in cleaned
    assert "\\" not in cleaned


def test_extract_published_date_from_text_reads_tripadvisor_review_dates():
    """Measured against the live API: TripAdvisor's own search-result text
    always has a null `published_date` field, but the raw page text it comes
    with names a real date in plain English ("Reviewed July 30, 2016")."""
    text = "Reviewed July 30, 2016\nGreat walkable square with lots of shops."

    parsed = _extract_published_date_from_text(text)

    assert parsed is not None
    assert (parsed.year, parsed.month, parsed.day) == (2016, 7, 30)
    assert parsed.tzinfo is not None


def test_extract_published_date_from_text_reads_posted_phrasing():
    parsed = _extract_published_date_from_text("Posted on January 5, 2024 by a longtime resident.")

    assert parsed is not None
    assert (parsed.year, parsed.month, parsed.day) == (2024, 1, 5)


def test_extract_published_date_from_text_returns_none_without_a_recognized_phrase():
    """A wrong guess is worse than an honest 'unknown' -- a bare date-shaped
    number elsewhere on the page (a price, a phone number) must not be
    mistaken for a real post date."""
    assert _extract_published_date_from_text("Table for 4, 2024 available at 7pm.") is None
    assert _extract_published_date_from_text("") is None


def test_search_recovers_a_real_date_for_tripadvisor_style_results(harvard_square):
    """Tavily's `published_date` field is null for this source (measured
    live), but the review text itself names a real date -- that should be
    recovered instead of leaving the item with no timestamp at all."""
    client = FakeTavilyClient(
        results=[
            {
                "url": "https://www.tripadvisor.com/ShowUserReviews-harvard-square",
                "title": "Safe and Clean to walk around - Review of Harvard Square",
                "content": "Great walkable square, felt safe throughout our visit to Harvard Square.",
                "raw_content": "Reviewed July 30, 2016\nGreat walkable square, felt safe throughout our visit to "
                "Harvard Square.",
                "published_date": None,
            }
        ]
    )

    evidence = TavilyWebSearchTool(client=client).search(harvard_square, _topic())

    assert len(evidence) == 1
    assert evidence[0].published_at is not None
    assert evidence[0].published_at.year == 2016


def test_is_relevant_to_community_voice_requires_city_and_region(starbucks_cambridge):
    """Regression coverage for the same class of bug the live feed hit: a
    generic chain name ("Starbucks") mentioned near a bare city name isn't
    enough to trust which branch a comment is actually about."""
    assert not _is_relevant_to_community_voice(
        "Great local Starbucks",
        "This Starbucks in Cambridge has good service.",
        starbucks_cambridge,
        source="https://www.yelp.com/biz/some-starbucks-seattle",
    )
    assert _is_relevant_to_community_voice(
        "Great local Starbucks",
        "This Starbucks in Cambridge, MA has good service and is close to campus.",
        starbucks_cambridge,
        source="https://www.yelp.com/biz/starbucks-cambridge-ma",
    )


def test_is_relevant_to_community_voice_trusts_a_distinctive_multi_word_name(harvard_square):
    """A specific, multi-word place name is distinctive enough on its own to
    stand in for a region mention (unlike a single generic chain word)."""
    assert _is_relevant_to_community_voice(
        "Living near Harvard Square",
        "Harvard Square is walkable and has a lot of shops in Cambridge.",
        harvard_square,
        source="https://www.reddit.com/r/CambridgeMA/comments/xyz",
    )


def test_is_relevant_to_community_voice_accepts_hyper_local_domain(starbucks_cambridge):
    assert _is_relevant_to_community_voice(
        "Neighborhood roundup",
        "Notes on the Starbucks that just reopened.",
        starbucks_cambridge,
        source="https://www.cambridgeday.com/2026/09/roundup",
    )


def test_search_drops_off_topic_forum_results_even_when_soft_filter_would_keep_them(starbucks_cambridge):
    """The soft per-topic filter (`_is_relevant_to_location`) matches on the
    bare chain name alone and would let this through; the stricter
    Community-Voices-only check must still drop it."""
    client = FakeTavilyClient(
        results=[
            {
                "url": "https://www.yelp.com/biz/some-starbucks-seattle",
                "title": "Starbucks review",
                "content": "This Starbucks location has friendly baristas and fast service every morning.",
            }
        ]
    )

    evidence = TavilyWebSearchTool(client=client).search(starbucks_cambridge, _topic())

    assert evidence == []


def test_mentions_business_requires_its_distinguishing_words_not_just_the_kind_of_place():
    """Regression test for a real mix-up: "LEAVES Coffee Roasters" shares
    "coffee" and "roasters" with "SR Coffee Roaster & Bar", and its reviews
    were cited as evidence about the wrong cafe."""
    name = "SR Coffee Roaster & Bar"

    assert _mentions_business("SR Coffee Roasters in Nihonbashi has great espresso", name)
    assert not _mentions_business("LEAVES Coffee Roasters has a strong following among coffee enthusiasts", name)
    assert not _mentions_business("Best coffee roasters and bars in Tokyo", name)


def test_mentions_business_falls_back_to_the_whole_phrase_for_a_purely_generic_name():
    assert _mentions_business("We went to Coffee Shop on Main Street", "Coffee Shop")
    assert not _mentions_business("A nice shop that sells coffee", "Coffee Shop")


def test_mentions_business_ignores_apostrophes():
    assert _mentions_business("Tomods has friendly staff", "Tomod's")


def test_business_search_drops_pages_about_other_businesses_with_no_soft_fallback(harvard_square):
    business = harvard_square.model_copy(update={"name": "SR Coffee Roaster & Bar", "is_business": True})
    client = FakeTavilyClient(
        results=[
            {
                "url": "https://example.jp/sr",
                "title": "SR Coffee Roasters review",
                "content": "SR Coffee Roasters in Cambridge serves a lovely flat white and the staff are kind.",
            },
            {
                "url": "https://example.jp/leaves",
                "title": "LEAVES Coffee Roasters review",
                "content": "LEAVES Coffee Roasters has a strong following among coffee enthusiasts.",
            },
        ]
    )

    evidence = TavilyWebSearchTool(client=client).search(business, _topic())

    assert [e.source_url for e in evidence] == ["https://example.jp/sr"]


def test_business_search_returns_nothing_rather_than_another_places_pages(harvard_square):
    business = harvard_square.model_copy(update={"name": "SR Coffee Roaster & Bar", "is_business": True})
    client = FakeTavilyClient(
        results=[
            {
                "url": "https://example.jp/leaves",
                "title": "LEAVES Coffee Roasters review",
                "content": "LEAVES Coffee Roasters has a strong following among coffee enthusiasts.",
            }
        ]
    )

    assert TavilyWebSearchTool(client=client).search(business, _topic()) == []


def test_a_same_named_business_in_another_city_is_rejected(harvard_square):
    """Regression test from a live run: "SR Coffee Roaster & Bar" in Tokyo
    matched a Yelp page for "SR Coffee" in Leesburg, Virginia on the name alone."""
    tokyo = harvard_square.model_copy(
        update={"name": "SR Coffee Roaster & Bar", "city": "Chuo", "region": "Tokyo", "country": "Japan", "is_business": True}
    )
    client = FakeTavilyClient(
        results=[
            {
                "url": "https://www.yelp.com/biz/sr-coffee-leesburg-3",
                "title": "SR Coffee - Leesburg, VA",
                "content": "The first time I came to SR Coffee I felt the food was overpriced and I didn't enjoy it.",
            },
            {
                "url": "https://tabelog.com/en/tokyo/A1302/13250783",
                "title": "SR Coffee roaster & Bar - Kayabacho, Tokyo",
                "content": "SR Coffee roaster & Bar is a cafe near Kayabacho station in Nihonbashi, Tokyo.",
            },
        ]
    )

    evidence = TavilyWebSearchTool(client=client).search(tokyo, _topic())

    assert [e.source_url for e in evidence] == ["https://tabelog.com/en/tokyo/A1302/13250783"]


def test_place_context_is_skipped_when_the_location_names_nothing_to_check(harvard_square):
    nowhere = harvard_square.model_copy(update={"city": None, "region": None, "country": None})

    assert _mentions_place_context("anything at all", nowhere)
