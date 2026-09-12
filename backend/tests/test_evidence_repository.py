from datetime import datetime, timezone

from app.evidence.repository import InMemoryEvidenceRepository
from app.models.evidence import Evidence, SourceType


def _evidence(evidence_id: str, topic: str) -> Evidence:
    return Evidence(
        evidence_id=evidence_id,
        source_url=f"https://example.org/{evidence_id}",
        source_title="Title",
        source_type=SourceType.NEWS,
        retrieved_at=datetime.now(timezone.utc),
        location_scope="Cambridge, MA",
        text="Some text.",
        topic=topic,
    )


def test_add_and_get():
    repo = InMemoryEvidenceRepository()
    repo.add(_evidence("e1", "housing"))

    assert repo.get("e1") is not None
    assert repo.get("missing") is None


def test_add_all_and_list_all():
    repo = InMemoryEvidenceRepository()
    repo.add_all([_evidence("e1", "housing"), _evidence("e2", "safety")])

    assert {e.evidence_id for e in repo.list_all()} == {"e1", "e2"}


def test_list_by_topic():
    repo = InMemoryEvidenceRepository()
    repo.add_all([_evidence("e1", "housing"), _evidence("e2", "safety"), _evidence("e3", "housing")])

    housing_evidence = repo.list_by_topic("housing")

    assert {e.evidence_id for e in housing_evidence} == {"e1", "e3"}


def test_adding_same_id_twice_overwrites():
    repo = InMemoryEvidenceRepository()
    repo.add(_evidence("e1", "housing"))
    repo.add(_evidence("e1", "safety"))

    assert len(repo.list_all()) == 1
    assert repo.get("e1").topic == "safety"
