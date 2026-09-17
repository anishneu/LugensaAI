import pytest

from app.verification.contradiction import claims_contradict


@pytest.mark.parametrize(
    "text_a,text_b",
    [
        ("This neighborhood is very safe at night.", "This is a dangerous area after dark."),
        ("This is a low crime neighborhood.", "Residents report a high crime area nearby."),
        ("Rent here is quite affordable for students.", "Housing costs are expensive compared to nearby towns."),
        ("The streets are well-lit at night.", "Several blocks are poorly lit after dark."),
    ],
)
def test_detects_clear_contradictions(text_a, text_b):
    assert claims_contradict(text_a, text_b)


@pytest.mark.parametrize(
    "text_a,text_b",
    [
        ("This neighborhood is very safe at night.", "Rent here is affordable for students."),
        ("The streets are well-lit at night.", "The streets are well-lit at night."),
        ("Public transit is convenient.", "The area has many good restaurants."),
    ],
)
def test_unrelated_or_agreeing_claims_are_not_contradictions(text_a, text_b):
    assert not claims_contradict(text_a, text_b)
