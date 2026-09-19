"""Machine translation of foreign-language evidence into English.

A place in Japan, Germany, or Russia is mostly written about in that country's
language, and a reader who only knows English can't use a passage they can't
read. Evidence text and titles are therefore translated to English *before*
the rest of the pipeline sees them — which also means relevance filtering,
retrieval scoring, claim extraction, and synthesis all work on English.

Translation is done locally with Argos Translate: free, no API key, nothing
about the research leaves the machine. (Google Translate's unofficial endpoint
would be higher quality but is an undocumented scrape; hosted APIs need keys
and billing.) Language packs (~100MB each) download on first use per language.

Honesty rules, same as the rest of the project:
- A translation is never presented as the source's own words. The original
  passage and title are kept in `Evidence.metadata` and the UI labels
  anything translated as machine-translated, with the original one click away.
- If translation is unavailable (packages missing, pack download failed), the
  original text is kept as-is and flagged as untranslated — never silently
  dropped, never faked.
"""

from __future__ import annotations

import threading
import time
from abc import ABC, abstractmethod
from functools import lru_cache

from app.models.evidence import Evidence

META_LANGUAGE = "language"
META_ORIGINAL_TITLE = "original_title"
META_ORIGINAL_TEXT = "original_text"
META_TRANSLATED_BY = "translated_by"

_MIN_DETECTABLE_CHARS = 20
_MIN_DETECTION_CONFIDENCE = 0.90
_RETRY_FAILED_PACK_AFTER_SECONDS = 300
_CACHE_SIZE = 2048

# langdetect distinguishes Chinese variants; Argos ships one Chinese pack.
_CODE_ALIASES = {"zh-cn": "zh", "zh-tw": "zh"}


class Translator(ABC):
    @abstractmethod
    def detect(self, text: str) -> str | None:
        """ISO 639-1 code of the text's language, or None if it can't be told confidently."""

    @abstractmethod
    def translate_to_english(self, text: str, source_language: str) -> str | None:
        """English translation, or None if translation isn't available right now."""


class ArgosTranslator(Translator):
    """Offline translation via Argos Translate + langdetect.

    Both imports are lazy so the rest of the app (and the test suite) never
    needs them installed — see `translation_enabled()` in `app/core/config.py`.
    One shared lock guards language-pack installation and translation: the
    research agent searches topics on a thread pool, and neither the pack
    installer nor a half-loaded model is safe to race.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._ready: set[str] = set()
        self._failed_at: dict[str, float] = {}
        self._cache: dict[tuple[str, str], str] = {}

    def detect(self, text: str) -> str | None:
        if len(text.strip()) < _MIN_DETECTABLE_CHARS:
            return None
        from langdetect import DetectorFactory, detect_langs
        from langdetect.lang_detect_exception import LangDetectException

        DetectorFactory.seed = 0  # langdetect is otherwise nondeterministic
        try:
            best = detect_langs(text)[0]
        except LangDetectException:
            return None
        if best.prob < _MIN_DETECTION_CONFIDENCE:
            return None
        return _CODE_ALIASES.get(best.lang, best.lang)

    def _ensure_pack(self, source_language: str) -> bool:
        if source_language in self._ready:
            return True
        failed_at = self._failed_at.get(source_language)
        if failed_at is not None and time.monotonic() - failed_at < _RETRY_FAILED_PACK_AFTER_SECONDS:
            return False

        try:
            import argostranslate.package as package
            import argostranslate.translate as argos

            installed = argos.get_installed_languages()
            source = next((lang for lang in installed if lang.code == source_language), None)
            english = next((lang for lang in installed if lang.code == "en"), None)
            if not (source and english and source.get_translation(english)):
                package.update_package_index()
                match = next(
                    (
                        p
                        for p in package.get_available_packages()
                        if p.from_code == source_language and p.to_code == "en"
                    ),
                    None,
                )
                if match is None:
                    self._failed_at[source_language] = time.monotonic()
                    return False
                package.install_from_path(match.download())
        except Exception:  # noqa: BLE001 - network/disk/package errors all mean "not available now"
            self._failed_at[source_language] = time.monotonic()
            return False

        self._ready.add(source_language)
        return True

    def translate_to_english(self, text: str, source_language: str) -> str | None:
        # Only successes are cached: a failure (no network for the pack
        # download, say) must be retried later, not remembered forever.
        key = (source_language, text)
        with self._lock:
            cached = self._cache.get(key)
            if cached is not None:
                return cached
            if not self._ensure_pack(source_language):
                return None
            try:
                import argostranslate.translate as argos

                result = argos.translate(text, source_language, "en") or None
            except Exception:  # noqa: BLE001
                return None
            if result:
                if len(self._cache) >= _CACHE_SIZE:
                    self._cache.pop(next(iter(self._cache)))
                self._cache[key] = result
            return result


@lru_cache(maxsize=1)
def default_translator() -> Translator:
    """One shared instance: the agent is rebuilt per request, but loaded
    translation models and the translation cache should outlive a request."""
    return ArgosTranslator()


def translate_evidence(items: list[Evidence], translator: Translator, max_translations: int = 20) -> None:
    """Translate foreign-language items to English in place.

    Sets `metadata["language"]` on every item whose language could be
    determined. Translated items keep their originals under `original_title`
    / `original_text`; items that couldn't be translated (over the cap, or the
    translator was unavailable) keep their text and carry only the language,
    which the UI reads as "not translated".
    """
    translated = 0
    for item in items:
        language = translator.detect(f"{item.source_title}. {item.text}")
        if language is None:
            continue
        item.metadata[META_LANGUAGE] = language
        if language == "en" or translated >= max_translations:
            continue

        new_text = translator.translate_to_english(item.text, language)
        if not new_text:
            continue
        new_title = translator.translate_to_english(item.source_title, language)

        item.metadata[META_ORIGINAL_TEXT] = item.text
        item.metadata[META_ORIGINAL_TITLE] = item.source_title
        item.metadata[META_TRANSLATED_BY] = "machine translation (Argos Translate)"
        item.text = new_text
        if new_title:
            item.source_title = new_title
        translated += 1
