"""Forums, Reddit, Quora, social media and regional communities: what people say about a place."""

from datetime import datetime, timezone

import pytest

from app.agents.factory import build_default_agent
from app.models.evidence import Evidence, SourceType
from app.models.location import Location
from app.models.trace import TraceStage
from app.tools.base import ToolExecutionError, WebSearchTool
from app.tools.community_sources import (
    GLOBAL_COMMUNITY_DOMAINS,
    REGIONAL_COMMUNITY_DOMAINS,
    community_domains,
    community_query,
    feed_domains,
    is_community_domain,
    native_query,
    regional_domains,
)
from app.tools.tavily_tools import TavilyWebSearchTool, _classify_source_type
from tests.test_tavily_tools import FakeTavilyClient, _topic


def _place(**kw) -> Location:
    base = dict(
        name="Zhongshan", city="Taipei", region="Taiwan", country="Taiwan", slug="z", latitude=25.05, longitude=121.52,
        raw_query="Zhongshan, Taipei", country_code="tw",
    )
    return Location(**{**base, **kw})


def test_a_taiwan_place_searches_taiwanese_forums_before_the_global_ones():
    domains = community_domains("tw")

    assert domains[:5] == ["ptt.cc", "dcard.tw", "mobile01.com", "pixnet.net", "ipeen.com.tw"]
    assert "reddit.com" in domains and "quora.com" in domains


def test_an_unknown_or_missing_country_still_gets_the_global_communities():
    assert community_domains(None) == list(GLOBAL_COMMUNITY_DOMAINS)
    assert community_domains("zz") == list(GLOBAL_COMMUNITY_DOMAINS)
    assert community_domains("TW")[0] == "ptt.cc"  # case-insensitive


def test_no_domain_is_listed_twice_and_every_country_code_is_lowercase_alpha2():
    for code, domains in REGIONAL_COMMUNITY_DOMAINS.items():
        assert len(code) == 2 and code == code.lower()
        assert len(set(domains)) == len(domains)
    assert len(set(community_domains("tw"))) == len(community_domains("tw"))


@pytest.mark.parametrize(
    "url",
    [
        "https://www.ptt.cc/bbs/Taiwan/M.1.html",
        "https://www.dcard.tw/f/travel/p/1",
        "https://pantip.com/topic/1",
        "https://www.reddit.com/r/taiwan/comments/x",
        "https://www.quora.com/What-is",
        "https://blog.naver.com/x/1",
        "https://otzovik.com/review_1.html",
    ],
)
def test_forums_and_social_sites_are_classified_as_community_sources(url):
    assert _classify_source_type(url) == SourceType.COMMUNITY_FORUM


def test_review_sites_on_the_list_stay_review_sites():
    assert _classify_source_type("https://tabelog.com/fukuoka/x") == SourceType.REVIEW_AGGREGATOR
    assert _classify_source_type("https://www.yelp.com/biz/x") == SourceType.REVIEW_AGGREGATOR


def test_is_community_domain_matches_subdomains_but_not_lookalikes():
    assert is_community_domain("old.reddit.com") and is_community_domain("www.ptt.cc")
    assert not is_community_domain("notreddit.com") and not is_community_domain("example.com")


def test_a_business_is_searched_by_name_and_an_area_by_the_question():
    cafe = _place(name="Cafe Pustekuchen", city="Barchfeld", is_business=True)

    assert community_query(cafe, "how is the coffee?") == '"Cafe Pustekuchen" Barchfeld reviews opinions experience'
    assert community_query(_place(), "is it safe at night?") == "Zhongshan Taipei is it safe at night?"
    assert community_query(_place(), "  ").endswith("what is it like")


def test_the_search_is_restricted_to_the_community_domains_when_asked_to():
    client = FakeTavilyClient(results=[])
    tool = TavilyWebSearchTool(client=client, include_domains_for=lambda place: community_domains(place.country_code))

    tool.search(_place(), _topic("community_sentiment"))

    assert client.domains and client.domains[0][0] == "ptt.cc"


def test_a_normal_search_is_not_restricted_to_any_domain():
    client = FakeTavilyClient(results=[])

    TavilyWebSearchTool(client=client).search(_place(), _topic("housing"))

    assert client.domains == [None]


# ------------------------------------------------------------------ the agent


class _CommunitySearch(WebSearchTool):
    def __init__(self, fail: bool = False) -> None:
        self.calls: list[tuple[str, str]] = []
        self._fail = fail

    def search(self, location, topic):
        self.calls.append((topic.topic_id, topic.search_queries[0]))
        if self._fail:
            raise ToolExecutionError("tavily down")
        return [
            Evidence(
                evidence_id="community:1",
                source_url="https://www.reddit.com/r/taiwan/comments/1",
                source_title="Living near Zhongshan?",
                publisher="reddit.com",
                source_type=SourceType.COMMUNITY_FORUM,
                retrieved_at=datetime.now(timezone.utc),
                location_scope="Taipei",
                text="Zhongshan Taipei is walkable and safe at night, lots of cafes and a quiet residential feel.",
                topic=topic.topic_id,
            )
        ]


def _agent(community):
    agent = build_default_agent()
    agent.community_search_tool = community
    return agent


def test_the_agent_searches_forums_and_keeps_the_undated_posts_it_finds():
    community = _CommunitySearch()

    response = _agent(community).run(_place(), "Is it safe and walkable at night?")

    assert community.calls and "safe and walkable" in community.calls[0][1]
    forum = [e for e in response.evidence if e.source_type == SourceType.COMMUNITY_FORUM]
    assert forum and forum[0].published_at is None, "an undated forum post is kept, and stays undated"
    step = next(s for s in response.research_trace if "community search" in s.description)
    assert step.stage == TraceStage.TOOL_SELECTION and "ptt.cc" in step.details["domains"]


def test_a_failed_community_search_is_a_limitation_not_a_crash():
    response = _agent(_CommunitySearch(fail=True)).run(_place(), "Is it safe?")

    assert any("Community search failed" in lim and "tavily down" in lim for lim in response.limitations)
    assert response.summary


def test_without_a_community_tool_nothing_extra_runs():
    agent = build_default_agent()
    agent.community_search_tool = None

    assert not any("community search" in s.description for s in agent.run(_place(), "Is it safe?").research_trace)


# ------------------------------------------------------------------ English first


class _MixedLanguageSearch(WebSearchTool):
    """Three relevant sources: one English, two machine-translated from Japanese."""

    def search(self, location, topic):
        def item(n: int, lang: str | None) -> Evidence:
            return Evidence(
                evidence_id=f"m{n}",
                source_url=f"https://example.org/{n}",
                source_title=f"Zhongshan guide {n}",
                source_type=SourceType.BLOG,
                retrieved_at=datetime.now(timezone.utc),
                location_scope="Taipei",
                text="Zhongshan Taipei safe walkable cafes quiet residential guide",
                topic=topic.topic_id,
                metadata={"language": lang} if lang else {},
            )

        return [item(1, "ja"), item(2, "ja"), item(3, None)]


def test_english_sources_come_first_and_translated_ones_only_fill_the_remaining_places():
    agent = build_default_agent()
    agent.web_search_tool = _MixedLanguageSearch()
    agent.config = agent.config.model_copy(update={"max_evidence_per_topic": 2})

    response = agent.run(_place(), "Is it safe and walkable?")

    kept = [e.evidence_id for e in response.evidence]
    assert "m3" in kept, "the English source is always kept when other-language ones compete for the places"
    assert len(kept) == 2 and sum(1 for e in response.evidence if e.metadata.get("language") == "ja") == 1


# ------------------------------------------------------------------ separate searches, so no source is crowded out


def test_the_feed_searches_reddit_and_the_countrys_forums_and_not_listings_or_video():
    assert feed_domains("tw") == ["ptt.cc", "dcard.tw", "mobile01.com", "pixnet.net", "ipeen.com.tw", "reddit.com"]
    assert feed_domains(None) == ["reddit.com"]
    assert not {"tripadvisor.com", "youtube.com", "facebook.com"} & set(feed_domains("tw"))


def test_regional_forums_can_be_left_out_of_the_english_search_because_they_are_searched_separately():
    assert regional_domains("tw")[0] == "ptt.cc" and regional_domains("zz") == []
    assert "ptt.cc" not in community_domains("tw", include_regional=False)
    assert "reddit.com" in community_domains("tw", include_regional=False)


def test_the_native_query_is_the_places_own_name_in_its_own_script():
    assert native_query(_place(local_name="台北101", local_area="信義區")) == "台北101 信義區"
    assert native_query(_place(local_area="信義區")) == "信義區"
    assert native_query(_place()) == ""


class _Recorder(WebSearchTool):
    def __init__(self) -> None:
        self.queries: list[str] = []

    def search(self, location, topic):
        self.queries.append(topic.search_queries[0])
        return []


def _agent_with(community, regional):
    agent = build_default_agent()
    agent.community_search_tool = community
    agent.regional_search_tool = regional
    return agent


def test_a_place_with_a_native_name_also_gets_a_local_language_search_of_the_countrys_forums():
    community, regional = _Recorder(), _Recorder()

    response = _agent_with(community, regional).run(_place(local_name="台北101", local_area="信義區"), "Is it safe?")

    assert regional.queries == ["台北101 信義區"]
    assert len(community.queries) == 1 and "safe" in community.queries[0]
    step = next(s for s in response.research_trace if "regional forum search" in s.description)
    assert "ptt.cc" in step.details["domains"]
    english = next(s for s in response.research_trace if "community search" in s.description)
    assert "ptt.cc" not in english.details["domains"], "the forums are searched once, in their own language"


def test_without_a_native_name_the_countrys_forums_ride_in_the_english_search_instead():
    community, regional = _Recorder(), _Recorder()

    response = _agent_with(community, regional).run(_place(), "Is it safe?")

    assert regional.queries == []
    english = next(s for s in response.research_trace if "community search" in s.description)
    assert "ptt.cc" in english.details["domains"]


def test_a_country_with_no_listed_forums_gets_no_regional_search():
    community, regional = _Recorder(), _Recorder()

    _agent_with(community, regional).run(_place(country_code="zz", local_name="台北101"), "Is it safe?")

    assert regional.queries == []


def test_a_failed_regional_search_is_a_limitation_not_a_crash():
    class Down(_Recorder):
        def search(self, location, topic):
            raise ToolExecutionError("tavily down")

    response = _agent_with(_Recorder(), Down()).run(_place(local_name="台北101"), "Is it safe?")

    assert any("Regional forum search failed" in lim for lim in response.limitations)
    assert response.summary


# ------------------------------------------------------------------ dates on posts


def test_a_forum_post_that_passes_every_filter_gets_its_real_date():
    from app.tools.post_dates import PostDateRecovery

    reddit = "https://www.reddit.com/r/Taipei/comments/1fxbl4l/zhongshan_taipei_is_walkable"
    feed = (
        '<feed><entry><id>t3_1fxbl4l</id><updated>2024-10-06T08:04:12+00:00</updated></entry></feed>'
    )
    fetched: list[str] = []

    def fetch(url: str) -> str | None:
        fetched.append(url)
        return feed

    client = FakeTavilyClient(
        results=[
            {"url": reddit, "title": "Zhongshan, Taipei is walkable", "content": "Zhongshan Taipei Taiwan is walkable and safe at night, lots of cafes."},
            {"url": "https://www.reddit.com/r/Taipei/comments/zzz9999/other_city", "title": "Other", "content": "Nothing here about the place asked about, only Kaohsiung and its harbour."},
        ]
    )
    tool = TavilyWebSearchTool(client=client, date_recovery=PostDateRecovery(fetch))

    found = tool.search(_place(), _topic("community_sentiment"))

    dated = [e for e in found if e.source_url == reddit]
    assert dated and dated[0].published_at == datetime(2024, 10, 6, 8, 4, 12, tzinfo=timezone.utc)
    assert dated[0].metadata["date_source"] == "reddit_feed"
    assert all("zzz9999" not in url for url in fetched), "a post that was filtered out is never fetched"
