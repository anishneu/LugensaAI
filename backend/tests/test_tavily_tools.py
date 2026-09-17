import pytest

from app.models.plan import Priority, ResearchTopic
from app.tools.base import ToolConfigurationError, ToolExecutionError
from app.tools.tavily_tools import (
    TavilyLiveFeedTool,
    TavilyPageRetrievalTool,
    TavilyWebSearchTool,
    _classify_source_type,
    _clean_text,
    _is_relevant_to_live_feed,
    _is_relevant_to_location,
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

    def search(
        self,
        query: str,
        max_results: int,
        include_raw_content: bool,
        include_images: bool,
        time_range: str | None = None,
    ) -> dict:
        self.queries.append(query)
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
                "title": "Harvard Square this week",
                "content": "A recent discussion thread about Harvard Square, Cambridge, posted this week.",
                "published_date": "2026-09-15",
            }
        ]
    )
    tool = TavilyLiveFeedTool(client=client)

    feed = tool.fetch(harvard_square)

    assert len(feed) == 1
    assert feed[0].topic == "live_feed"
    assert "Harvard Square" in client.queries[0]


def test_live_feed_sorts_newest_first(harvard_square):
    client = FakeTavilyClient(
        results=[
            {
                "url": "https://example.org/older",
                "title": "Older Harvard Square post",
                "content": "An older discussion thread about Harvard Square, Cambridge, from a while back.",
                "published_date": "2025-01-01",
            },
            {
                "url": "https://example.org/newer",
                "title": "Newer Harvard Square post",
                "content": "A brand new discussion thread about Harvard Square, Cambridge, posted recently.",
                "published_date": "2026-09-15",
            },
        ]
    )
    tool = TavilyLiveFeedTool(client=client)

    feed = tool.fetch(harvard_square)

    assert [e.source_url for e in feed] == ["https://example.org/newer", "https://example.org/older"]


def test_live_feed_drops_results_that_never_mention_the_location_without_fallback(harvard_square):
    """Unlike per-topic research search, the live feed has no verified
    pipeline downstream to catch a bad match — the location filter here is
    not soft."""
    client = FakeTavilyClient(
        results=[
            {
                "url": "https://example.org/unrelated",
                "title": "Totally unrelated post",
                "content": "This discussion thread has nothing to do with the place in question.",
            }
        ]
    )
    tool = TavilyLiveFeedTool(client=client)

    assert tool.fetch(harvard_square) == []


def test_live_feed_drops_results_that_mention_only_a_generic_chain_name(starbucks_cambridge):
    """Regression test for a real bug found live: searching a chain business
    like "Starbucks, Cambridge" returned nationwide Starbucks content (a
    Rockville MD apartment post, a Philly hiring thread) because the old
    filter accepted a name-only match, and "Starbucks" alone is not
    distinctive enough to mean anything about location."""
    client = FakeTavilyClient(
        results=[
            {
                "url": "https://example.org/unrelated-starbucks",
                "title": "Starbucks hiring thread",
                "content": "Just applied to a Starbucks near me, they said $19/hr to start working there.",
            },
            {
                "url": "https://example.org/on-topic-starbucks",
                "title": "Starbucks in Cambridge closing early",
                "content": "The Starbucks on Mass Ave in Cambridge is closing early this week for renovations.",
            },
        ]
    )
    tool = TavilyLiveFeedTool(client=client)

    feed = tool.fetch(starbucks_cambridge)

    assert [e.source_url for e in feed] == ["https://example.org/on-topic-starbucks"]


def test_live_feed_falls_back_to_area_level_query_when_poi_query_finds_nothing(starbucks_cambridge):
    """A single Starbucks branch rarely has recent web content naming it
    specifically -- the feed should fall back to area-level activity rather
    than showing nothing, since it promises "what's being said in this
    region", not "about this exact business"."""
    client = FakeTavilyClient(
        results_sequence=[
            [
                {
                    "url": "https://example.org/unrelated-starbucks",
                    "title": "Starbucks hiring thread",
                    "content": "Just applied to a Starbucks near me, they said $19/hr to start working there.",
                }
            ],
            [
                {
                    "url": "https://example.org/cambridge-news",
                    "title": "Cambridge council meeting recap",
                    "content": "This week's Cambridge city council meeting covered zoning changes downtown.",
                }
            ],
        ]
    )
    tool = TavilyLiveFeedTool(client=client)

    feed = tool.fetch(starbucks_cambridge)

    assert len(client.queries) == 2
    assert [e.source_url for e in feed] == ["https://example.org/cambridge-news"]


def test_is_relevant_to_live_feed_requires_city_when_known(starbucks_cambridge):
    assert _is_relevant_to_live_feed("The Starbucks in Cambridge just reopened", starbucks_cambridge)
    assert not _is_relevant_to_live_feed("I love my local Starbucks in Rockville", starbucks_cambridge)


def test_live_feed_wraps_client_errors(harvard_square):
    tool = TavilyLiveFeedTool(client=FakeTavilyClient(raise_error=True))

    with pytest.raises(ToolExecutionError):
        tool.fetch(harvard_square)


def test_live_feed_missing_api_key_and_client_raises_configuration_error():
    with pytest.raises(ToolConfigurationError):
        TavilyLiveFeedTool()
