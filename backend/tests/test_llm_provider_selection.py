"""Which concrete LLMService `build_default_agent()` wires in.

Constructing either concrete service is safe without a real key or a running
Ollama server: `AnthropicLLMService.__init__` only stores credentials, and
`OllamaLLMService.__init__` only builds an (unused until `.complete()`)
httpx.Client. Neither test below makes a real network call.
"""

from app.agents.factory import build_default_agent
from app.core.llm_service import AnthropicLLMService, OllamaLLMService


def test_anthropic_is_used_when_its_key_is_set(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-key-for-construction-only")

    agent = build_default_agent(use_llm=True)

    assert isinstance(agent.claim_extractor._llm, AnthropicLLMService)


def test_ollama_is_used_when_enabled_without_an_anthropic_key():
    agent = build_default_agent(use_llm=True)

    assert isinstance(agent.claim_extractor._llm, OllamaLLMService)


def test_anthropic_takes_priority_when_both_are_configured(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-key-for-construction-only")
    monkeypatch.setenv("OLLAMA_ENABLED", "1")

    agent = build_default_agent(use_llm=True)

    assert isinstance(agent.claim_extractor._llm, AnthropicLLMService)
