import sqlite3
from datetime import datetime, timezone

from app.evidence.sqlite_repository import SQLiteEvidenceRepository, iter_run_ids, load_run
from app.models.evidence import Evidence, SourceType


def _evidence(evidence_id: str, topic: str = "housing") -> Evidence:
    return Evidence(
        evidence_id=evidence_id,
        source_url=f"https://example.org/{evidence_id}",
        source_title="Title",
        source_type=SourceType.NEWS,
        retrieved_at=datetime.now(timezone.utc),
        location_scope="Cambridge, MA",
        text="Some text.",
        topic=topic,
        metadata={"claim_text": "Rent is high."},
        relevance_score=0.5,
        quality_score=0.8,
        recency_days=10,
        # Deliberately non-None: a previous version of this repository had a
        # schema/round-trip written before `image_url` existed on Evidence,
        # which silently dropped it. Leaving this None would let that
        # regression back in without any test noticing.
        image_url="https://example.org/photo.jpg",
    )


def test_add_and_list_all_round_trips_every_field(tmp_path):
    db_path = tmp_path / "evidence.db"
    repo = SQLiteEvidenceRepository(db_path, run_id="run-1")
    original = _evidence("e1")

    repo.add(original)
    [loaded] = repo.list_all()

    assert loaded == original


def test_list_by_topic_filters_within_a_run(tmp_path):
    db_path = tmp_path / "evidence.db"
    repo = SQLiteEvidenceRepository(db_path, run_id="run-1")
    repo.add(_evidence("e1", topic="housing"))
    repo.add(_evidence("e2", topic="safety"))

    assert {e.evidence_id for e in repo.list_by_topic("housing")} == {"e1"}


def test_runs_are_isolated_from_each_other(tmp_path):
    db_path = tmp_path / "evidence.db"
    SQLiteEvidenceRepository(db_path, run_id="run-1").add(_evidence("e1"))
    SQLiteEvidenceRepository(db_path, run_id="run-2").add(_evidence("e2"))

    run_1_repo = SQLiteEvidenceRepository(db_path, run_id="run-1")
    assert {e.evidence_id for e in run_1_repo.list_all()} == {"e1"}


def test_data_survives_a_new_connection_to_the_same_file(tmp_path):
    db_path = tmp_path / "evidence.db"
    SQLiteEvidenceRepository(db_path, run_id="run-1").add(_evidence("e1"))

    reopened = SQLiteEvidenceRepository(db_path, run_id="run-1")
    assert len(reopened.list_all()) == 1


def test_iter_run_ids_and_load_run(tmp_path):
    db_path = tmp_path / "evidence.db"
    SQLiteEvidenceRepository(db_path, run_id="run-1").add(_evidence("e1"))
    SQLiteEvidenceRepository(db_path, run_id="run-2").add(_evidence("e2"))

    assert iter_run_ids(db_path) == ["run-1", "run-2"]
    assert {e.evidence_id for e in load_run(db_path, "run-1")} == {"e1"}


def test_iter_run_ids_on_missing_file_returns_empty(tmp_path):
    assert iter_run_ids(tmp_path / "does-not-exist.db") == []


def test_get_returns_none_for_missing_evidence(tmp_path):
    repo = SQLiteEvidenceRepository(tmp_path / "evidence.db", run_id="run-1")
    assert repo.get("missing") is None


def test_migrates_a_database_created_before_image_url_existed(tmp_path):
    db_path = tmp_path / "evidence.db"
    old_schema_conn = sqlite3.connect(db_path)
    old_schema_conn.execute(
        """
        CREATE TABLE evidence (
            run_id TEXT NOT NULL, evidence_id TEXT NOT NULL, source_url TEXT NOT NULL,
            source_title TEXT NOT NULL, publisher TEXT, source_type TEXT NOT NULL,
            retrieved_at TEXT NOT NULL, published_at TEXT, location_scope TEXT NOT NULL,
            text TEXT NOT NULL, topic TEXT NOT NULL, metadata TEXT NOT NULL,
            relevance_score REAL, quality_score REAL, recency_days INTEGER,
            PRIMARY KEY (run_id, evidence_id)
        )
        """
    )
    old_schema_conn.commit()
    old_schema_conn.close()

    # Opening it with the current repository should migrate in place, not crash.
    repo = SQLiteEvidenceRepository(db_path, run_id="run-1")
    repo.add(_evidence("e1"))

    [loaded] = repo.list_all()
    assert loaded.image_url == "https://example.org/photo.jpg"
