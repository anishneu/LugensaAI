"""The wording/number checks that stop a real citation from vouching for an invented claim."""

from datetime import datetime, timezone

from app.core.config import AgentConfig
from app.models.claim import Claim, ClaimStatus
from app.models.evidence import Evidence, SourceType
from app.verification.support import numbers_in, untraceable_sentences, wording_support
from app.verification.verifier import EvidenceBasedClaimVerifier

_GOOGLE_TEXT = (
    "Google Maps lists Suiran with an average rating of 3.9 out of 5 from 384 reviews. Diners like the fresh "
    "seafood bowls with large sashimi pieces. Other reviews mention there can be long wait times."
)


def _evidence(text: str = _GOOGLE_TEXT) -> Evidence:
    return Evidence(
        evidence_id="e1",
        source_url="https://maps.example/suiran",
        source_title="Google Maps listing for Suiran",
        source_type=SourceType.REVIEW_AGGREGATOR,
        retrieved_at=datetime.now(timezone.utc),
        location_scope="Kurume, Fukuoka",
        text=text,
        topic="food",
        relevance_score=1.0,
    )


def _verify(text: str, check_wording: bool = True) -> Claim:
    claim = Claim(
        claim_id="c1", text=text, claim_type="food", supporting_evidence_ids=["e1"], check_wording=check_wording
    )
    [verified] = EvidenceBasedClaimVerifier().verify([claim], {"e1": _evidence()}, AgentConfig())
    return verified


def test_numbers_ignore_thousands_separators():
    assert numbers_in("1,200 reviews, rated 3.9 of 5") == {"1200", "3.9", "5"}


def test_a_faithful_paraphrase_with_matching_figures_is_supported():
    claim = _verify("Suiran has a 3.9 out of 5 rating from 384 reviews, and some reviews mention long wait times.")

    assert claim.status == ClaimStatus.SUPPORTED and not claim.limitations


def test_an_invented_figure_on_a_real_citation_is_rejected():
    claim = _verify("Suiran has a 4.7 out of 5 rating from 384 reviews.")

    assert claim.status == ClaimStatus.INSUFFICIENT_EVIDENCE
    assert any("4.7" in limitation for limitation in claim.limitations)


def test_invented_wording_on_a_real_citation_is_rejected():
    claim = _verify("Suiran offers a rooftop terrace with live jazz performances every weekend evening.")

    assert claim.status == ClaimStatus.INSUFFICIENT_EVIDENCE
    assert any("wording is not found" in limitation for limitation in claim.limitations)


def test_claims_not_written_by_a_model_are_not_wording_checked():
    """Fixture claims are pre-annotated, not free text, so the check doesn't apply."""
    claim = _verify("Suiran offers a rooftop terrace with live jazz performances.", check_wording=False)

    assert claim.status == ClaimStatus.SUPPORTED


def test_wording_support_reports_the_overlap_and_missing_figures():
    result = wording_support("Rated 4.7 stars with fresh seafood bowls.", [_GOOGLE_TEXT])

    assert result.missing_numbers == ("4.7",)
    assert 0 < result.overlap < 1


def test_overview_sentence_with_no_source_is_flagged_and_sourced_ones_are_not():
    text = (
        "Diners like the fresh seafood bowls with large sashimi pieces. "
        "It is a suitable destination for tourists seeking an authentic upscale dining experience."
    )

    flagged = untraceable_sentences(text, [_GOOGLE_TEXT])

    assert flagged == ["It is a suitable destination for tourists seeking an authentic upscale dining experience."]


def test_one_long_page_cannot_vouch_for_a_sentence_by_scattering_its_words():
    """Each sentence is judged against ONE source at a time, not the pooled words of all of them."""
    a = "Diners praise seafood bowls sashimi."
    b = "Tourists visit temple gardens autumn."
    # Pooled, the two sources cover 8 of its 9 content words; individually, 4 of 9 each.
    sentence = "Tourists praise temple seafood gardens sashimi bowls autumn lovely."

    assert untraceable_sentences(sentence, [a, b]) == [sentence]


def test_a_figure_in_a_sentence_must_appear_in_some_source():
    flagged = untraceable_sentences(
        "Suiran has a rating of 4.8 out of 5 from many reviews of seafood bowls.", [_GOOGLE_TEXT]
    )

    assert len(flagged) == 1


def test_very_short_sentences_are_not_judged():
    assert untraceable_sentences("Here is the summary.", [_GOOGLE_TEXT]) == []


# ---- non-Latin scripts and numerals (the checks must not be English-only)


def test_words_in_other_scripts_are_not_discarded():
    from app.verification.support import content_tokens

    assert {"москва", "арбат"} <= content_tokens("Арбат — улица в Москве, Москва")
    assert "翠藍" in content_tokens("店名は 翠藍 です")
    assert content_tokens("東京 is big") >= {"東京"}  # two-character CJK words are whole words


def test_figures_in_other_numeral_systems_match_the_same_figure_in_ascii():
    assert numbers_in("評価 ３．９ 、 レビュー ３８４件") >= {"384"}
    assert numbers_in("تقييم ٣٨٤ مراجعة") == {"384"}
    assert numbers_in("३८४ समीक्षाएँ") == {"384"}


def test_an_english_claim_is_checked_against_a_source_written_in_another_script_by_its_figures():
    source = "翠藍 のレビュー ３８４件、評価 ３.９"

    assert wording_support("Suiran has 384 reviews.", [source]).missing_numbers == ()
    assert wording_support("Suiran has 999 reviews.", [source]).missing_numbers == ("999",)
