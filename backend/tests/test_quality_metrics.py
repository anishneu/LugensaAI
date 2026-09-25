"""The evaluation's answer-quality metrics, on small texts whose right answers are obvious."""

from datetime import datetime, timezone

from app.models.claim import Claim, ClaimStatus
from app.models.evidence import Evidence, SourceType
from evaluation.quality_metrics import (
    citation_check,
    clean,
    sentence_grounding,
    states_a_limit,
    unsupported_specifics,
    word_count,
)

SOURCES = [
    "The Red Line subway stops at Harvard Square and runs to Alewife every few minutes, so getting around without a car is easy.",
    "Rents near Harvard Square are among the highest in Cambridge, often above 3200 dollars a month for a one bedroom apartment.",
]


def _evidence(evidence_id: str, text: str) -> Evidence:
    return Evidence(
        evidence_id=evidence_id, source_url=f"https://example.org/{evidence_id}", source_title="t", source_type=SourceType.OTHER,
        retrieved_at=datetime.now(timezone.utc), location_scope="Cambridge", text=text, topic="housing",
    )


def _claim(text: str, ids: list[str]) -> Claim:
    return Claim(claim_id="c", text=text, claim_type="fact", supporting_evidence_ids=ids, status=ClaimStatus.SUPPORTED)


def test_clean_removes_formatting_and_citation_markers():
    assert clean("**Rent** is high [1] and [2, 3] transit is good.") == "Rent is high  and  transit is good."


def test_a_sentence_a_source_backs_is_grounded_and_one_none_backs_is_not():
    answer = "The Red Line subway stops at Harvard Square and runs to Alewife every few minutes. The sushi restaurants here have won several national awards."

    g = sentence_grounding(answer, SOURCES)

    assert g.assessed == 2 and g.ungrounded == 1 and g.ungrounded_share == 0.5


def test_a_figure_that_no_source_contains_makes_its_sentence_ungrounded():
    answer = "Rents near Harvard Square are among the highest in Cambridge, often above 9999 dollars a month for a one bedroom apartment."

    assert sentence_grounding(answer, SOURCES).ungrounded == 1


def test_short_sentences_are_not_judged():
    assert sentence_grounding("Great place. Go there.", SOURCES).assessed == 0
    assert sentence_grounding("Great place. Go there.", SOURCES).ungrounded_share is None


def test_names_and_numbers_absent_from_every_source_are_counted_as_unsupported():
    answer = "The Red Line stops here. Harvard University is nearby and the Charles River Esplanade has 40 benches."

    s = unsupported_specifics(answer, SOURCES, allowed_texts=["Harvard Square, Cambridge"])

    assert "number 40" in s.unsupported
    assert "name Charles River Esplanade" in s.unsupported
    assert "name Red Line" not in s.unsupported  # it is in a source, and "The" is not part of the name
    assert s.total == 4  # the number 40 and three names


def test_the_places_own_name_and_the_question_do_not_count_against_an_answer():
    s = unsupported_specifics("Harvard Square is lively.", [], allowed_texts=["Harvard Square, Cambridge, MA"])

    assert s.unsupported == ()


def test_a_name_never_runs_across_a_line_break():
    s = unsupported_specifics("It is near Harvard Square\nRecent bike theft was reported.", ["Harvard Square Recent bike theft"], [])

    assert s.unsupported == () and s.total == 1  # only "Harvard Square" is a name; it is not joined to the next line


def test_a_single_capitalised_word_at_the_start_of_a_sentence_is_not_a_name():
    s = unsupported_specifics("Overall the area is busy. Students like it.", SOURCES, allowed_texts=[])

    assert s.total == 0 and s.unsupported_share is None


def test_a_citation_counts_only_if_the_evidence_exists_and_the_claim_is_worded_like_it():
    evidence = [_evidence("e1", SOURCES[0])]
    claims = [
        _claim("The Red Line subway stops at Harvard Square.", ["e1"]),      # cited and worded like it
        _claim("The area has a famous rooftop cinema festival.", ["e1"]),    # cited, but not what the source says
        _claim("Something else entirely happens here.", ["missing"]),        # cited evidence does not exist
        _claim("An uncited statement about the area.", []),
    ]

    check = citation_check(claims, evidence)

    assert (check.claims, check.with_real_citation, check.worded_like_its_source) == (4, 2, 1)


def test_an_answer_that_admits_what_it_lacks_is_recognised():
    assert states_a_limit("There is not enough information about nightlife here.")
    assert states_a_limit("A confident answer.", limitations=["Only one source was found."])
    assert not states_a_limit("It is a lively area with many restaurants.")


def test_word_count_ignores_formatting():
    assert word_count("**Two** words [1]") == 2
