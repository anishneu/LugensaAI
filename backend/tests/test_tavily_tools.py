import pytest

from app.models.plan import Priority, ResearchTopic
from app.tools.base import ToolConfigurationError, ToolExecutionError
from app.tools.tavily_tools import (
    TavilyPageRetrievalTool,
    TavilyWebSearchTool,
    _classify_source_type,
    _clean_text,
    _is_relevant_to_location,
    _truncate_for_display,
)


class FakeTavilyClient:
    def __init__(self, results: list[dict] | None = None, raise_error: bool = False, images: list | None = None) -> None:
        self._results = results or []
        self._raise_error = raise_error
        self._images = images or []
        self.queries: list[str] = []

    def search(self, query: str, max_results: int, include_raw_content: bool, include_images: bool) -> dict:
        self.queries.append(query)
        if self._raise_error:
            raise RuntimeError("simulated network failure")
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
                "content": "Short snippet about housing.",
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
    assert item.text == "Short snippet about housing."
    assert item.topic == "housing"
    assert item.metadata["provider"] == "tavily"
    assert tool.raw_content_cache[item.source_url] == "Much longer full page text about housing near Harvard Square."
    assert client.queries == ["Harvard Square housing"]


def test_page_retrieval_reads_from_shared_cache(harvard_square):
    client = FakeTavilyClient(
        results=[
            {
                "url": "https://example.org/a",
                "title": "A",
                "content": "snippet",
                "raw_content": "full text",
            }
        ]
    )
    search_tool = TavilyWebSearchTool(client=client)
    search_tool.search(harvard_square, _topic())
    retrieval_tool = TavilyPageRetrievalTool(search_tool.raw_content_cache)

    assert retrieval_tool.retrieve_full_text("https://example.org/a") == "full text"
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
        results=[{"url": "https://example.org/unrelated", "title": "Totally unrelated", "content": "Nothing to do with it."}]
    )
    tool = TavilyWebSearchTool(client=client)

    evidence = tool.search(harvard_square, _topic())

    assert len(evidence) == 1
    assert evidence[0].metadata.get("location_match") == "false"


def test_search_pairs_images_with_results_by_position(harvard_square):
    client = FakeTavilyClient(
        results=[
            {"url": "https://example.org/a", "title": "Harvard Square guide", "content": "About Harvard Square."},
            {"url": "https://example.org/b", "title": "Harvard Square news", "content": "More Harvard Square info."},
        ],
        images=["https://example.org/img-a.jpg", {"url": "https://example.org/img-b.jpg"}],
    )
    tool = TavilyWebSearchTool(client=client)

    evidence = tool.search(harvard_square, _topic())

    by_url = {e.source_url: e for e in evidence}
    assert by_url["https://example.org/a"].image_url == "https://example.org/img-a.jpg"
    assert by_url["https://example.org/b"].image_url == "https://example.org/img-b.jpg"
