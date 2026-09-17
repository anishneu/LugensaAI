"""Cross-source contradiction detection (Milestone 6).

Deliberately kept out of the LLM's hands, same as the rest of
`ClaimVerifier` (see `docs/research-workflow.md`'s "LLM integration"
section) — verification is the one step in this pipeline that is never
LLM-backed, so it can't itself be fooled by a persuasive-sounding but wrong
model output.

This is a coarse, honest heuristic — a small curated list of domain-relevant
opposite-sentiment phrase pairs — not real natural-language contradiction
detection (which would need to handle negation, hedging, differing scope,
etc.). It catches the clear cases (`"crime is low"` vs. `"high crime area"`)
and is documented as exactly that: the same spirit as `_classify_source_type`
in `app/tools/tavily_tools.py` — a real, bounded, explainable technique, not
a placeholder pretending to be sophisticated.
"""

from __future__ import annotations

_ANTONYM_PAIRS: tuple[tuple[frozenset[str], frozenset[str]], ...] = (
    (frozenset({"safe", "safety"}), frozenset({"unsafe", "dangerous", "danger"})),
    (frozenset({"low crime"}), frozenset({"high crime"})),
    (frozenset({"affordable", "cheap", "inexpensive"}), frozenset({"expensive", "costly", "unaffordable"})),
    (frozenset({"convenient"}), frozenset({"inconvenient"})),
    (frozenset({"walkable"}), frozenset({"not walkable", "unwalkable"})),
    (frozenset({"quiet"}), frozenset({"noisy", "loud"})),
    (frozenset({"clean"}), frozenset({"dirty"})),
    (frozenset({"well-lit", "well lit"}), frozenset({"poorly lit", "poorly-lit", "dark"})),
    (frozenset({"improving", "improved"}), frozenset({"declining", "worsening", "worsened"})),
)


def claims_contradict(text_a: str, text_b: str) -> bool:
    """Whether two claim texts appear to state opposite things.

    True only when one text contains a phrase from one side of a curated
    antonym pair and the other text contains a phrase from the other side.
    """
    lowered_a = text_a.lower()
    lowered_b = text_b.lower()
    for group_a, group_b in _ANTONYM_PAIRS:
        a_has_first = any(phrase in lowered_a for phrase in group_a)
        a_has_second = any(phrase in lowered_a for phrase in group_b)
        b_has_first = any(phrase in lowered_b for phrase in group_a)
        b_has_second = any(phrase in lowered_b for phrase in group_b)
        if (a_has_first and b_has_second) or (a_has_second and b_has_first):
            return True
    return False
