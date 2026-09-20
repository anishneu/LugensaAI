from datetime import datetime, timezone

from app.models.evidence import Evidence, SourceType
from app.tools.tavily_tools import TavilyLiveFeedTool, TavilyWebSearchTool
from app.tools.translation import (
    META_LANGUAGE,
    META_ORIGINAL_TEXT,
    META_ORIGINAL_TITLE,
    Translator,
)
from app.tools.translation import translate_evidence
from tests.test_tavily_tools import FakeTavilyClient, _topic

_JAPANESE_TEXT = "東京湾潮見プリンスホテルは観光に便利な立地です。"
_JAPANESE_TITLE = "潮見プリンスホテル 口コミ"


class FakeTranslator(Translator):
    """Detects by script and 'translates' from a fixed phrasebook."""

    def __init__(self, available: bool = True) -> None:
        self.available = available
        self.translate_calls = 0

    def detect(self, text: str) -> str | None:
        if len(text.strip()) < 5:
            return None
        return "ja" if any("぀" <= ch <= "ヿ" or "一" <= ch <= "鿿" for ch in text) else "en"

    def translate_to_english(self, text: str, source_language: str) -> str | None:
        self.translate_calls += 1
        if not self.available:
            return None
        return {
            _JAPANESE_TEXT: "Tokyo Bay Shiomi Prince Hotel is conveniently located for sightseeing near Tokyo.",
            _JAPANESE_TITLE: "Shiomi Prince Hotel reviews",
        }.get(text, f"[en] {text}")


def _evidence(title: str, text: str) -> Evidence:
    return Evidence(
        evidence_id="e1",
        source_url="https://example.jp/a",
        source_title=title,
        source_type=SourceType.OTHER,
        retrieved_at=datetime.now(timezone.utc),
        location_scope="Koto, Tokyo",
        text=text,
        topic="reviews",
    )


def test_translates_foreign_text_and_keeps_the_original():
    item = _evidence(_JAPANESE_TITLE, _JAPANESE_TEXT)

    translate_evidence([item], FakeTranslator())

    assert item.text.startswith("Tokyo Bay Shiomi Prince Hotel")
    assert item.source_title == "Shiomi Prince Hotel reviews"
    assert item.metadata[META_LANGUAGE] == "ja"
    assert item.metadata[META_ORIGINAL_TEXT] == _JAPANESE_TEXT
    assert item.metadata[META_ORIGINAL_TITLE] == _JAPANESE_TITLE


def test_english_text_is_left_alone_and_never_translated():
    item = _evidence("Hotel reviews", "A perfectly ordinary English review of the hotel.")
    translator = FakeTranslator()

    translate_evidence([item], translator)

    assert item.text == "A perfectly ordinary English review of the hotel."
    assert META_ORIGINAL_TEXT not in item.metadata
    assert translator.translate_calls == 0


def test_untranslatable_text_is_kept_and_flagged_not_dropped_or_faked():
    item = _evidence(_JAPANESE_TITLE, _JAPANESE_TEXT)

    translate_evidence([item], FakeTranslator(available=False))

    assert item.text == _JAPANESE_TEXT
    assert item.metadata[META_LANGUAGE] == "ja"
    assert META_ORIGINAL_TEXT not in item.metadata


def test_translation_cap_leaves_the_rest_untranslated():
    items = [_evidence(_JAPANESE_TITLE, _JAPANESE_TEXT) for _ in range(3)]

    translate_evidence(items, FakeTranslator(), max_translations=1)

    assert sum(META_ORIGINAL_TEXT in item.metadata for item in items) == 1
    assert all(item.metadata[META_LANGUAGE] == "ja" for item in items)


def test_search_translates_before_the_relevance_filter(harvard_square):
    """A foreign page never spells the place the way the English query does;
    without translating first it would be judged off-topic on words it
    couldn't have used."""
    client = FakeTavilyClient(
        results=[
            {
                "url": "https://example.jp/a",
                "title": _JAPANESE_TITLE,
                "content": _JAPANESE_TEXT,
            }
        ]
    )
    class _Translator(FakeTranslator):
        def translate_to_english(self, text, source_language):
            if text == _JAPANESE_TEXT:
                return "A guide to Harvard Square and its hotels."
            return super().translate_to_english(text, source_language)

    evidence = TavilyWebSearchTool(client=client, translator=_Translator()).search(harvard_square, _topic())

    assert len(evidence) == 1
    assert "location_match" not in evidence[0].metadata  # matched on the translated text


def test_live_feed_translates_foreign_items(harvard_square):
    client = FakeTavilyClient(
        results=[
            {
                "url": "https://www.cambridgema.gov/news/ja",
                "title": _JAPANESE_TITLE,
                "content": _JAPANESE_TEXT,
                "published_date": "Wed, 16 Sep 2026 15:14:23 GMT",
            }
        ]
    )

    feed = TavilyLiveFeedTool(client=client, translator=FakeTranslator()).fetch(harvard_square)

    assert len(feed) == 1
    assert feed[0].metadata[META_ORIGINAL_TEXT] == _JAPANESE_TEXT
    assert feed[0].text.startswith("Tokyo Bay")


# ---- translation is CPU-bound (~11 ms/char measured), so it must be spent only where it matters


class _CountingTranslator(FakeTranslator):
    def __init__(self) -> None:
        super().__init__()
        self.translated_inputs: list[str] = []

    def translate_to_english(self, text, source_language):
        self.translated_inputs.append(text)
        return "translated"


def _foreign_item(n: int, text: str | None = None):
    from datetime import datetime, timezone

    from app.models.evidence import Evidence, SourceType

    return Evidence(
        evidence_id=f"e{n}", source_url=f"https://example.jp/{n}", source_title="日本語のタイトルです。テスト用",
        source_type=SourceType.OTHER, retrieved_at=datetime.now(timezone.utc), location_scope="x",
        text=text or ("これは日本語の長い文章です。" * 10), topic="food",
    )


def test_only_the_leading_part_of_a_long_passage_is_translated_but_the_whole_original_is_kept():
    translator = _CountingTranslator()
    item = _foreign_item(1, "これは日本語の文章です。" * 200)

    translate_evidence([item], translator)

    body = translator.translated_inputs[0]
    assert len(body) <= 700 and body.endswith("。")  # cut back to a sentence end
    assert item.metadata["original_text"] == "これは日本語の文章です。" * 200


def test_items_the_caller_rejects_are_never_translated():
    translator = _CountingTranslator()
    items = [_foreign_item(1), _foreign_item(2)]

    translate_evidence(items, translator, should_translate=lambda item: item.evidence_id == "e2")

    assert len(translator.translated_inputs) == 2  # e2's text and its title; e1 was skipped entirely
    assert "original_text" not in items[0].metadata and "original_text" in items[1].metadata


def test_the_translation_cap_is_respected():
    translator = _CountingTranslator()
    items = [_foreign_item(n) for n in range(5)]

    translate_evidence(items, translator, max_translations=2)

    assert sum("original_text" in i.metadata for i in items) == 2
