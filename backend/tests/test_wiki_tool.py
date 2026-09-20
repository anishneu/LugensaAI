import httpx
import pytest

from app.models.evidence import SourceType
from app.models.location import Location
from app.tools.base import ToolExecutionError
from app.tools.wiki_tool import WikiContextTool

_LOCATION = Location(
    name="Suiran",
    city="Kurume",
    region="Fukuoka",
    country="Japan",
    slug="suiran",
    latitude=33.3253,
    longitude=130.6153,
    raw_query="Suiran",
    is_business=True,
)
_GUIDE = (
    "Kurume (久留米) is a city in Fukuoka Prefecture.\n\n== Understand ==\nIt is known for ramen and rubber.\n\n"
    "== See ==\nThe Ishibashi Cultural Center and the Zendō-ji temple are popular with visitors. "
    "Many travellers come for the tonkotsu ramen, which was invented here in 1937."
)


def _handler(seen: list[httpx.Request] | None = None):
    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)
        params = dict(request.url.params)
        host = request.url.host
        if params.get("list") == "geosearch" and host == "en.wikipedia.org":
            return httpx.Response(200, json={"query": {"geosearch": [{"title": "Zendōji Station", "dist": 844.2}]}})
        if params.get("list") == "geosearch":
            return httpx.Response(200, json={"query": {"geosearch": [{"title": "Kurume", "dist": 9221.5}]}})
        if host == "en.wikipedia.org":
            page = {"pageid": 11, "title": "Zendōji Station", "fullurl": "https://en.wikipedia.org/wiki/Z", "extract": "A railway station."}
        else:
            page = {"pageid": 22, "title": "Kurume", "fullurl": "https://en.wikivoyage.org/wiki/Kurume", "extract": _GUIDE}
        return httpx.Response(200, json={"query": {"pages": {str(page["pageid"]): page}}})

    return handler


def _tool(handler=None) -> WikiContextTool:
    return WikiContextTool(transport=httpx.MockTransport(handler or _handler()))


def test_returns_nearby_wikipedia_article_and_the_town_travel_guide_as_attributed_reference_evidence():
    evidence = _tool().lookup(_LOCATION, "Is it a good location for a tourist?", "community_sentiment")

    station, guide = evidence
    assert station.source_type == guide.source_type == SourceType.REFERENCE
    assert "about 844 m from this location" in station.text
    assert station.publisher.startswith("Wikipedia") and guide.publisher.startswith("Wikivoyage")
    assert "CC BY-SA" in guide.publisher and guide.metadata["license"] == "CC BY-SA 4.0"
    assert guide.source_url == "https://en.wikivoyage.org/wiki/Kurume"
    assert all(e.published_at is None and e.topic == "community_sentiment" for e in evidence)


def test_guide_headings_become_plain_text_and_the_excerpt_follows_the_question():
    guide = _tool().lookup(_LOCATION, "Where should tourists eat ramen?", "food")[-1]

    assert "==" not in guide.text
    assert "ramen" in guide.text


def test_identifies_itself_with_contact_details_because_wikimedia_blocks_anonymous_clients():
    seen: list[httpx.Request] = []
    _tool(_handler(seen)).lookup(_LOCATION, "visit", "food")

    agents = {r.headers["User-Agent"] for r in seen}
    assert len(agents) == 1
    assert "https://" in agents.pop()


def test_no_coordinates_means_no_lookup():
    no_pin = _LOCATION.model_copy(update={"latitude": None, "longitude": None})

    assert _tool().lookup(no_pin, "visit", "food") == []


def test_a_wikimedia_failure_is_a_tool_error_not_a_crash():
    tool = WikiContextTool(transport=httpx.MockTransport(lambda r: httpx.Response(403, text="blocked")))

    with pytest.raises(ToolExecutionError):
        tool.lookup(_LOCATION, "visit", "food")
