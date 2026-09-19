from app.synthesis.excerpt import best_excerpt, query_terms

_NAV = "About the site FAQ Japanese culture guide. Sign in. Rewards. Browse by area. "
_REVIEWS = (
    "The flat white here is rich and smooth and the beans are roasted in house. "
    "Staff were friendly but the cafe gets very crowded on weekends. "
    "Prices are a little high for a coffee, though the cheesecake is worth it. "
)


def test_short_text_is_returned_untouched():
    assert best_excerpt("short review", {"coffee"}, 400) == "short review"


def test_picks_the_passage_that_answers_the_question_not_the_page_navigation():
    """Regression: the model only saw the first few hundred characters of a
    page, which for a review site is navigation, so answers came out generic."""
    page = _NAV * 6 + _REVIEWS + _NAV * 6

    excerpt = best_excerpt(page, query_terms("How is the coffee and what are the customer reviews?"), 260)

    assert "flat white" in excerpt
    assert "Sign in" not in excerpt
    assert excerpt.startswith("…")


def test_with_no_signal_it_reads_from_the_start():
    page = "Alpha beta gamma. " * 60

    assert best_excerpt(page, {"zebra"}, 100).startswith("Alpha")


def test_stays_within_the_limit_and_only_selects_source_words():
    page = _NAV * 20 + _REVIEWS * 20

    excerpt = best_excerpt(page, query_terms("coffee reviews"), 300)

    assert len(excerpt) <= 302
    assert set(excerpt.replace("…", "").split()) <= set(page.split())
