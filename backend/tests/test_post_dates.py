"""Recovering the real publication date of a forum or social post. No test here touches the network."""

from datetime import datetime, timedelta, timezone

from app.models.evidence import Evidence, SourceType
from app.tools import post_dates
from app.tools.post_dates import (
    DATE_SOURCE,
    PostDateRecovery,
    date_from_html,
    date_from_reddit_feed,
    date_from_url,
    dates_from_archive,
    fetch_text,
    parse_date,
    reddit_feed_url,
)

_PTT = "https://www.ptt.cc/bbs/car/M.1762748907.A.922.html"
_REDDIT = "https://www.reddit.com/r/Taipei/comments/1fxbl4l/taipei_101_is_it_worth_visiting"

_REDDIT_FEED = """<?xml version="1.0"?><feed>
<updated>2026-09-20T04:57:46+00:00</updated>
<entry><id>t3_1fxbl4l</id><updated>2024-10-06T08:04:12+00:00</updated><title>Taipei 101: is it worth visiting</title></entry>
<entry><id>t1_abc123</id><updated>2024-10-07T10:00:00+00:00</updated><title>a reply</title></entry>
</feed>"""


def _item(url: str, published_at: datetime | None = None) -> Evidence:
    return Evidence(
        evidence_id=url,
        source_url=url,
        source_title="t",
        source_type=SourceType.COMMUNITY_FORUM,
        retrieved_at=datetime.now(timezone.utc),
        published_at=published_at,
        location_scope="Taipei",
        text="text",
        topic="live_feed",
    )


# ---- the URL


def test_a_ptt_article_is_dated_by_the_time_in_its_name():
    assert date_from_url(_PTT) == datetime(2025, 11, 10, 4, 28, 27, tzinfo=timezone.utc)


def test_a_date_in_the_path_is_read_but_a_bare_number_is_not():
    assert date_from_url("https://blog.example.com/2026/09/17/night-markets") == datetime(2026, 9, 17, tzinfo=timezone.utc)
    assert date_from_url("https://blog.example.com/2026-09-17-night-markets") == datetime(2026, 9, 17, tzinfo=timezone.utc)
    assert date_from_url("https://www.dcard.tw/f/travel/p/256921269") is None
    assert date_from_url("https://example.com/post/20260917") is None, "an 8-digit run is as likely an id as a date"


def test_an_impossible_or_future_date_in_a_url_is_rejected():
    assert date_from_url("https://example.com/2026/13/40/x") is None
    future = (datetime.now(timezone.utc) + timedelta(days=400)).strftime("%Y/%m/%d")
    assert date_from_url(f"https://example.com/{future}/x") is None


def test_parse_date_reads_zulu_offsets_and_rfc2822_and_rejects_nonsense():
    assert parse_date("2025-11-10T04:28:27Z") == datetime(2025, 11, 10, 4, 28, 27, tzinfo=timezone.utc)
    assert parse_date("2025-11-10T12:28:27+08:00") == datetime(2025, 11, 10, 4, 28, 27, tzinfo=timezone.utc)
    assert parse_date("Mon, 10 Nov 2025 04:28:27 GMT") == datetime(2025, 11, 10, 4, 28, 27, tzinfo=timezone.utc)
    assert parse_date("1970-01-01") is None and parse_date("soon") is None and parse_date(None) is None


# ---- Reddit


def test_reddit_thread_urls_map_to_their_atom_feed():
    assert reddit_feed_url(_REDDIT) == "https://www.reddit.com/r/Taipei/comments/1fxbl4l/_/.rss"
    assert reddit_feed_url("https://www.reddit.com/r/Taipei/") is None


def test_the_archive_response_gives_a_date_per_post_id_and_ignores_garbage():
    body = '{"data": [{"id": "1fxbl4l", "created_utc": 1728201852}, {"id": "bad", "created_utc": "x"}, {"created_utc": 5}, {"id": "old", "created_utc": 0}]}'

    assert dates_from_archive(body) == {"1fxbl4l": datetime(2024, 10, 6, 8, 4, 12, tzinfo=timezone.utc)}
    assert dates_from_archive("not json") == {} and dates_from_archive('{"data": 5}') == {}


def test_the_reddit_date_is_the_posts_own_entry_not_the_feed_or_a_reply():
    assert date_from_reddit_feed(_REDDIT_FEED, "1fxbl4l") == datetime(2024, 10, 6, 8, 4, 12, tzinfo=timezone.utc)
    assert date_from_reddit_feed(_REDDIT_FEED, "zzzzzzz") is None


# ---- page metadata


def test_json_ld_and_meta_dates_are_read_and_modified_dates_are_not():
    ld = '<script type="application/ld+json">{"@graph":[{"@type":"WebSite"},{"@type":"Article","datePublished":"2026-03-02T09:00:00+00:00","dateModified":"2026-09-01T00:00:00+00:00"}]}</script>'
    assert date_from_html(f"<html><head>{ld}</head></html>") == datetime(2026, 3, 2, 9, tzinfo=timezone.utc)

    meta = '<meta property="article:published_time" content="2025-07-04T10:00:00Z"><meta property="article:modified_time" content="2026-01-01T00:00:00Z">'
    assert date_from_html(f"<html><head>{meta}</head></html>") == datetime(2025, 7, 4, 10, tzinfo=timezone.utc)

    only_modified = '<meta property="article:modified_time" content="2026-01-01T00:00:00Z">'
    assert date_from_html(f"<html><head>{only_modified}</head></html>") is None


def test_a_bare_time_tag_is_not_trusted_but_a_microdata_published_time_is():
    assert date_from_html('<p>Reply <time datetime="2026-01-01T00:00:00Z">yesterday</time></p>') is None
    assert date_from_html('<time itemprop="datePublished" datetime="2026-01-01T00:00:00Z">1 Jan</time>') == datetime(2026, 1, 1, tzinfo=timezone.utc)


def test_broken_markup_and_broken_json_ld_do_not_raise():
    assert date_from_html('<script type="application/ld+json">{not json</script><meta') is None
    assert date_from_html("") is None


# ---- the recovery step


class _Pages:
    def __init__(self, pages: dict[str, str | None]) -> None:
        self.pages, self.calls = pages, []

    def __call__(self, url: str) -> str | None:
        self.calls.append(url)
        return self.pages.get(url)


def test_url_dates_cost_no_request_and_say_where_they_came_from():
    pages = _Pages({})
    ptt = _item(_PTT)

    PostDateRecovery(pages).enrich([ptt])

    assert ptt.published_at == datetime(2025, 11, 10, 4, 28, 27, tzinfo=timezone.utc)
    assert ptt.metadata[DATE_SOURCE] == "url" and pages.calls == []


def test_reddit_is_dated_from_its_feed_and_other_pages_from_their_metadata():
    pages = _Pages(
        {
            "https://www.reddit.com/r/Taipei/comments/1fxbl4l/_/.rss": _REDDIT_FEED,
            "https://blog.example.com/p/1": '<meta property="article:published_time" content="2025-07-04T10:00:00Z">',
        }
    )
    reddit, blog = _item(_REDDIT), _item("https://blog.example.com/p/1")

    PostDateRecovery(pages).enrich([reddit, blog])

    assert reddit.published_at == datetime(2024, 10, 6, 8, 4, 12, tzinfo=timezone.utc)
    assert reddit.metadata[DATE_SOURCE] == "reddit_feed"
    assert blog.metadata[DATE_SOURCE] == "page_metadata"


def test_an_existing_date_is_never_overwritten_or_refetched():
    known = datetime(2020, 1, 1, tzinfo=timezone.utc)
    pages = _Pages({})
    item = _item(_REDDIT, published_at=known)

    PostDateRecovery(pages).enrich([item])

    assert item.published_at == known and pages.calls == [] and DATE_SOURCE not in item.metadata


def test_a_page_that_cannot_be_read_stays_undated_and_costs_the_others_nothing():
    class Exploding(_Pages):
        def __call__(self, url):
            if "bad" in url:
                raise RuntimeError("boom")
            return super().__call__(url)

    good = "https://blog.example.com/p/1"
    pages = Exploding({good: '<meta property="article:published_time" content="2025-07-04T10:00:00Z">'})
    bad, ok, missing = _item("https://bad.example.com/p"), _item(good), _item("https://gone.example.com/p")

    PostDateRecovery(pages).enrich([bad, ok, missing])

    assert bad.published_at is None and missing.published_at is None and ok.published_at is not None


def test_login_walled_hosts_are_not_requested_and_the_number_of_requests_is_capped():
    pages = _Pages({})
    items = [_item("https://www.dcard.tw/f/travel/p/1"), _item("https://www.instagram.com/p/x")] + [
        _item(f"https://forum.example.com/t/{n}") for n in range(20)
    ]

    PostDateRecovery(pages, max_fetches=5).enrich(items)

    assert len(pages.calls) == 5
    assert not any("dcard" in c or "instagram" in c for c in pages.calls)


def test_with_fetching_disabled_only_url_dates_are_used(monkeypatch):
    monkeypatch.setenv("DISABLE_POST_DATE_FETCH", "1")
    reddit, ptt = _item(_REDDIT), _item(_PTT)

    PostDateRecovery().enrich([reddit, ptt])

    assert reddit.published_at is None and ptt.published_at is not None


# ---- the fetcher refuses to be a way into the local network


def test_the_fetcher_never_connects_to_a_private_or_local_address(monkeypatch):
    def no_network(*args, **kwargs):  # pragma: no cover - reaching this is the failure
        raise AssertionError("a request was attempted")

    monkeypatch.setattr(post_dates.urllib.request.OpenerDirector, "open", no_network)

    for url in ("http://127.0.0.1:8000/api", "http://localhost/x", "http://169.254.169.254/latest", "http://10.0.0.5/a", "file:///etc/passwd", "ftp://example.com/x"):
        assert fetch_text(url) is None


_ARCHIVE = "https://arctic-shift.photon-reddit.com/api/posts/ids?fields=id,created_utc&ids="


def test_every_reddit_thread_is_dated_from_one_archive_request():
    ids = ["1fxbl4l", "1c96yvb", "1ih9h90"]
    pages = _Pages({_ARCHIVE + ",".join(ids): '{"data": [{"id": "1fxbl4l", "created_utc": 1728201852}, {"id": "1c96yvb", "created_utc": 1713700000}, {"id": "1ih9h90", "created_utc": 1738700000}]}'})
    items = [_item(f"https://www.reddit.com/r/Taipei/comments/{i}/slug") for i in ids]

    PostDateRecovery(pages).enrich(items)

    assert [i.metadata[DATE_SOURCE] for i in items] == ["reddit_archive"] * 3
    assert items[0].published_at == datetime(2024, 10, 6, 8, 4, 12, tzinfo=timezone.utc)
    assert len(pages.calls) == 1, "Reddit itself is throttled, so it is not asked when the archive answered"


def test_reddit_is_asked_only_for_the_posts_the_archive_lacks_and_only_a_couple():
    ids = ["aaaaaa1", "aaaaaa2", "aaaaaa3", "aaaaaa4"]
    pages = _Pages({_ARCHIVE + ",".join(ids): '{"data": []}'})
    items = [_item(f"https://www.reddit.com/r/Taipei/comments/{i}/slug") for i in ids]

    PostDateRecovery(pages).enrich(items)

    feed_calls = [c for c in pages.calls if c.endswith(".rss")]
    assert len(feed_calls) == 2 and all(i.published_at is None for i in items)


def test_an_archive_outage_leaves_reddit_posts_undated_without_raising():
    class Down(_Pages):
        def __call__(self, url):
            raise ConnectionError("archive down")

    item = _item(_REDDIT)

    PostDateRecovery(Down({})).enrich([item])

    assert item.published_at is None
