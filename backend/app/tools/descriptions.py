"""A readable description from the raw text of a web page snippet.

A search snippet is not prose. Measured on a live news search, it is the page's own markdown and chrome joined
together: `## Related headline` lines, "8 hours ago" stamps, bylines, `[](...)` link leftovers, `[...]` where
two passages were stitched, a "company logo" alt text, a newsletter pitch. Shown as-is in a feed card it reads
as fragments run together.

This keeps only what reads as a sentence about something: whole sentences, long enough to say something, not
headlines or navigation, not a repeat of the title, not a newsletter or cookie notice. It never rewrites a
sentence and never invents one; if nothing qualifies it returns "" and the card shows just its title and source.
"""

from __future__ import annotations

import re

_MAX_CHARS = 260
_MIN_WORDS = 7
_MIN_CJK_CHARS = 14

_IMAGE_RE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_LINK_RE = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_LINK_LEFTOVER_RE = re.compile(r"\[\]\(?|\]\(|\(\)")
_STITCH_RE = re.compile(r"\[\s*(?:\.\.\.|…)\s*\]")
_RELATIVE_TIME_RE = re.compile(
    r"\b(?:\d+|an?)\s+(?:seconds?|minutes?|mins?|hours?|hrs?|days?|weeks?|months?|years?)\s+ago\b",
    re.IGNORECASE,
)
_DATE_RE = re.compile(
    r"\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
    r"\.?\s+\d{1,2}(?:st|nd|rd|th)?,?\s+(?:\d{4})?(?:,?\s*\d{1,2}:\d{2}\s*(?:[AP]\.?M\.?)?)?",
    re.IGNORECASE,
)
_BYLINE_RE = re.compile(r"^\s*(?:by|written by|posted by|source:)\s*[A-Z]", re.IGNORECASE)
_BOILERPLATE_RE = re.compile(
    r"company logo|skip to (?:main )?content|newsletter|sign up|subscribe|cookie|privacy policy|all rights reserved|"
    r"click here|read more|read the full|advertisement|follow (?:us|patch|.{0,30}) on|email (?:it )?to|"
    r"log ?in|share (?:on|this)|get more .{0,40}delivered|more from\b|related (?:articles|stories)|"
    r"visit us|what'?s on\b|view videos|rumble|now in \d+ communities|"
    r"opt out|personal information|do not sell|your privacy|terms of (?:use|service)|accept (?:all )?cookies|"
    r"by continuing|by using this (?:site|website)",
    re.IGNORECASE,
)
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?。！？])\s+|(?<=[。！？])")
_CJK_RE = re.compile(r"[぀-ヿ㐀-䶿一-鿿가-힯]")
_WORD_RE = re.compile(r"[^\W\d_][\w'’-]*", re.UNICODE)


def _clean_markup(raw: str) -> str:
    text = _IMAGE_RE.sub(" ", raw)
    text = _LINK_RE.sub(r"\1", text)
    text = _LINK_LEFTOVER_RE.sub(" ", text)
    return _STITCH_RE.sub("\n", text)


def _looks_like_a_heading(sentence: str) -> bool:
    """Title Case with no sentence in it: a headline, a menu, a row of nav labels."""
    words = _WORD_RE.findall(sentence)
    capitalized = sum(1 for w in words if w[:1].isupper())
    return len(words) >= 5 and capitalized / len(words) >= 0.75


def _is_a_sentence_worth_showing(sentence: str, title: str) -> bool:
    if _BOILERPLATE_RE.search(sentence) or _BYLINE_RE.match(sentence):
        return False
    # A whole sentence: it ends where a sentence ends, and was not cut off by the search engine ("... and...").
    if sentence.endswith(("...", "…")) or not re.search(r"[.!?。！？][\"'”’)]*$", sentence):
        return False
    cjk = len(_CJK_RE.findall(sentence))
    if cjk >= _MIN_CJK_CHARS:
        pass
    elif cjk == 0 and len(_WORD_RE.findall(sentence)) >= _MIN_WORDS:
        pass
    else:
        return False
    letters = sum(ch.isalpha() for ch in sentence)
    if letters < 0.6 * len(sentence):
        return False  # mostly digits and symbols: a table row, a price list
    if _looks_like_a_heading(sentence):
        return False
    folded, folded_title = sentence.lower().strip(" .…"), title.lower().strip(" .…")
    if folded_title:
        shorter, longer = sorted((folded, folded_title), key=len)
        # A repeat of the title, or the title with a little added; a sentence that merely contains a short title is fine.
        if shorter in longer and len(shorter) >= 0.7 * len(longer):
            return False
    return True


def readable_description(raw: str, title: str = "", max_chars: int = _MAX_CHARS) -> str:
    """The first whole sentences of `raw` that read as a description, at most `max_chars`, or "" if none do."""
    if not raw:
        return ""
    chosen: list[str] = []
    length = 0
    for line in _clean_markup(raw).splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue  # a heading line is a headline (usually another story's), not a description
        # A timestamp sits between two unrelated items on a page, so it is a break, not something to delete.
        broken = _DATE_RE.sub("\n", _RELATIVE_TIME_RE.sub("\n", stripped))
        for piece in broken.splitlines():
            line_text = re.sub(r"\s+", " ", piece).strip(" *>|-–•·\t")
            for sentence in _SENTENCE_SPLIT_RE.split(line_text):
                sentence = sentence.strip()
                if not _is_a_sentence_worth_showing(sentence, title):
                    continue
                if chosen and length + len(sentence) + 1 > max_chars:
                    return " ".join(chosen)
                if not chosen and len(sentence) > max_chars:
                    cut = sentence[:max_chars].rsplit(" ", 1)[0].rstrip(",;:")
                    return cut + "…"
                chosen.append(sentence)
                length += len(sentence) + 1
                if len(chosen) == 2:
                    return " ".join(chosen)
    return " ".join(chosen)
