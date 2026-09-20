"""A scripted LLMService test double shared by the Milestone 2 LLM tests.

None of these tests call a real model — that would be slow and nondeterministic.
This double lets us exercise the LLM-backed components'
parsing, validation, and fallback logic deterministically instead.
"""

from __future__ import annotations

from app.core.llm_service import LLMService, LLMServiceError


class ScriptedLLMService(LLMService):
    def __init__(self, responses: list[str] | None = None, raise_error: bool = False) -> None:
        self._responses = list(responses or [])
        self._raise_error = raise_error
        self.calls: list[tuple[str, str]] = []

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        self.calls.append((system_prompt, user_prompt))
        if self._raise_error:
            raise LLMServiceError("scripted failure")
        if not self._responses:
            raise LLMServiceError("ScriptedLLMService ran out of scripted responses")
        return self._responses.pop(0)
