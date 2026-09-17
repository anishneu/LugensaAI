"""Provider-independent LLM service interface.

Milestone 1's planner and synthesizer were deliberately rule-based and never
called an LLM, so the whole pipeline ran without any API key or network
access. Milestone 2 adds real implementations of this same interface, used
by the LLM-backed planner, claim extractor, and synthesizer in
`app/planning/llm_planner.py` and `app/synthesis/llm_*.py`:

- `AnthropicLLMService` — billed per Anthropic's normal pricing, used when
  `ANTHROPIC_API_KEY` is set.
- `OllamaLLMService` — free and local, used when `OLLAMA_ENABLED` is set
  instead (see `app/core/config.py`; Anthropic takes priority if both are
  set — see `app/agents/factory.py`).

By default (neither set) the pipeline still runs entirely on the free,
deterministic Milestone 1 path.

`FakeLLMService` is a deterministic stand-in used only in tests. It is never
used for real research output.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

import httpx

from app.core.config import (
    ANTHROPIC_MAX_TOKENS,
    ANTHROPIC_MODEL,
    OLLAMA_BASE_URL,
    OLLAMA_MODEL,
    OLLAMA_TIMEOUT_SECONDS,
)


class LLMServiceError(Exception):
    """Raised when an LLM call fails or returns unusable output.

    Callers (the LLM-backed planner/extractor/synthesizer) are expected to
    catch this and fall back to their Milestone 1 rule-based counterpart
    rather than let a single flaky API call take down the whole pipeline.
    """


class LLMService(ABC):
    """Minimal provider-independent text-completion interface."""

    @abstractmethod
    def complete(self, system_prompt: str, user_prompt: str) -> str:
        """Return a text completion for the given prompts.

        Raises LLMServiceError on any failure (network, auth, rate limit).
        """
        raise NotImplementedError


class FakeLLMService(LLMService):
    """Deterministic stand-in for tests. Never used for real research output."""

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        return f"[fake-llm-response system_len={len(system_prompt)} user_len={len(user_prompt)}]"


class AnthropicLLMService(LLMService):
    """Calls the real Anthropic API. Requires `ANTHROPIC_API_KEY` in the environment.

    Importing this module never requires the `anthropic` package or a key —
    only instantiating this class does, so the rest of the app can reference
    `LLMService` freely without pulling in a hard dependency on a live key.
    """

    def __init__(self, model: str = ANTHROPIC_MODEL, max_tokens: int = ANTHROPIC_MAX_TOKENS) -> None:
        try:
            import anthropic
        except ImportError as exc:  # pragma: no cover - exercised only without the dependency installed
            raise LLMServiceError(
                "The 'anthropic' package is required for AnthropicLLMService. Install it with "
                "`pip install anthropic` (already in requirements.txt)."
            ) from exc
        self._client = anthropic.Anthropic()
        self._model = model
        self._max_tokens = max_tokens

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        import anthropic

        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=self._max_tokens,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            )
        except anthropic.APIError as exc:
            raise LLMServiceError(f"Anthropic API call failed: {exc}") from exc

        text_blocks = [block.text for block in response.content if getattr(block, "type", None) == "text"]
        if not text_blocks:
            raise LLMServiceError("Anthropic API returned no text content.")
        return "".join(text_blocks)


class OllamaLLMService(LLMService):
    """Calls a local Ollama server (https://ollama.com) — free, no API key,
    no per-token billing, but it does need Ollama installed and running with
    `model` already pulled (`ollama pull <model>`) on this machine.

    Every current caller of `LLMService.complete()` in this project asks for
    strict JSON in its own system prompt (see `app/core/llm_json.py`), so
    passing Ollama's `format: "json"` here is safe for all of them and
    meaningfully improves how reliably a local model returns parseable JSON.

    `transport` is exposed purely so tests can inject `httpx.MockTransport`
    instead of making a real local network call — see tests/test_llm_service.py.
    """

    def __init__(
        self,
        base_url: str = OLLAMA_BASE_URL,
        model: str = OLLAMA_MODEL,
        timeout: float = OLLAMA_TIMEOUT_SECONDS,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._model = model
        self._client = httpx.Client(base_url=base_url, transport=transport, timeout=timeout)

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        try:
            response = self._client.post(
                "/api/chat",
                json={
                    "model": self._model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "stream": False,
                    "format": "json",
                },
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise LLMServiceError(
                f"Ollama call failed ({exc}). Is Ollama running (`ollama serve`) with the "
                f"'{self._model}' model pulled (`ollama pull {self._model}`)?"
            ) from exc

        content = response.json().get("message", {}).get("content")
        if not content:
            raise LLMServiceError("Ollama response had no message content.")
        return content
