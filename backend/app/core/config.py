from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel

BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent

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
    # After the first search pass the agent may look at what it found and decide
    # to search again or consult another source. Each round is one such decision;
    # both limits keep the loop bounded (and inside the per-question time budget).
    max_research_rounds: int = 2
    max_actions_per_round: int = 2


# --- LLM configuration (Milestone 2) -----------------------------------
#
# The LLM-backed planner, claim extractor and synthesizer run on a local
# Ollama model (https://ollama.com): no API key, no per-token billing, nothing
# leaves this machine. Ollama needs to be installed with a model pulled
# (`ollama pull <model>`), and inference is only as fast as this machine's
# CPU/GPU. Since it needs real local setup the user may not have done, it is
# opt-in via OLLAMA_ENABLED, not auto-detected. Without it,
# `build_default_agent()` uses the free, rule-based Milestone 1 components
# exclusively (see app/agents/factory.py).
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
# qwen3:30b is a mixture-of-experts model: 30B parameters of knowledge but only
# ~3B active per token, so it writes about as fast as a small model while
# reading and reasoning far better. Measured against the previous default
# (llama3.2:3b) on the same question and hardware it took the same ~3 minutes
# and produced 3 precise, source-grounded claims where the 3B produced 13
# padded ones. It needs ~19GB of RAM and `ollama pull qwen3:30b`.
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen3:30b")
# A slow first call (loading the model into memory) is normal; default the
# timeout generously rather than fall back to rules mid-question.
OLLAMA_TIMEOUT_SECONDS = float(os.environ.get("OLLAMA_TIMEOUT_SECONDS", "600"))
# Ollama silently truncates any prompt longer than the context window, and its
# default window is small. The synthesis prompt carries a system prompt, the
# claims and several evidence excerpts, so ask for room explicitly rather than
# have the model quietly answer from the first half of its evidence.
OLLAMA_NUM_CTX = int(os.environ.get("OLLAMA_NUM_CTX", "8192"))
# Reasoning models (Qwen3, DeepSeek-R1, gpt-oss) spend most of a request
# "thinking" before they answer. Measured on qwen3:30b: 233 seconds with
# thinking on versus 6.7 seconds off, for an extract-and-summarize task that
# gains nothing from it. Default "false" (models with no thinking mode accept
# and ignore it); set to "" to send nothing.
OLLAMA_THINK = os.environ.get("OLLAMA_THINK", "false").strip().lower()
# Loading a 19GB model takes 25-40 seconds. Ollama unloads after 5 idle minutes
# by default, so a question asked after a coffee break would pay that again.
OLLAMA_KEEP_ALIVE = os.environ.get("OLLAMA_KEEP_ALIVE", "30m")


def ollama_enabled() -> bool:
    return bool(os.environ.get("OLLAMA_ENABLED"))


def llm_enabled() -> bool:
    """Whether the LLM-backed path is configured."""
    return ollama_enabled()


# --- Search configuration (Milestone 3) ---------------------------------
#
# Nothing calls the Tavily API unless TAVILY_API_KEY is set. Without it nothing is searched, and
# every response says so. Tavily's free tier (1,000 credits a month) covers light usage; beyond that it
# is a paid service billed by Tavily, not something this project controls.
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


# Translation of foreign-language evidence into English (Argos Translate,
# local and free). On when both packages are installed, off if either is
# missing or DISABLE_TRANSLATION is set (tests force this off).
def translation_enabled() -> bool:
    if os.environ.get("DISABLE_TRANSLATION"):
        return False
    try:
        import argostranslate  # noqa: F401
        import langdetect  # noqa: F401
    except ImportError:
        return False
    return True


GOOGLE_PLACES_API_KEY_ENV_VAR = "GOOGLE_PLACES_API_KEY"


def place_profile_enabled() -> bool:
    """Google Maps ratings/reviews for one specific business. Opt-in: needs a
    key from a Google Cloud project with billing enabled (see
    app/tools/google_places_tool.py). Also off under DISABLE_PLACE_PROFILE."""
    return bool(os.environ.get(GOOGLE_PLACES_API_KEY_ENV_VAR)) and not os.environ.get("DISABLE_PLACE_PROFILE")


SEMANTIC_MODEL_NAME = os.environ.get("SEMANTIC_MODEL_NAME", "sentence-transformers/all-MiniLM-L6-v2")


# --- Geocoding / POI search (Milestone 9) -------------------------------
#
# Live geocoding (OpenStreetMap Nominatim) needs no API key, so — unlike
# TAVILY_API_KEY / OLLAMA_ENABLED — this is opt-out, not opt-in: on by
# default, off only if DISABLE_LIVE_GEOCODING is set (tests force this off
# so the suite never makes a real network call — see tests/conftest.py).
def geocoding_enabled() -> bool:
    return not bool(os.environ.get("DISABLE_LIVE_GEOCODING"))


# Wikipedia/Wikivoyage (app/tools/wiki_tool.py): free, no key. Wikimedia blocks
# clients that don't identify themselves with contact details, so this is sent
# in the User-Agent. Override it if you fork the project.
WIKIMEDIA_CONTACT = os.environ.get("WIKIMEDIA_CONTACT", "https://github.com/anishneu/agentic-ai-location-web")
