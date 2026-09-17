from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel

BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent
FIXTURES_ROOT = BACKEND_ROOT / "fixtures"

# Load backend/.env (gitignored) into the environment, if present, before any
# of the env-var reads below. Explicit path so this works regardless of the
# process's current working directory.
try:
    from dotenv import load_dotenv

    load_dotenv(BACKEND_ROOT / ".env")
except ImportError:  # pragma: no cover - dotenv is in requirements.txt but stay lenient
    pass


class AgentConfig(BaseModel):
    """Bounded-loop and retrieval limits for a LocationResearchAgent run.

    These exist so the research loop is guaranteed to terminate and cannot
    run away making unbounded tool calls or hoarding unlimited evidence.
    """

    max_tool_calls: int = 30
    max_evidence_per_topic: int = 4
    min_relevance_score: float = 0.25
    stale_evidence_days: int = 730


# --- LLM configuration (Milestone 2) -----------------------------------
#
# Nothing in this project calls the Anthropic API unless ANTHROPIC_API_KEY is
# set. Without it, `build_default_agent()` uses the free, rule-based
# Milestone 1 components exclusively (see app/agents/factory.py). Anthropic
# API usage is billed per Anthropic's normal pricing once a key is set — it
# is not free, just optional and inexpensive with the default model.
ANTHROPIC_API_KEY_ENV_VAR = "ANTHROPIC_API_KEY"
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")
ANTHROPIC_MAX_TOKENS = int(os.environ.get("ANTHROPIC_MAX_TOKENS", "1024"))


def anthropic_enabled() -> bool:
    """Whether an Anthropic API key is configured in the environment."""
    return bool(os.environ.get(ANTHROPIC_API_KEY_ENV_VAR))


# --- Ollama configuration (free, local alternative to Anthropic) -------
#
# Ollama (https://ollama.com) runs a model entirely on this machine — no API
# key, no per-token billing — but it does need Ollama installed and a model
# pulled locally (`ollama pull <model>`) first, and inference is only as fast
# as this machine's CPU/GPU. Unlike ANTHROPIC_API_KEY, there's no key whose
# presence implies intent to use it, and unlike geocoding it needs real local
# setup the user may not have done — so this is opt-in via OLLAMA_ENABLED,
# not auto-detected.
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.1")
# CPU-only inference of even a small (~8B) model can take minutes per call,
# well past what would be a reasonable timeout for a hosted API -- default
# generously and let a real deployment with a hosted/GPU Ollama tighten it.
OLLAMA_TIMEOUT_SECONDS = float(os.environ.get("OLLAMA_TIMEOUT_SECONDS", "600"))


def ollama_enabled() -> bool:
    return bool(os.environ.get("OLLAMA_ENABLED"))


def llm_enabled() -> bool:
    """Whether an LLM-backed path (Anthropic or Ollama) is configured."""
    return anthropic_enabled() or ollama_enabled()


# --- Search configuration (Milestone 3) ---------------------------------
#
# Nothing calls the Tavily API unless TAVILY_API_KEY is set. Without it,
# `build_default_agent()` uses the free, fixture-backed Milestone 1 tools
# exclusively. Tavily's free tier covers light usage; beyond that it is a
# paid service billed by Tavily, not something this project controls.
TAVILY_API_KEY_ENV_VAR = "TAVILY_API_KEY"
TAVILY_MAX_RESULTS = int(os.environ.get("TAVILY_MAX_RESULTS", "4"))


def search_enabled() -> bool:
    """Whether a Tavily API key is configured in the environment."""
    return bool(os.environ.get(TAVILY_API_KEY_ENV_VAR))


# --- Evidence storage (Milestone 5) -------------------------------------
#
# SQLite, not a hosted database — no server to run, no account to create.
def evidence_db_path() -> Path:
    """A function, not a constant, so tests can override EVIDENCE_DB_PATH per-test
    (via monkeypatch) and have it take effect without needing to re-import this
    module — see tests/conftest.py, which points every test at a temp file so
    tests never write into the real project data directory."""
    return Path(os.environ.get("EVIDENCE_DB_PATH", str(BACKEND_ROOT / "data" / "evidence.db")))


# --- Retrieval configuration (Milestone 4) ------------------------------
#
# Semantic retrieval uses a local sentence-transformers model — no API key,
# but a real (if one-time, cached) model download and real CPU inference, so
# it's opt-out rather than opt-in: on by default if the package is
# installed, off if it isn't or if DISABLE_SEMANTIC_RETRIEVAL is set (tests
# force this off so the suite stays fast — see tests/conftest.py).
def semantic_retrieval_enabled() -> bool:
    if os.environ.get("DISABLE_SEMANTIC_RETRIEVAL"):
        return False
    try:
        import sentence_transformers  # noqa: F401
    except ImportError:
        return False
    return True


SEMANTIC_MODEL_NAME = os.environ.get("SEMANTIC_MODEL_NAME", "sentence-transformers/all-MiniLM-L6-v2")


# --- Geocoding / POI search (Milestone 9) -------------------------------
#
# Live geocoding (OpenStreetMap Nominatim) needs no API key, so — unlike
# ANTHROPIC_API_KEY / TAVILY_API_KEY — this is opt-out, not opt-in: on by
# default, off only if DISABLE_LIVE_GEOCODING is set (tests force this off
# so the suite never makes a real network call — see tests/conftest.py).
def geocoding_enabled() -> bool:
    return not bool(os.environ.get("DISABLE_LIVE_GEOCODING"))
