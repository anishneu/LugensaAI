"""The running product must never serve invented evidence, claims or places.

Fixture data lives in tests/fixtures and is reachable only through tests/fixture_tools.py.
"""

from pathlib import Path

APP = Path(__file__).resolve().parent.parent / "app"
FORBIDDEN = ("tests.fixture", "fixtures/", "FixtureClaimExtractor", "FixtureWebSearchTool", "FixtureLocationResolver", ".example.net", ".example.org")


def test_nothing_under_app_references_fixture_data():
    offenders = {
        f"{path.relative_to(APP)}: {token}"
        for path in APP.rglob("*.py")
        for token in FORBIDDEN
        if token in path.read_text(encoding="utf-8")
    }

    assert not offenders, sorted(offenders)


def test_the_fixture_directories_are_gone_from_the_backend_root():
    assert not (APP.parent / "fixtures").exists()
