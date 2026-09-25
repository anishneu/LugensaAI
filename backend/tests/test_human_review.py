"""The blinded human review: the labels must hide the system, the scoring must unhide it, and bad ratings must be refused."""

import pytest

from evaluation.human_review import (
    LABELS,
    RatingError,
    SourceRef,
    blank_ratings,
    blinded_order,
    build_key,
    build_sheet,
    score_ratings,
)

SYSTEMS = ["A", "B", "PIPELINE"]
ANSWERS = {
    "case1": {"A": "Answer from the plain model.", "B": "Answer from the sources.", "PIPELINE": "Answer from the pipeline."},
    "case2": {"A": "Second plain.", "B": "Second sources.", "PIPELINE": "Second pipeline."},
}


def test_the_order_is_the_same_every_time_but_not_the_same_for_every_case():
    assert blinded_order("case1", SYSTEMS) == blinded_order("case1", list(reversed(SYSTEMS)))
    orders = {tuple(blinded_order(f"case{n}", SYSTEMS)) for n in range(40)}
    assert len(orders) > 1  # "A" is not always the same system


def test_every_case_maps_each_label_to_a_different_system():
    key = build_key(ANSWERS)
    for by_label in key.values():
        assert sorted(by_label) == sorted(LABELS) and sorted(by_label.values()) == sorted(SYSTEMS)


def test_the_sheet_shows_answers_and_sources_but_never_names_a_system():
    key = build_key(ANSWERS)
    sheet = build_sheet(
        {"case1": ("Harvard Square", "Is it safe?"), "case2": ("Kendall Square", "Is it fun?")},
        ANSWERS,
        {"case1": [SourceRef("A source title", "https://example.org/1", "what it says")]},
        key,
    )
    assert "### Answer A" in sheet and "### Answer B" in sheet and "### Answer C" in sheet
    assert "A source title (https://example.org/1) — what it says" in sheet
    assert "Answer from the pipeline." in sheet
    for name in ("PIPELINE", "plain model is", "system A", "baseline"):
        assert name not in sheet


def test_the_blank_ratings_file_has_a_row_per_answer():
    rows = blank_ratings(build_key(ANSWERS)).strip().split("\n")
    assert rows[0] == "case_id,answer,accuracy,usefulness,notes"
    assert len(rows) == 1 + 2 * 3


def test_ratings_are_unblinded_per_system():
    key = {"case1": {"A": "PIPELINE", "B": "A", "C": "B"}, "case2": {"A": "B", "B": "PIPELINE", "C": "A"}}
    csv_text = (
        "case_id,answer,accuracy,usefulness,notes\n"
        "case1,A,2,2,good\n"   # PIPELINE
        "case1,B,0,1,\n"       # A
        "case1,C,,,\n"         # skipped
        "case2,B,1,2,\n"       # PIPELINE
        "case2,A,1,1,\n"       # B
    )
    scored = score_ratings(csv_text, key)
    assert scored["PIPELINE"] == {"rated": 2, "mean_accuracy": 1.5, "mean_usefulness": 2.0, "rated_0_for_accuracy": 0}
    assert scored["A"] == {"rated": 1, "mean_accuracy": 0.0, "mean_usefulness": 1.0, "rated_0_for_accuracy": 1}
    assert scored["B"]["rated"] == 1


@pytest.mark.parametrize(
    "row",
    ["case1,A,3,1,", "case1,A,2,,", "case1,A,x,1,", "case9,A,1,1,", "case1,Z,1,1,"],
)
def test_a_rating_that_is_out_of_range_half_filled_or_for_nothing_is_refused_not_guessed_at(row):
    key = {"case1": {"A": "A", "B": "B", "C": "PIPELINE"}}
    with pytest.raises(RatingError):
        score_ratings("case_id,answer,accuracy,usefulness,notes\n" + row + "\n", key)


def test_an_unrated_sheet_scores_nothing():
    key = {"case1": {"A": "A", "B": "B", "C": "PIPELINE"}}
    assert score_ratings(blank_ratings(key), key) == {}
