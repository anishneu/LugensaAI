from datetime import datetime, timezone

from app.agents.location_research_agent import _site_of, _spread_across_sites
from app.models.evidence import Evidence, SourceType


def _item(url: str) -> Evidence:
    return Evidence(
        evidence_id=url, source_url=url, source_title="t", source_type=SourceType.OTHER, retrieved_at=datetime.now(timezone.utc),
        location_scope="x", text="text long enough to be evidence about this place", topic="community_sentiment",
    )


def test_subdomains_are_the_same_site_and_a_second_level_domain_is_kept_whole():
    assert _site_of("https://ca.trip.com/a") == _site_of("https://www.trip.com/b") == "trip.com"
    assert _site_of("https://www.bbc.co.uk/news") == "bbc.co.uk"
    assert _site_of("https://www.reddit.com/r/x") == "reddit.com"


def test_one_site_cannot_fill_every_place_when_others_are_available():
    items = [_item(f"https://www.trip.com/{i}") for i in range(3)] + [_item("https://www.reddit.com/r/x/comments/1/a")] + [_item("https://example.org/a")]

    kept = [i.source_url for i in _spread_across_sites(items, 4)]

    assert kept == ["https://www.trip.com/0", "https://www.trip.com/1", "https://www.reddit.com/r/x/comments/1/a", "https://example.org/a"]


def test_when_there_are_too_few_sites_the_places_are_still_filled():
    items = [_item(f"https://www.trip.com/{i}") for i in range(5)]

    assert [i.source_url for i in _spread_across_sites(items, 4)] == [f"https://www.trip.com/{i}" for i in range(4)]


def test_nothing_changes_when_every_source_is_from_a_different_site():
    items = [_item(f"https://site{i}.example/{i}") for i in range(6)]

    assert _spread_across_sites(items, 4) == items[:4]
