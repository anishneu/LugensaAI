"""Separating the questions in a prompt from the context around them."""

import pytest

from app.planning.questions import split_prompt


def test_the_prompt_that_started_this_is_two_questions_and_one_statement_typed_with_a_question_mark():
    p = split_prompt("How is the university? I heard a grat deal about the university's coop program? How often do people gets coops?")

    assert p.questions == ["How is the university?", "How often do people gets coops?"]
    assert p.context == ["I heard a grat deal about the university's coop program?"]
    assert p.is_multi


def test_a_single_question_is_not_multi():
    p = split_prompt("Would this be a good place for a college student?")
    assert p.questions == ["Would this be a good place for a college student?"] and not p.is_multi and p.context == []


def test_context_before_a_question_is_kept_apart_from_it():
    p = split_prompt("I am moving there in June. Is it safe? How is the nightlife?")
    assert p.questions == ["Is it safe?", "How is the nightlife?"]
    assert p.context == ["I am moving there in June."]


def test_questions_on_separate_lines_are_separate():
    assert split_prompt("Is it walkable?\nAre there good cafes?").questions == ["Is it walkable?", "Are there good cafes?"]


@pytest.mark.parametrize(
    "text",
    ["", "   ", "Tell me about the area", "It is a nice place."],
)
def test_a_prompt_with_no_question_mark_has_no_questions_and_is_left_whole(text):
    assert split_prompt(text).questions == []


def test_an_abbreviation_does_not_end_a_sentence():
    p = split_prompt("Is it near St. Louis Street? Is the U.S. embassy close?")
    assert p.questions == ["Is it near St. Louis Street?", "Is the U.S. embassy close?"]


def test_full_width_question_marks_and_other_languages_count():
    p = split_prompt("この地域は安全ですか？ 食べ物はどうですか？")
    assert len(p.questions) == 2


def test_a_statement_that_merely_ends_in_a_question_mark_is_not_a_second_question():
    p = split_prompt("Is it safe? The area is quiet at night?")
    assert p.questions == ["Is it safe?"] and p.context == ["The area is quiet at night?"]
