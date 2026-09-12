"""Provider-independent LLM service interface.

Milestone 1's planner and synthesizer are deliberately rule-based and do not
call an LLM at all, so that the whole pipeline runs without any API key or
network access. This interface is the seam a later milestone will use to
plug in a real, LLM-backed planner/synthesizer (e.g. an Anthropic-backed
implementation) without changing the agent's orchestration code.

`FakeLLMService` is a deterministic stand-in used only in tests that
exercise this seam directly. Nothing in the Milestone 1 agent pipeline
depends on it.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class LLMService(ABC):
    """Minimal provider-independent text-completion interface."""

    @abstractmethod
    def complete(self, system_prompt: str, user_prompt: str) -> str:
        """Return a text completion for the given prompts."""
        raise NotImplementedError


class FakeLLMService(LLMService):
    """Deterministic stand-in for tests. Never used for real research output."""

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        return f"[fake-llm-response system_len={len(system_prompt)} user_len={len(user_prompt)}]"
