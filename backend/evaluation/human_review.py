"""A person judging the answers, without knowing which system wrote which.

The automatic measures in `quality_metrics.py` only say whether an answer stays with its sources. They cannot say whether it is
right or useful. This makes that judging easy to do and hard to bias: every case's answers are shown under the letters A, B and C in
an order shuffled per case (so "A" is not always the same system), next to the sources the systems were given so statements can be
checked. Ratings go in a CSV; the key that says which letter was which system stays in a separate file until the ratings are scored.

Everything here is a plain function or a file write, so it is tested without a model.
"""

from __future__ import annotations

import csv
import io
import random
from dataclasses import dataclass

LABELS = ("A", "B", "C")

SCALE = """\
**Accuracy** (are the checkable statements right, judged against the sources and what you can verify?)
- 2 = every checkable statement is right, or is honestly hedged
- 1 = some statements are wrong, unsupported, or too vague to check
- 0 = mostly wrong, or made up

**Usefulness** (would this help someone deciding about this place?)
- 2 = clearly helpful and answers the question
- 1 = partly helpful, or answers a different question
- 0 = not helpful (empty, evasive, or off topic)

Leave a row blank to skip it. Judge each answer on its own, and do not try to guess which system wrote it.
"""


def blinded_order(case_id: str, systems: list[str]) -> list[str]:
    """The systems in a fixed, shuffled order for this case: the same every time it is asked, different from case to case."""
    order = sorted(systems)
    random.Random(f"lugensa-review:{case_id}").shuffle(order)
    return order


def build_key(answers: dict[str, dict[str, str]]) -> dict[str, dict[str, str]]:
    """case_id -> {label: system}, for every case that has answers."""
    return {case_id: dict(zip(LABELS, blinded_order(case_id, list(by_system)))) for case_id, by_system in answers.items()}


@dataclass(frozen=True)
class SourceRef:
    title: str
    url: str
    snippet: str


def build_sheet(
    cases: dict[str, tuple[str, str]],
    answers: dict[str, dict[str, str]],
    sources: dict[str, list[SourceRef]],
    key: dict[str, dict[str, str]],
) -> str:
    """Markdown to read while judging. `cases` maps case_id to (place, question). No system name appears in it."""
    lines = ["# Answer review", "", "Read each answer, check it against its sources, and put your ratings in `ratings.csv`.", "", SCALE]
    for case_id, by_label in key.items():
        place, question = cases[case_id]
        lines += ["", f"## {case_id}", "", f"**Place:** {place}", "", f"**Question:** {question}", "", "### Sources the systems were given", ""]
        refs = sources.get(case_id, [])
        lines += [f"{i}. {r.title} ({r.url}) — {r.snippet}" for i, r in enumerate(refs, start=1)] or ["_None._"]
        for label, system in by_label.items():
            lines += ["", f"### Answer {label}", "", answers[case_id][system].strip()]
    return "\n".join(lines) + "\n"


def blank_ratings(key: dict[str, dict[str, str]]) -> str:
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(["case_id", "answer", "accuracy", "usefulness", "notes"])
    for case_id, by_label in key.items():
        for label in by_label:
            writer.writerow([case_id, label, "", "", ""])
    return out.getvalue()


class RatingError(ValueError):
    pass


def score_ratings(ratings_csv: str, key: dict[str, dict[str, str]]) -> dict[str, dict[str, float | int | None]]:
    """Unblinds the ratings: per system, how many answers were rated and the mean accuracy and usefulness."""
    totals: dict[str, dict[str, list[int]]] = {}
    for n, row in enumerate(csv.DictReader(io.StringIO(ratings_csv)), start=2):
        accuracy, usefulness = (row.get("accuracy") or "").strip(), (row.get("usefulness") or "").strip()
        if not accuracy and not usefulness:
            continue
        case_id, label = (row.get("case_id") or "").strip(), (row.get("answer") or "").strip().upper()
        if case_id not in key or label not in key[case_id]:
            raise RatingError(f"row {n}: there is no answer {label!r} for case {case_id!r}")
        for name, value in (("accuracy", accuracy), ("usefulness", usefulness)):
            if value not in ("0", "1", "2"):
                raise RatingError(f"row {n}: {name} must be 0, 1 or 2 (or both left blank), not {value!r}")
        system = key[case_id][label]
        bucket = totals.setdefault(system, {"accuracy": [], "usefulness": []})
        bucket["accuracy"].append(int(accuracy))
        bucket["usefulness"].append(int(usefulness))
    result: dict[str, dict[str, float | int | None]] = {}
    for system, values in totals.items():
        n = len(values["accuracy"])
        result[system] = {
            "rated": n,
            "mean_accuracy": round(sum(values["accuracy"]) / n, 2),
            "mean_usefulness": round(sum(values["usefulness"]) / n, 2),
            "rated_0_for_accuracy": sum(1 for v in values["accuracy"] if v == 0),
        }
    return result
