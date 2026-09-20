"""Small JSON-loading helpers shared by the fixture-backed tools.

All fixture content under `backend/tests/fixtures/` is synthetic test data written
for local development and testing. It does not represent real, current
information about any real place and must never be treated as such outside
this project's test suite. Nothing under `app/` imports this module: the running product never
serves fixture evidence, claims or places.
"""

from __future__ import annotations

import json
from pathlib import Path

FIXTURES_ROOT = Path(__file__).resolve().parent / "fixtures"


def load_locations(fixtures_root: Path = FIXTURES_ROOT) -> list[dict]:
    path = fixtures_root / "locations.json"
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def load_topic_documents(slug: str, topic_id: str, fixtures_root: Path = FIXTURES_ROOT) -> list[dict]:
    """Return the fixture documents for a (location, topic) pair.

    Returns an empty list if no fixture file exists — this represents a
    genuine coverage gap (no evidence available), not an error.
    """
    path = fixtures_root / "sources" / slug / f"{topic_id}.json"
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def iter_all_documents(fixtures_root: Path = FIXTURES_ROOT):
    """Yield (slug, topic_id, document) for every fixture document on disk."""
    sources_root = fixtures_root / "sources"
    if not sources_root.exists():
        return
    for location_dir in sources_root.iterdir():
        if not location_dir.is_dir():
            continue
        for topic_file in location_dir.glob("*.json"):
            with topic_file.open(encoding="utf-8") as f:
                documents = json.load(f)
            for document in documents:
                yield location_dir.name, topic_file.stem, document
