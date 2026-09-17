"""Shared helper for parsing structured JSON out of an LLM text completion.

Every LLM-backed component in this project asks for strict JSON output but
still has to tolerate models that wrap it in a markdown code fence or add
stray whitespace — this is the one place that leniency lives.
"""

from __future__ import annotations

import json
import re

_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def parse_json_object(text: str) -> dict:
    """Parse `text` as a JSON object, tolerating a surrounding markdown fence.

    Raises ValueError (not a json.JSONDecodeError) so callers can catch one
    exception type regardless of what specifically went wrong.
    """
    cleaned = _FENCE_RE.sub("", text.strip()).strip()
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise ValueError(f"LLM output was not valid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ValueError(f"Expected a JSON object, got {type(parsed).__name__}")
    return parsed
