"""Which language a place is written about in, and what the people there call it.

An English query only finds English pages. Measured on 15 places worldwide,
14 of 15 came back with English-only sources, and for a restaurant in Kurume,
Japan the English search returned five pages about a *different* hotel in
Kyoto while the same search in Japanese returned Tabelog, Retty and Yahoo Japan
reviews of the right restaurant. Searching in the local language, and matching
pages on the place's native-script name, is what makes results real outside the
English-speaking world.

Two lookups, both free:

* the country's main written language, from a reverse geocode (OpenStreetMap
  Nominatim) and a curated country -> language table below;
* the place's native name and its city's native name: Nominatim in that
  language for an area, Google Places in that language for a business.

Only languages the free translator (Argos) can read back to English are listed.
A page in a language we cannot translate could not pass the relevance filters
or the wording checks, so searching for it would only waste queries. Countries
where English is the everyday web language (US, UK, Australia, India, Nigeria,
Kenya, Singapore, ...) are deliberately absent: English search already works
there. Where a country is genuinely mixed (Belgium, Switzerland) the table
picks one or none rather than guess.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass

from app.models.location import Location
from app.tools.base import ToolExecutionError
from app.tools.google_places_tool import GooglePlacesTool
from app.tools.nominatim_tool import NominatimClient

PRIMARY_LANGUAGE: dict[str, str] = {
    # Europe
    "AL": "sq", "AT": "de", "AZ": "az", "BG": "bg", "BY": "ru", "CH": "de", "CY": "el", "CZ": "cs",
    "DE": "de", "DK": "da", "EE": "et", "ES": "es", "FI": "fi", "FR": "fr", "GR": "el", "HU": "hu",
    "IT": "it", "LT": "lt", "LV": "lv", "MD": "ro", "NL": "nl", "NO": "nb", "PL": "pl", "PT": "pt",
    "RO": "ro", "RU": "ru", "SE": "sv", "SI": "sl", "SK": "sk", "UA": "uk",
    # Americas
    "AR": "es", "BO": "es", "BR": "pt", "CL": "es", "CO": "es", "CR": "es", "CU": "es", "DO": "es",
    "EC": "es", "GT": "es", "HN": "es", "HT": "fr", "MX": "es", "NI": "es", "PA": "es", "PE": "es",
    "PY": "es", "SV": "es", "UY": "es", "VE": "es",
    # Asia and the Middle East
    "AE": "ar", "BD": "bn", "BH": "ar", "CN": "zh", "HK": "zt", "ID": "id", "IL": "he", "IQ": "ar",
    "IR": "fa", "JO": "ar", "JP": "ja", "KG": "ky", "KR": "ko", "KW": "ar", "LB": "ar", "MO": "zt",
    "MY": "ms", "OM": "ar", "PK": "ur", "QA": "ar", "SA": "ar", "SY": "ar", "TH": "th", "TR": "tr",
    "TW": "zt", "VN": "vi", "YE": "ar",
    # Africa
    "CD": "fr", "CI": "fr", "DZ": "ar", "EG": "ar", "LY": "ar", "MA": "fr", "MG": "fr", "SN": "fr",
    "TN": "ar", "TZ": "sw",
}

LANGUAGE_NAMES: dict[str, str] = {
    "ar": "Arabic", "az": "Azerbaijani", "bg": "Bulgarian", "bn": "Bengali", "cs": "Czech", "da": "Danish",
    "de": "German", "el": "Greek", "es": "Spanish", "et": "Estonian", "fa": "Persian", "fi": "Finnish",
    "fr": "French", "he": "Hebrew", "hu": "Hungarian", "id": "Indonesian", "it": "Italian", "ja": "Japanese",
    "ko": "Korean", "ky": "Kyrgyz", "lt": "Lithuanian", "lv": "Latvian", "ms": "Malay", "nb": "Norwegian",
    "nl": "Dutch", "pl": "Polish", "pt": "Portuguese", "ro": "Romanian", "ru": "Russian", "sl": "Slovenian",
    "sk": "Slovak", "sq": "Albanian", "sv": "Swedish", "sw": "Swahili", "th": "Thai", "tr": "Turkish",
    "uk": "Ukrainian", "ur": "Urdu", "vi": "Vietnamese", "zh": "Simplified Chinese", "zt": "Traditional Chinese",
}

# Nominatim address keys that name the containing city, most specific first.
_CITY_KEYS = ("city", "town", "village", "municipality", "county")
_CACHE: dict[tuple, "LocalContext"] = {}
_CACHE_LOCK = threading.Lock()


@dataclass(frozen=True)
class LocalContext:
    country_code: str | None = None
    language: str | None = None  # None: English search is enough, or no readable local language
    local_name: str | None = None
    local_area: str | None = None


class LocaleResolver:
    """`client` and `google` are injectable so tests never touch the network."""

    def __init__(self, client: NominatimClient | None = None, google: GooglePlacesTool | None = None) -> None:
        self._client = client or NominatimClient()
        self._google = google

    def resolve(self, location: Location) -> LocalContext:
        if location.latitude is None or location.longitude is None:
            return LocalContext()
        key = (round(location.latitude, 3), round(location.longitude, 3), location.name.casefold(), self._google is not None)
        with _CACHE_LOCK:
            cached = _CACHE.get(key)
        if cached is not None:
            return cached

        english = self._client.reverse(location.latitude, location.longitude, "en")
        english_address = english.get("address") or {}
        country_code = (english_address.get("country_code") or "").lower() or None
        language = PRIMARY_LANGUAGE.get((country_code or "").upper())
        if language is None:
            return self._remember(key, LocalContext(country_code=country_code))

        local_address = self._client.reverse(location.latitude, location.longitude, language).get("address") or {}
        local_area = next(
            (local_address[k] for k in _CITY_KEYS if local_address.get(k) and english_address.get(k)), None
        )
        local_name = self._local_name(location, english_address, local_address, language)

        # A name that is identical in both languages (Paris) adds nothing to a query or a match.
        if local_area and local_area.casefold() == (location.city or "").casefold():
            local_area = None
        if local_name and local_name.casefold() == location.name.casefold():
            local_name = None
        return self._remember(
            key, LocalContext(country_code=country_code, language=language, local_name=local_name, local_area=local_area)
        )

    def _local_name(self, location: Location, english: dict, local: dict, language: str) -> str | None:
        if location.is_business:
            if self._google is None:
                return None
            try:
                return self._google.local_name(location.name, location.latitude, location.longitude, language)
            except ToolExecutionError:
                return None
        wanted = location.name.casefold()
        for key, value in english.items():
            if isinstance(value, str) and value.casefold() == wanted and local.get(key):
                return local[key]
        return None

    @staticmethod
    def _remember(key: tuple, context: LocalContext) -> LocalContext:
        with _CACHE_LOCK:
            _CACHE[key] = context
        return context
