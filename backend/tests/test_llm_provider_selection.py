"""Which concrete LLMService `build_default_agent()` wires in.

Constructing OllamaLLMService is safe without a running Ollama server: its
`__init__` only builds an (unused until `.complete()`) httpx.Client. Nothing
below makes a real network call.
"""

from app.agents.factory import build_default_agent
from app.api.routes import capabilities
from app.core.llm_service import OllamaLLMService
from app.synthesis.claim_extractor import FixtureClaimExtractor


def test_ollama_is_used_when_the_llm_path_is_on():
    agent = build_default_agent(use_llm=True)

    assert isinstance(agent.claim_extractor._llm, OllamaLLMService)


def test_no_llm_falls_back_to_the_rule_based_components():
    agent = build_default_agent(use_llm=False)

    assert isinstance(agent.claim_extractor, FixtureClaimExtractor)


def test_capabilities_report_ollama_only_when_enabled(monkeypatch):
    assert capabilities().llm_provider == "none"

    monkeypatch.setenv("OLLAMA_ENABLED", "1")
    monkeypatch.setenv("OLLAMA_MODEL", "some-model")
    assert capabilities().llm_provider == "ollama"
