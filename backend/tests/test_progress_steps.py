"""The agent reports each step as it happens (for the streamed research), and a failing listener never harms the run."""

from tests.fixture_tools import fixture_agent

PLACE = "Harvard Square, Cambridge, MA"
QUESTION = "Would this be a good place for a college student?"


def test_every_trace_step_is_reported_as_it_is_recorded_and_in_order():
    seen = []

    response = fixture_agent().run(PLACE, QUESTION, on_step=seen.append)

    assert [s.description for s in seen] == [s.description for s in response.research_trace]
    assert len(seen) >= 5


def test_the_slow_stages_announce_themselves_before_they_start():
    descriptions = [s.description for s in fixture_agent().run(PLACE, QUESTION).research_trace]

    def index(prefix: str) -> int:
        return next(i for i, d in enumerate(descriptions) if d.startswith(prefix))

    assert index("Working out which topics") < index("Planned")
    assert index("Reading") < index("Extracted")
    assert index("Writing the overview") < index("Generated summary")


def test_a_listener_that_raises_does_not_stop_or_change_the_run():
    def broken(step):
        raise RuntimeError("the progress display crashed")

    with_listener = fixture_agent().run(PLACE, QUESTION, on_step=broken)
    without = fixture_agent().run(PLACE, QUESTION)

    assert [s.description for s in with_listener.research_trace] == [s.description for s in without.research_trace]
    assert with_listener.summary == without.summary
