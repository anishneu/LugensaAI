"""Durable evidence storage backed by a local SQLite file (Milestone 5).

Requires nothing beyond the Python standard library — no server to run, no
account to create. Each `SQLiteEvidenceRepository` instance is scoped to one
`run_id`: from the agent's point of view, `list_all()` / `get()` /
`list_by_topic()` behave exactly like `InMemoryEvidenceRepository` — they
only ever see this run's own evidence, never another run's. What's
different is that the rows are written to disk immediately and survive
process restarts, so a run's evidence can be inspected later. That's what
"survives across runs" means here: durable storage per run, not merging
different runs' evidence together during retrieval (which would silently
corrupt topic coverage for whichever question is currently running).

`iter_run_ids()` and `load_run()` are the read side of that: a way to list
and re-read a past run's evidence without re-running the agent.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path

from app.evidence.repository import EvidenceRepository
from app.models.evidence import Evidence, SourceType

_SCHEMA = """
CREATE TABLE IF NOT EXISTS evidence (
    run_id TEXT NOT NULL,
    evidence_id TEXT NOT NULL,
    source_url TEXT NOT NULL,
    source_title TEXT NOT NULL,
    publisher TEXT,
    source_type TEXT NOT NULL,
    retrieved_at TEXT NOT NULL,
    published_at TEXT,
    location_scope TEXT NOT NULL,
    text TEXT NOT NULL,
    topic TEXT NOT NULL,
    metadata TEXT NOT NULL,
    relevance_score REAL,
    quality_score REAL,
    recency_days INTEGER,
    image_url TEXT,
    PRIMARY KEY (run_id, evidence_id)
)
"""


def _migrate(conn: sqlite3.Connection) -> None:
    """Add columns introduced after this table was first created.

    `CREATE TABLE IF NOT EXISTS` only helps a brand-new database file — an
    existing `backend/data/evidence.db` from before `image_url` existed on
    `Evidence` keeps its old schema forever without this, silently dropping
    the field on every read/write (which is exactly what happened: images
    worked in `TavilyWebSearchTool` but vanished by the time evidence came
    back out of storage).
    """
    existing_columns = {row[1] for row in conn.execute("PRAGMA table_info(evidence)")}
    if "image_url" not in existing_columns:
        conn.execute("ALTER TABLE evidence ADD COLUMN image_url TEXT")


def _row_to_evidence(row: sqlite3.Row) -> Evidence:
    columns = row.keys()
    return Evidence(
        evidence_id=row["evidence_id"],
        source_url=row["source_url"],
        source_title=row["source_title"],
        publisher=row["publisher"],
        source_type=SourceType(row["source_type"]),
        retrieved_at=datetime.fromisoformat(row["retrieved_at"]),
        published_at=datetime.fromisoformat(row["published_at"]) if row["published_at"] else None,
        location_scope=row["location_scope"],
        text=row["text"],
        topic=row["topic"],
        metadata=json.loads(row["metadata"]),
        relevance_score=row["relevance_score"],
        quality_score=row["quality_score"],
        recency_days=row["recency_days"],
        image_url=row["image_url"] if "image_url" in columns else None,
    )


class SQLiteEvidenceRepository(EvidenceRepository):
    def __init__(self, db_path: Path, run_id: str) -> None:
        self._run_id = run_id
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute(_SCHEMA)
        _migrate(self._conn)
        self._conn.commit()

    def add(self, evidence: Evidence) -> None:
        self._conn.execute(
            """
            INSERT OR REPLACE INTO evidence (
                run_id, evidence_id, source_url, source_title, publisher, source_type,
                retrieved_at, published_at, location_scope, text, topic, metadata,
                relevance_score, quality_score, recency_days, image_url
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                self._run_id,
                evidence.evidence_id,
                evidence.source_url,
                evidence.source_title,
                evidence.publisher,
                evidence.source_type.value,
                evidence.retrieved_at.isoformat(),
                evidence.published_at.isoformat() if evidence.published_at else None,
                evidence.location_scope,
                evidence.text,
                evidence.topic,
                json.dumps(evidence.metadata),
                evidence.relevance_score,
                evidence.quality_score,
                evidence.recency_days,
                evidence.image_url,
            ),
        )
        self._conn.commit()

    def get(self, evidence_id: str) -> Evidence | None:
        row = self._conn.execute(
            "SELECT * FROM evidence WHERE run_id = ? AND evidence_id = ?", (self._run_id, evidence_id)
        ).fetchone()
        return _row_to_evidence(row) if row else None

    def list_all(self) -> list[Evidence]:
        rows = self._conn.execute("SELECT * FROM evidence WHERE run_id = ?", (self._run_id,)).fetchall()
        return [_row_to_evidence(row) for row in rows]

    def list_by_topic(self, topic_id: str) -> list[Evidence]:
        rows = self._conn.execute(
            "SELECT * FROM evidence WHERE run_id = ? AND topic = ?", (self._run_id, topic_id)
        ).fetchall()
        return [_row_to_evidence(row) for row in rows]

    def close(self) -> None:
        self._conn.close()


def iter_run_ids(db_path: Path) -> list[str]:
    """List every run_id ever written to this database file, oldest first."""
    if not db_path.exists():
        return []
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(_SCHEMA)
        rows = conn.execute("SELECT DISTINCT run_id FROM evidence ORDER BY rowid").fetchall()
        return [row[0] for row in rows]
    finally:
        conn.close()


def load_run(db_path: Path, run_id: str) -> list[Evidence]:
    """Read back a past run's evidence without re-running the agent."""
    return SQLiteEvidenceRepository(db_path, run_id).list_all()
