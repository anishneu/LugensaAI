"""A pin on a street corner or a station approach, and a question that names the business beside it."""

from app.agents.factory import build_default_agent
from app.models.location import Location
from app.models.place import PlaceCandidate
from app.models.place_profile import PlaceProfile
from app.tools.base import ToolExecutionError


def _pin(**overrides) -> Location:
    base = dict(
        name="Hunts Bank & Victoria Station Approach", city="Manchester", region="England", country="United Kingdom",
        slug="hb", latitude=53.4855, longitude=-2.2427, raw_query="Hunts Bank & Victoria Station Approach, Manchester",
    )
    return Location(**{**base, **overrides})


def _arena() -> PlaceCandidate:
    return PlaceCandidate(
        name="AO Arena", display_name="AO Arena", category="Arena", city="Manchester", region="England",
        country="United Kingdom", latitude=53.4885, longitude=-2.2440, is_business=True,
    )


class _Google:
    def __init__(self, venue=None, fail=False, rating=4.6) -> None:
        self._venue, self._fail, self._rating = venue, fail, rating
        self.named_calls = 0
        self.lookups: list[str] = []

    def venues_at(self, lat, lon, radius_m=40.0, limit=5):
        return []

    def venue_named_in(self, text, lat, lon, radius_m=300.0):
        self.named_calls += 1
        if self._fail:
            raise ToolExecutionError("google is down")
        return self._venue if self._venue and self._venue.name.lower() in text.lower() else None

    def lookup(self, name, lat, lon, area=""):
        self.lookups.append(name)
        return PlaceProfile(place_id="p", name=name, rating=self._rating, review_count=48_213)


def _run(question: str, google, location: Location | None = None):
    agent = build_default_agent()
    agent.place_profile_tool = google
    return agent.run(location or _pin(), question)


def test_a_question_that_names_the_venue_beside_the_pin_researches_that_venue():
    google = _Google(_arena())

    response = _run("How are the reviews of this AO Arena.", google)

    assert response.location.name == "AO Arena" and response.location.is_business
    assert google.lookups == ["AO Arena"], "its Google Maps rating and reviews are fetched"
    assert any("names AO Arena" in lim for lim in response.limitations)


def test_the_google_rating_opens_the_key_findings_of_a_reviews_question():
    response = _run("How are the reviews of this AO Arena?", _Google(_arena(), rating=4.6))

    assert response.key_findings[0] == "Google Maps rates AO Arena 4.6 out of 5 from 48,213 reviews."


def test_a_question_that_names_nothing_costs_no_google_call_and_keeps_the_pin():
    google = _Google(_arena())

    response = _run("is it a good place to visit?", google)

    assert google.named_calls == 0 and not response.location.is_business


def test_a_named_business_that_is_not_near_the_pin_is_not_adopted():
    google = _Google(None)

    response = _run("How are the reviews of Old Trafford?", google)

    assert google.named_calls == 1 and response.location.name.startswith("Hunts Bank") and google.lookups == []


def test_a_google_outage_is_a_limitation_not_a_crash():
    response = _run("How are the reviews of AO Arena?", _Google(_arena(), fail=True))

    assert any("Could not check Google Maps for a business named" in lim for lim in response.limitations)
    assert response.summary


def test_a_pin_that_is_already_a_business_is_never_swapped():
    google = _Google(_arena())

    response = _run("How are the reviews of AO Arena?", google, _pin(name="Some Cafe", is_business=True))

    assert google.named_calls == 0 and response.location.name == "Some Cafe"


def test_the_rating_line_is_not_repeated_when_a_finding_already_states_it():
    from app.agents.location_research_agent import LocationResearchAgent  # noqa: F401 - documents what is under test

    class Restating:
        writes_free_text = False

        def synthesize(self, *args, **kwargs):
            from app.synthesis.synthesizer import SynthesisResult

            return SynthesisResult(summary="s", key_findings=["4.6/5 average rating from 48,213 Google Maps reviews"], details="d", recommendation="r")

    agent = build_default_agent()
    agent.place_profile_tool = _Google(_arena(), rating=4.6)
    agent.synthesizer = Restating()

    response = agent.run(_pin(), "How are the reviews of this AO Arena?")

    assert response.key_findings == ["4.6/5 average rating from 48,213 Google Maps reviews"]
