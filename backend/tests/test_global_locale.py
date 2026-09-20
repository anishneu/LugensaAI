"""Working outside English-speaking countries: local-language search, native names, global sources."""

import json

import pytest

from app.agents.factory import build_default_agent
from app.models.evidence import SourceType
from app.models.location import Location
from app.models.plan import Priority, ResearchPlan, ResearchTopic
from app.models.trace import TraceStage
from app.planning.local_queries import LLMLocalQueryWriter, RuleBasedLocalQueryWriter
from app.tools.base import ToolExecutionError
from app.tools.locale import PRIMARY_LANGUAGE, LocaleResolver, LocalContext
from app.tools.tavily_tools import TavilyWebSearchTool, _classify_source_type
from tests.llm_doubles import ScriptedLLMService
from tests.test_tavily_tools import FakeTavilyClient


def _place(**overrides) -> Location:
    base = dict(
        name="Suiran", city="Kurume", region="Fukuoka", country="Japan", slug="suiran", latitude=33.3253,
        longitude=130.6153, raw_query="Suiran", is_business=True, language="ja", local_name="翠藍", local_area="久留米市",
    )
    return Location(**{**base, **overrides})


def _topic(topic_id: str = "community_sentiment", **kw) -> ResearchTopic:
    return ResearchTopic(
        topic_id=topic_id, reason="r", search_queries=[f"{topic_id} english query"], expected_evidence="what people say",
        priority=Priority.HIGH, completion_criteria="c", **kw,
    )


def _plan(*topics: ResearchTopic) -> ResearchPlan:
    return ResearchPlan(question="How are the reviews?", topics=list(topics))


# ------------------------------------------------------------------ locale resolution


class _FakeNominatim:
    def __init__(self, english: dict, local: dict | None = None, fail: bool = False) -> None:
        self._english, self._local, self._fail = english, local or {}, fail
        self.calls: list[str] = []

    def reverse(self, lat, lon, language="en", zoom=14):
        self.calls.append(language)
        if self._fail:
            raise ToolExecutionError("nominatim down")
        return {"address": self._english if language == "en" else self._local}


class _FakeGoogle:
    def __init__(self, name: str | None = "翠藍") -> None:
        self._name = name
        self.asked: list[str] = []

    def local_name(self, name, lat, lon, language):
        self.asked.append(language)
        return self._name


_KURUME_EN = {"city": "Kurume", "country_code": "jp"}
_KURUME_JA = {"city": "久留米市", "country_code": "jp"}


def _fresh(**kw) -> Location:
    # A distinct coordinate per test, since resolved locales are cached by position.
    _fresh.n += 1
    return _place(latitude=30.0 + _fresh.n / 1000, **kw)


_fresh.n = 0


def test_a_business_in_japan_gets_the_language_the_city_name_and_google_s_native_business_name():
    google = _FakeGoogle("翠藍")

    context = LocaleResolver(_FakeNominatim(_KURUME_EN, _KURUME_JA), google).resolve(_fresh())  # type: ignore[arg-type]

    assert context == LocalContext(country_code="jp", language="ja", local_name="翠藍", local_area="久留米市")
    assert google.asked == ["ja"]


def test_an_area_takes_its_native_name_from_the_matching_address_component():
    english = {"suburb": "Shibuya", "city": "Tokyo", "country_code": "jp"}
    local = {"suburb": "渋谷", "city": "東京都", "country_code": "jp"}

    context = LocaleResolver(_FakeNominatim(english, local)).resolve(  # type: ignore[arg-type]
        _fresh(name="Shibuya", city="Tokyo", is_business=False)
    )

    assert (context.local_name, context.local_area) == ("渋谷", "東京都")


def test_english_speaking_countries_need_no_local_search():
    english = {"city": "Sydney", "country_code": "au"}
    nominatim = _FakeNominatim(english)

    context = LocaleResolver(nominatim).resolve(_fresh(city="Sydney"))  # type: ignore[arg-type]

    assert context == LocalContext(country_code="au")
    assert nominatim.calls == ["en"], "no second, local-language lookup is needed"


def test_a_name_that_is_the_same_in_both_languages_is_not_repeated():
    english = {"city": "Paris", "country_code": "fr"}
    local = {"city": "Paris", "country_code": "fr"}

    context = LocaleResolver(_FakeNominatim(english, local)).resolve(_fresh(name="Cafe X", city="Paris", is_business=False))  # type: ignore[arg-type]

    assert context.language == "fr" and context.local_area is None


def test_a_business_without_google_still_gets_the_city_and_language():
    context = LocaleResolver(_FakeNominatim(_KURUME_EN, _KURUME_JA), google=None).resolve(_fresh())  # type: ignore[arg-type]

    assert (context.language, context.local_name, context.local_area) == ("ja", None, "久留米市")


def test_every_mapped_language_is_one_the_free_translator_can_read():
    """A language with no Argos pack would be searched for pages that could never be read."""
    supported = set(
        "ar az bg bn ca cs da de el eo es et eu fa fi fr ga gl he hi hu id it ja ko ky lt lv ms nb nl pl pt ro ru "
        "sk sl sq sv sw th tl tr uk ur vi zh zt".split()
    )
    assert set(PRIMARY_LANGUAGE.values()) <= supported
    assert "US" not in PRIMARY_LANGUAGE and "GB" not in PRIMARY_LANGUAGE and "IN" not in PRIMARY_LANGUAGE


# ------------------------------------------------------------------ local queries


def test_rule_based_writer_uses_the_native_name_and_city_for_one_topic_only():
    plan = _plan(_topic("food"), _topic("safety"))

    assert RuleBasedLocalQueryWriter().write(_place(), plan) == {"food": "翠藍 久留米市"}


def test_rule_based_writer_has_nothing_to_write_without_native_names():
    assert RuleBasedLocalQueryWriter().write(_place(local_name=None, local_area=None), _plan(_topic())) == {}


def _llm_writer(reply: str | dict) -> LLMLocalQueryWriter:
    return LLMLocalQueryWriter(ScriptedLLMService([reply if isinstance(reply, str) else json.dumps(reply)]))


def test_llm_writer_writes_a_query_per_topic_in_the_local_language():
    plan = _plan(_topic("community_sentiment"), _topic("food"))

    queries = _llm_writer({"queries": {"community_sentiment": "翠藍 久留米 口コミ 評判", "food": "翠藍 久留米 メニュー"}}).write(_place(), plan)

    assert queries == {"community_sentiment": "翠藍 久留米 口コミ 評判", "food": "翠藍 久留米 メニュー"}


def test_llm_writer_discards_a_query_that_leaves_out_the_place():
    plan = _plan(_topic("community_sentiment"), _topic("food"))

    queries = _llm_writer({"queries": {"community_sentiment": "口コミ 評判", "food": "翠藍 メニュー", "invented": "翠藍 x"}}).write(_place(), plan)

    assert queries == {"food": "翠藍 メニュー"}


@pytest.mark.parametrize("reply", ["not json", '{"queries": "nope"}', '{"queries": {"community_sentiment": "no place here"}}'])
def test_llm_writer_falls_back_to_the_rule_based_query_on_failure_or_garbage(reply):
    assert _llm_writer(reply).write(_place(), _plan(_topic())) == {"community_sentiment": "翠藍 久留米市"}


def test_llm_writer_falls_back_when_the_model_errors():
    writer = LLMLocalQueryWriter(ScriptedLLMService(raise_error=True))

    assert writer.write(_place(), _plan(_topic())) == {"community_sentiment": "翠藍 久留米市"}


# ------------------------------------------------------------------ searching and matching


def _result(url: str, title: str, content: str) -> dict:
    return {"url": url, "title": title, "content": content, "raw_content": None}


_JA_PAGE = _result("https://tabelog.com/a/b/40021234/", "翠藍 久留米 口コミ", "久留米市善導寺町の海鮮料理店、翠藍。新鮮な海鮮丼が人気です。")
_EN_WRONG_HOTEL = _result("https://kayak.com/suiran-kyoto", "Suiran Kyoto hotel", "Suiran, a Luxury Collection Hotel in Kyoto. Reviews.")


def test_the_search_runs_the_local_language_query_too_and_merges_without_duplicates():
    client = FakeTavilyClient(results_sequence=[[_EN_WRONG_HOTEL], [_JA_PAGE, _EN_WRONG_HOTEL]])
    topic = _topic(local_queries=["翠藍 久留米 口コミ"])

    TavilyWebSearchTool(client=client).search(_place(), topic)

    assert client.queries == ["community_sentiment english query", "翠藍 久留米 口コミ"]


def test_a_page_about_the_business_is_accepted_by_its_native_name_and_city_even_untranslated():
    client = FakeTavilyClient(results=[_JA_PAGE])

    found = TavilyWebSearchTool(client=client).search(_place(), _topic(local_queries=["翠藍 久留米"]))

    assert [e.source_url for e in found] == ["https://tabelog.com/a/b/40021234/"]


def test_without_native_names_the_same_japanese_page_is_rejected():
    """The English name and city appear nowhere in it, so nothing ties it to this business."""
    client = FakeTavilyClient(results=[_JA_PAGE])

    found = TavilyWebSearchTool(client=client).search(_place(local_name=None, local_area=None), _topic())

    assert found == []


def test_a_same_named_business_elsewhere_is_still_rejected_with_native_names_in_play():
    client = FakeTavilyClient(results=[_EN_WRONG_HOTEL])

    assert TavilyWebSearchTool(client=client).search(_place(), _topic(local_queries=["翠藍 久留米"])) == []


def test_one_query_failing_does_not_lose_the_others_but_all_failing_is_an_error():
    class _FailsOnLocal(FakeTavilyClient):
        def search(self, query, **kw):
            if "口コミ" in query:
                raise RuntimeError("boom")
            return super().search(query, **kw)

    ok = _FailsOnLocal(results=[_JA_PAGE])
    assert TavilyWebSearchTool(client=ok).search(_place(), _topic(local_queries=["翠藍 口コミ"]))

    with pytest.raises(ToolExecutionError):
        TavilyWebSearchTool(client=FakeTavilyClient(raise_error=True)).search(_place(), _topic(local_queries=["x"]))


# ------------------------------------------------------------------ official sources worldwide


@pytest.mark.parametrize(
    "url",
    [
        "https://www.city.kurume.lg.jp/kurashi/", "https://www.moj.go.jp/x", "https://www.gov.uk/foreign-travel-advice/japan",
        "https://www.diplomatie.gouv.fr/fr/conseils", "https://www.gob.mx/sre", "https://www.seoul.go.kr/main",
        "https://www.gov.br/pt-br", "https://www.nic.in/x", "https://www.abs.gov.au/x", "https://travel.gc.ca/egypt",
        "https://ec.europa.eu/x", "https://www.osac.gov/Country",
    ],
)
def test_government_sites_are_recognised_in_every_country_not_just_dot_gov(url):
    assert _classify_source_type(url) == SourceType.LOCAL_GOVERNMENT


@pytest.mark.parametrize("url", ["https://www.ox.ac.uk/x", "https://www.u-tokyo.ac.jp/en", "https://www.unsw.edu.au/x", "https://www.mit.edu/"])
def test_universities_are_recognised_in_every_country(url):
    assert _classify_source_type(url) == SourceType.ACADEMIC


@pytest.mark.parametrize("url", ["https://tabelog.com/fukuoka/x", "https://retty.me/area/x", "https://www.booking.com/hotel/x"])
def test_review_sites_outside_the_us_are_recognised(url):
    assert _classify_source_type(url) == SourceType.REVIEW_AGGREGATOR


def test_a_dot_com_that_merely_contains_go_is_not_government():
    assert _classify_source_type("https://www.go.com/x") == SourceType.OTHER
    assert _classify_source_type("https://www.gov-jobs.com/x") == SourceType.OTHER


# ------------------------------------------------------------------ the agent


class _Resolver:
    def __init__(self, context: LocalContext | None = None, fail: bool = False) -> None:
        self._context, self._fail = context, fail

    def resolve(self, location):
        if self._fail:
            raise ToolExecutionError("reverse geocoding is down")
        return self._context


def _agent(context: LocalContext | None = None, fail: bool = False, writer=None):
    agent = build_default_agent()
    agent.locale_resolver = _Resolver(context, fail)  # type: ignore[assignment]
    agent.local_query_writer = writer or RuleBasedLocalQueryWriter()
    return agent


_LOCATION = Location(
    name="Harvard Square", city="Cambridge", region="MA", country="US", slug="harvard-square", latitude=42.37,
    longitude=-71.12, raw_query="Harvard Square, Cambridge, MA",
)


def test_the_agent_records_the_local_language_plan_in_the_trace_and_on_the_topics():
    seen = {}

    class _SpySearch:
        def search(self, location, topic):
            seen["location"], seen["topic"] = location, topic
            return []

    agent = _agent(LocalContext("jp", "ja", "ハーバード広場", "ケンブリッジ"))
    agent.web_search_tool = _SpySearch()  # type: ignore[assignment]

    response = agent.run(_LOCATION, "What is the nightlife like?")

    assert seen["location"].language == "ja" and seen["location"].local_name == "ハーバード広場"
    assert seen["topic"].local_queries == ["ハーバード広場 ケンブリッジ"]
    step = next(s for s in response.research_trace if "local language" in s.description)
    assert step.stage == TraceStage.RESEARCH_PLANNING and "ハーバード広場" in step.details["queries"]


def test_english_speaking_places_skip_the_local_search():
    response = _agent(LocalContext("us")).run(_LOCATION, "What is the nightlife like?")

    assert any("English is the working language" in s.description for s in response.research_trace)


def test_a_failed_locale_lookup_is_a_limitation_and_the_run_still_completes():
    response = _agent(fail=True).run(_LOCATION, "What is the nightlife like?")

    assert any("reverse geocoding is down" in lim for lim in response.limitations)
    assert response.summary


def test_a_language_with_no_buildable_query_says_so():
    response = _agent(LocalContext("jp", "ja", None, None)).run(_LOCATION, "What is the nightlife like?")

    assert any("no local-language query could be built" in lim for lim in response.limitations)


def test_a_page_that_does_not_mention_the_place_is_not_translated_when_native_names_are_known():
    """Translation costs CPU seconds per snippet, so pages about something else must not be paid for."""
    from app.tools.translation import Translator

    class _Spy(Translator):
        def __init__(self) -> None:
            self.translated: list[str] = []

        def detect(self, text):
            return "ja"

        def translate_to_english(self, text, source_language):
            self.translated.append(text)
            return "translated text"

    unrelated = _result("https://news.example.jp/1/", "全国のニュース", "東京の天気は晴れです。全国的に穏やかな一日でした。")
    spy = _Spy()
    client = FakeTavilyClient(results=[unrelated, _JA_PAGE])

    TavilyWebSearchTool(client=client, translator=spy).search(_place(), _topic(local_queries=["翠藍"]))

    assert all("翠藍" in text or "久留米" in text for text in spy.translated), spy.translated
    assert not any("天気" in text for text in spy.translated)
