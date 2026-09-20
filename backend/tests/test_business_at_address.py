"""A street address usually means the business standing at it."""

from app.agents.factory import build_default_agent
from app.models.location import Location
from app.models.place import PlaceCandidate
from app.models.trace import TraceStage
from app.tools.base import ToolExecutionError


def _address(**overrides) -> Location:
    base = dict(
        name="Unterer Graben 11", city="Barchfeld-Immelborn", region="Thuringia", country="Germany", slug="ug11",
        latitude=50.8005744, longitude=10.3000295, raw_query="Unterer Graben 11, Barchfeld-Immelborn",
        is_address=True,
    )
    return Location(**{**base, **overrides})


def _venue(name: str = "Café Pustekuchen") -> PlaceCandidate:
    return PlaceCandidate(
        name=name, display_name=name, category="Cafe", city="Barchfeld-Immelborn", region="Thuringia",
        country="Germany", latitude=50.80061, longitude=10.30015, is_business=True,
    )


class _FakeGoogle:
    def __init__(self, venues=None, fail: bool = False) -> None:
        self._venues, self._fail = venues or [], fail
        self.venue_calls = 0
        self.venue_args: dict = {}
        self.lookups: list[str] = []

    def venues_at(self, lat, lon, radius_m=40.0, limit=5, rank="DISTANCE", businesses_only=True):
        self.venue_calls += 1
        self.venue_args = {"radius_m": radius_m, "rank": rank, "businesses_only": businesses_only}
        if self._fail:
            raise ToolExecutionError("google is down")
        return self._venues

    def venue_named_in(self, text, lat, lon, radius_m=300.0):
        self.named_calls = getattr(self, "named_calls", 0) + 1
        return next((v for v in self._venues if v.name.lower() in text.lower()), None)

    def lookup(self, name, lat, lon, area="", exact=False):
        if exact:
            return None
        self.lookups.append(name)
        return None


def _run(location: Location, google) -> tuple:
    agent = build_default_agent()
    agent.place_profile_tool = google
    return agent.run(location, "How is the cafe at this location? What are the customer reviews?"), google


def test_an_address_with_a_business_standing_at_it_is_researched_as_that_business():
    response, google = _run(_address(), _FakeGoogle([_venue()]))

    assert response.location.name == "Café Pustekuchen" and response.location.is_business
    assert response.location.latitude == 50.80061
    assert google.lookups == ["Café Pustekuchen"], "the Google rating and reviews are looked up for the cafe"
    assert any("Google Maps lists Café Pustekuchen there" in lim for lim in response.limitations)
    step = next(s for s in response.research_trace if "matched to the business" in s.description)
    assert step.stage == TraceStage.LOCATION_RESOLUTION


def test_business_research_queries_are_used_after_the_address_is_matched():
    response, _ = _run(_address(), _FakeGoogle([_venue()]))

    queries = [q for topic in response.topics for q in topic.search_queries]
    assert queries and all('"Café Pustekuchen"' in q for q in queries)


def test_other_businesses_at_the_same_address_are_named_not_hidden():
    response, _ = _run(_address(), _FakeGoogle([_venue(), _venue("Salon Eins")]))

    assert response.location.name == "Café Pustekuchen"
    assert any("Other places at the same address: Salon Eins" in lim for lim in response.limitations)


def test_no_business_at_the_address_leaves_it_an_address():
    response, google = _run(_address(), _FakeGoogle([]))

    assert response.location.name == "Unterer Graben 11" and not response.location.is_business
    assert google.lookups == []


def test_a_google_failure_is_a_limitation_and_the_address_is_still_researched():
    response, _ = _run(_address(), _FakeGoogle(fail=True))

    assert response.location.name == "Unterer Graben 11"
    assert any("google is down" in lim for lim in response.limitations)


def test_an_area_or_an_existing_business_is_never_swapped_for_a_nearby_business():
    for location in (_address(is_address=False, name="Kreuzberg"), _address(is_business=True, name="Some Cafe")):
        response, google = _run(location, _FakeGoogle([_venue()]))

        assert google.venue_calls == 0, "only an address pin triggers the lookup"
        assert response.location.name == location.name


def test_without_google_an_address_is_researched_as_an_address():
    agent = build_default_agent()
    agent.place_profile_tool = None

    response = agent.run(_address(), "How is the cafe?")

    assert response.location.name == "Unterer Graben 11"


def test_a_landmark_at_the_address_is_adopted_so_a_tourist_question_gets_its_google_ratings():
    """Ginkaku-ji's address is a temple: Google calls it a tourist attraction, not a business."""
    temple = PlaceCandidate(
        name="Ginkaku-ji", display_name="Ginkaku-ji, Kyoto", category="Buddhist temple", city="Kyoto", region="Kyoto",
        country="Japan", latitude=35.0270, longitude=135.7982, is_business=False,
    )
    google = _FakeGoogle([temple])

    response, _ = _run(_address(name="2 Ginkakujicho", city="Kyoto", country="Japan", region="Kyoto"), google)

    assert response.location.name == "Ginkaku-ji" and response.location.is_business
    assert google.lookups == ["Ginkaku-ji"]
    assert google.venue_args == {"radius_m": 60.0, "rank": "POPULARITY", "businesses_only": False}
