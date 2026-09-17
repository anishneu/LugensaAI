"""Provider-independent LLM service interface.

Milestone 1's planner and synthesizer were deliberately rule-based and never
called an LLM, so the whole pipeline ran without any API key or network
access. Milestone 2 adds a real, Anthropic-backed implementation of this
same interface — `AnthropicLLMService` — used by the LLM-backed planner,
claim extractor, and synthesizer in `app/planning/llm_planner.py` and
`app/synthesis/llm_*.py`. Nothing calls it unless `ANTHROPIC_API_KEY` is set
(see `app/core/config.py` and `app/agents/factory.py`); by default the
pipeline still runs entirely on the free, deterministic Milestone 1 path.

`FakeLLMService` is a deterministic stand-in used only in tests. It is never
used for real research output.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.core.config import ANTHROPIC_MAX_TOKENS, ANTHROPIC_MODEL


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
