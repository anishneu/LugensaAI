"""Provider-independent LLM service interface.

Milestone 1's planner and synthesizer were deliberately rule-based and never
called an LLM, so the whole pipeline ran without any API key or network
access. Milestone 2 adds real implementations of this same interface, used
by the LLM-backed planner, claim extractor, and synthesizer in
`app/planning/llm_planner.py` and `app/synthesis/llm_*.py`:

- `OllamaLLMService` — free and local, used when `OLLAMA_ENABLED` is set
  (see `app/core/config.py` and `app/agents/factory.py`).

When it is not set the pipeline still runs on its rule-based components, and
says in each response which steps were skipped for lack of a model.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

import httpx

from app.core.config import (
    OLLAMA_BASE_URL,
    OLLAMA_KEEP_ALIVE,
    OLLAMA_MODEL,
    OLLAMA_NUM_CTX,
    OLLAMA_THINK,
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
        num_ctx: int = OLLAMA_NUM_CTX,
        think: str = OLLAMA_THINK,
    ) -> None:
        self._model = model
        self._num_ctx = num_ctx
        self._think = think
        self._client = httpx.Client(base_url=base_url, transport=transport, timeout=timeout)

    def request_body(self, system_prompt: str, user_prompt: str) -> dict:
        """The exact /api/chat payload — exposed so a benchmark can send the
        same request the app does and read Ollama's timing counters."""
        body: dict = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
            "format": "json",
            "options": {"num_ctx": self._num_ctx},
            "keep_alive": OLLAMA_KEEP_ALIVE,
        }
        if self._think == "false":
            body["think"] = False
        return body

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        try:
            response = self._client.post("/api/chat", json=self.request_body(system_prompt, user_prompt))
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
