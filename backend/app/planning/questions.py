"""Telling apart the questions in one prompt from the context around them.

A person often asks several things at once ("How is the university? I heard a great deal about its co-op program. How often do people
get co-ops?"). The research plan is made from the whole text, so its topics cover all of it, but the *answer* has to address each
question, and say so when the evidence cannot answer one. That needs the questions separated, which is what this does: plain rules,
no model, and deliberately cautious: when in doubt it finds fewer questions, and one question is the normal case that changes nothing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# What an English question starts with. (A prompt in another language has none of these, so its sentences are judged by the second
# rule below.)
_INTERROGATIVES = frozenset(
    "who whom whose what which when where why how is are am was were do does did can could should would will shall may might has have "
    "had any anyone anybody isn't aren't don't doesn't didn't can't won't wasn't weren't what's how's where's who's when's why's".split()
)
# What a statement starts with. A sentence that starts like this and ends in "?" is a statement typed with a question mark ("I heard a
# great deal about it?"), and is context, not a second question.
_STATEMENT_STARTS = frozenset(
    "i i'm i've i'd i'll we we're we've my our he she they it its it's there this that these those the a an".split()
)
_QUESTION_MARKS = "?？"
_ABBREVIATION = re.compile(r"^(?:[A-Za-z]{1,3}|[A-Za-z]\.[A-Za-z])$")


@dataclass(frozen=True)
class Prompt:
    """A prompt taken apart: the questions in it, in order, and the other sentences (what the person said around them)."""

    questions: list[str]
    context: list[str]

    @property
    def is_multi(self) -> bool:
        return len(self.questions) > 1


def _sentences(text: str) -> list[str]:
    """Sentences, split after "?", "!" and full stops, but not after an abbreviation ("St. Louis") and not inside "U.S."."""
    out: list[str] = []
    for chunk in re.split(r"(?<=[?？!！])\s+|\n+", text.strip()):
        current: list[str] = []
        for word in chunk.split():
            current.append(word)
            if word.endswith(".") and not _ABBREVIATION.match(word[:-1]) and len(word) > 2:
                out.append(" ".join(current))
                current = []
        if current:
            out.append(" ".join(current))
    return [s.strip() for s in out if s.strip()]


def _first_word(sentence: str) -> str:
    return re.sub(r"^[^\w']+", "", sentence.split()[0]).lower() if sentence.split() else ""


def _is_question(sentence: str) -> bool:
    if not sentence.rstrip().endswith(tuple(_QUESTION_MARKS)):
        return False
    first = _first_word(sentence)
    if first in _INTERROGATIVES:
        return True
    return first not in _STATEMENT_STARTS


def split_prompt(text: str) -> Prompt:
    """The questions and the context in a prompt. A prompt with no question mark has no questions: it is one request, and is treated whole."""
    questions: list[str] = []
    context: list[str] = []
    for sentence in _sentences(text):
        (questions if _is_question(sentence) else context).append(sentence)
    return Prompt(questions=questions, context=context)
