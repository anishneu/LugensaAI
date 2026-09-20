import pytest

from app.models.location import Location


@pytest.fixture(autouse=True)
def _isolated_test_environment(monkeypatch, tmp_path):
    """Keep the whole test suite free, offline, fast, and side-effect-free.

    A developer's local `.env` may set real keys for manual/live testing
    (see backend/README.md), and semantic retrieval auto-enables itself if
    `sentence-transformers` happens to be installed — without this fixture,
    running `pytest` on such a machine would silently make real, billed API
    calls, load a real embedding model, and write into the real project
    `data/` directory. This fixture forces every test back to the free,
    deterministic, temp-storage default regardless of local machine state.
    Tests that specifically want the LLM-backed, live-search, or semantic
    path inject a fake/scripted implementation directly instead of relying
    on env vars or real external resources.
    """
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    monkeypatch.delenv("OLLAMA_ENABLED", raising=False)
    monkeypatch.delenv("GOOGLE_PLACES_API_KEY", raising=False)
    monkeypatch.setenv("DISABLE_SEMANTIC_RETRIEVAL", "1")
    monkeypatch.setenv("DISABLE_LIVE_GEOCODING", "1")
    monkeypatch.setenv("DISABLE_TRANSLATION", "1")
    monkeypatch.setenv("EVIDENCE_DB_PATH", str(tmp_path / "evidence.db"))
    # Module-level caches would otherwise carry one test's mocked Google answer
    # into the next test that asks the same question.
    from app.tools import google_places_tool

    google_places_tool._CACHE.clear()
    google_places_tool._SEARCH_CACHE.clear()
    from app.tools import tavily_tools

    tavily_tools._FEED_CACHE.clear()
    # The live feed shows the last 30 days: pin the clock so the tests' dates stay inside (or outside) it whenever they run.
    from datetime import datetime, timezone

    monkeypatch.setattr(tavily_tools, "_now", lambda: datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc))
    tavily_tools._SCOPE_CACHE.clear()
    tavily_tools._FEED_INFLIGHT.clear()


@pytest.fixture
def harvard_square() -> Location:
    return Location(
        name="Harvard Square",
        city="Cambridge",
        region="MA",
        country="US",
        slug="harvard-square-cambridge-ma",
        latitude=42.3736,
        longitude=-71.119,
        raw_query="Harvard Square, Cambridge, MA",
    )


@pytest.fixture
def starbucks_cambridge() -> Location:
    """A specific POI with a generic chain name — used to test that live-feed
    relevance filtering doesn't let name-only matches through unrelated
    content about the same chain in other cities."""
    return Location(
        name="Starbucks",
        city="Cambridge",
        region="MA",
        country="US",
        slug="starbucks-120-broadway-cambridge-ma",
        latitude=42.3656,
        longitude=-71.1029,
        raw_query="Starbucks, 120, Broadway, MIT, Cambridge, Massachusetts",
    )
