"""Turning a search snippet (markup, timestamps, navigation) into a description that reads as sentences."""

from app.tools.descriptions import readable_description

_TITLE = "England completes series sweep over Sri Lanka"


def test_whole_sentences_are_kept_and_at_most_two():
    raw = (
        "Manchester Fashion Week is leading this effort across the region. It returned under new ownership in 2025 "
        "after a decade-long hiatus. A third sentence should not appear in a short card."
    )

    assert readable_description(raw, "Fashion") == (
        "Manchester Fashion Week is leading this effort across the region. "
        "It returned under new ownership in 2025 after a decade-long hiatus."
    )


def test_markdown_links_and_images_leave_their_text_and_no_brackets():
    raw = "![logo](x.png) The [city council](https://example.org/a) has approved the new tram line through the centre. []( []("

    assert readable_description(raw) == "The city council has approved the new tram line through the centre."


def test_headline_lines_timestamps_and_bylines_are_not_descriptions():
    raw = (
        "8 hours ago\n\n## NHL star says he is 'for peace and love' after appearing in an ad\n\n13 hours ago\n\n"
        "By The Associated Press\n\nSeptember 19, 2026, 12:54 PM\n\n"
        "England reclaimed top spot in the world ranking by thrashing Sri Lanka by eight wickets in Manchester."
    )

    assert readable_description(raw, _TITLE) == (
        "England reclaimed top spot in the world ranking by thrashing Sri Lanka by eight wickets in Manchester."
    )


def test_a_timestamp_between_two_stories_separates_them_instead_of_gluing_them_together():
    raw = "14 hours ago Claim back up to £250 in work-from-home tax relief before time runs out 18 hours ago Find the latest news"

    assert readable_description(raw) == ""


def test_a_sentence_the_search_engine_cut_off_is_not_shown():
    raw = "Worship & Music Visit us company logo What's On Manchester Cathedral is a thriving, diverse and..."

    assert readable_description(raw) == ""


def test_newsletter_cookie_and_navigation_text_is_dropped():
    raw = (
        "Get more local news delivered straight to your inbox. Sign up for free newsletters and alerts today. "
        "We use cookies to improve your experience on this website and for advertising. "
        "The council says the road will reopen to traffic on Friday after weeks of repairs."
    )

    assert readable_description(raw) == "The council says the road will reopen to traffic on Friday after weeks of repairs."


def test_a_sentence_that_only_repeats_the_title_is_skipped():
    raw = "England completes series sweep over Sri Lanka. The hosts won by eight wickets to take the series three-nil."

    assert readable_description(raw, "England completes series sweep over Sri Lanka") == (
        "The hosts won by eight wickets to take the series three-nil."
    )


def test_a_row_of_title_case_labels_is_navigation_not_a_sentence():
    assert readable_description("Home News Sport Weather Travel Entertainment Video Contact Us.") == ""


def test_a_very_long_sentence_is_cut_at_a_word_with_an_ellipsis_not_mid_word():
    raw = "The council " + "has been discussing the proposal " * 20 + "today."

    out = readable_description(raw, max_chars=100)

    assert out.endswith("…") and len(out) <= 101 and not out[:-1].endswith(" ")


def test_chinese_sentences_are_kept_by_length_not_word_count():
    raw = "台北101是台灣著名的地標，觀景台可以俯瞰整個台北市的夜景。"

    assert readable_description(raw) == raw


def test_nothing_readable_gives_an_empty_string_never_an_invented_one():
    assert readable_description("") == "" and readable_description("## Heading only") == ""


def test_a_search_result_keeps_a_readable_description_beside_its_raw_snippet(harvard_square):
    from app.tools.tavily_tools import TavilyWebSearchTool
    from tests.test_tavily_tools import FakeTavilyClient, _topic

    junk = (
        "Skip to main content Sign Up Log In. 8 hours ago ## Another story entirely. "
        "Harvard Square in Cambridge, Massachusetts is busy on weekends and easy to reach by the Red Line. "
        "Sign up for our newsletter."
    )
    client = FakeTavilyClient(results=[{"url": "https://example.org/harvard", "title": "Harvard Square guide", "content": junk}])

    found = TavilyWebSearchTool(client=client).search(harvard_square, _topic("housing"))

    assert found[0].metadata["description"] == (
        "Harvard Square in Cambridge, Massachusetts is busy on weekends and easy to reach by the Red Line."
    )
