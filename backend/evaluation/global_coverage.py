"""Check the data stages against places around the world and print a table.

    python -m evaluation.global_coverage            # all places
    python -m evaluation.global_coverage Tokyo Cairo  # only those whose label contains a word

For each place this answers, with real network calls and no language model: does the place
resolve to the right spot (checked against known coordinates), what does web search return and
in which languages, was it translated, how much does OpenStreetMap know about what is around it,
and what do Wikipedia and Wikivoyage add.

Needs TAVILY_API_KEY (search) and optionally GOOGLE_PLACES_API_KEY (place resolution). It uses
about one Tavily credit per topic searched, so a full run is roughly 30-45 credits, and it is
slow the first time because translation packs (~100MB per language) download on first use.

It is a probe, not a benchmark: it says whether each stage returns something plausible for
each place, not whether the final answer is right. Add places to PLACES to cover your own.
"""

from __future__ import annotations

import math
import sys
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.agents.factory import build_default_agent  # noqa: E402
from app.core.config import search_enabled  # noqa: E402
from app.planning.planner import KeywordResearchPlanner  # noqa: E402
from app.tools.base import ToolExecutionError  # noqa: E402
from app.tools.locale import LocaleResolver  # noqa: E402
from app.tools.overpass_tool import OverpassNearbyTool  # noqa: E402
from app.tools.wiki_tool import WikiContextTool  # noqa: E402

QUESTION = "What is it like to live in or visit this place? Is it safe, and what is there to do?"


@dataclass(frozen=True)
class Place:
    label: str
    typed: str  # exactly what a user might type, in their own script
    latitude: float  # where it really is, to check the resolved pin against
    longitude: float
    tolerance_km: float


PLACES = [
    Place("Tokyo neighborhood", "Shibuya, Tokyo", 35.6580, 139.7016, 3),
    Place("Paris neighborhood", "Le Marais, Paris", 48.8575, 2.3622, 3),
    Place("Berlin neighborhood", "Kreuzberg, Berlin", 52.4986, 13.4030, 4),
    Place("Moscow (Cyrillic)", "Арбат, Москва", 55.7495, 37.5919, 4),
    Place("Cairo neighborhood", "Zamalek, Cairo", 30.0626, 31.2197, 4),
    Place("Nairobi neighborhood", "Westlands, Nairobi", -1.2676, 36.8108, 4),
    Place("Lagos neighborhood", "Victoria Island, Lagos", 6.4281, 3.4219, 5),
    Place("Mumbai neighborhood", "Bandra, Mumbai", 19.0596, 72.8295, 5),
    Place("Sao Paulo neighborhood", "Vila Madalena, São Paulo", -23.5534, -46.6911, 4),
    Place("Bangkok road", "Sukhumvit, Bangkok", 13.7380, 100.5610, 12),
    Place("Seoul (Hangul)", "홍대, 서울", 37.5563, 126.9237, 4),
    Place("Sydney beach", "Bondi Beach, Sydney", -33.8908, 151.2743, 3),
    Place("Small town", "Chefchaouen, Morocco", 35.1688, -5.2636, 5),
    Place("Business abroad", "Cafe de Flore, Paris", 48.8541, 2.3326, 1),
    Place("Remote/small", "Reykjavik city centre", 64.1466, -21.9426, 4),
    Place("Small business, Japan", "8JG8+44 Kurume", 33.3253, 130.6154, 1),
]


@dataclass
class Row:
    place: Place
    resolved: str = ""
    error_km: float | None = None
    language: str | None = None
    local_name: str | None = None
    is_business: bool = False
    web_english: int = 0
    web_local: int = 0
    languages: Counter = field(default_factory=Counter)
    translated: int = 0
    domains: list[str] = field(default_factory=list)
    osm_places: int | str = 0
    wiki_items: int | str = 0
    seconds: float = 0.0
    problem: str = ""

    @property
    def ok(self) -> bool:
        return self.error_km is not None and self.error_km <= self.place.tolerance_km


def _km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    h = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(h))


def probe(place: Place, agent, planner: KeywordResearchPlanner, locale: LocaleResolver) -> Row:
    row = Row(place)
    started = time.time()
    try:
        location = agent.location_resolver.resolve(place.typed)
    except Exception as exc:  # noqa: BLE001 - a probe reports every failure, it doesn't stop on one
        row.problem = f"could not resolve: {type(exc).__name__}"
        return row
    row.resolved = f"{location.name}, {location.city or '-'}, {location.country or '-'}"
    row.error_km = round(_km(location.latitude, location.longitude, place.latitude, place.longitude), 1)
    row.is_business = location.is_business

    try:
        context = locale.resolve(location)
        location = location.model_copy(update={
            "language": context.language, "local_name": context.local_name, "local_area": context.local_area,
        })
        row.language, row.local_name = context.language, context.local_name
    except ToolExecutionError:
        pass

    plan = planner.plan(location, QUESTION)
    if location.language:
        from app.planning.local_queries import RuleBasedLocalQueryWriter

        for topic_id, query in RuleBasedLocalQueryWriter().write(location, plan).items():
            next(t for t in plan.topics if t.topic_id == topic_id).local_queries = [query]

    domains: Counter = Counter()
    for topic in plan.topics[:2]:
        try:
            found = agent.web_search_tool.search(location, topic)
        except ToolExecutionError:
            continue
        for item in found:
            domains[urlparse(item.source_url).netloc.removeprefix("www.")] += 1
            lang = item.metadata.get("language")
            if lang:
                row.languages[lang] += 1
            if item.metadata.get("original_text"):
                row.translated += 1
            if lang and lang != "en":
                row.web_local += 1
            else:
                row.web_english += 1
    row.domains = [d for d, _ in domains.most_common(3)]

    try:
        row.osm_places = sum(g.total for g in OverpassNearbyTool().nearby(location.latitude, location.longitude, 600).groups)
    except ToolExecutionError:
        row.osm_places = "unavailable"
    try:
        row.wiki_items = len(WikiContextTool().lookup(location, QUESTION, plan.topics[0].topic_id))
    except ToolExecutionError:
        row.wiki_items = "unavailable"
    row.seconds = round(time.time() - started, 1)
    return row


def _print(rows: list[Row]) -> None:
    print(f"{'place':24} {'pin':5} {'km':>5} {'lang':4} {'native name':10} {'en':>3} {'local':>5} {'osm':>5} {'wiki':>4}  resolved")
    for r in rows:
        pin = "ok" if r.ok else "OFF" if r.error_km is not None else "FAIL"
        print(
            f"{r.place.label[:24]:24} {pin:5} {r.error_km if r.error_km is not None else '-':>5} "
            f"{(r.language or '-'):4} {(r.local_name or '-')[:10]:10} {r.web_english:>3} {r.web_local:>5} "
            f"{r.osm_places!s:>5} {r.wiki_items!s:>4}  {r.resolved or r.problem}"
        )
    good = sum(1 for r in rows if r.ok)
    print(f"\npins within tolerance: {good}/{len(rows)}")
    print(f"places with any non-English web source: {sum(1 for r in rows if r.web_local)}/{len(rows)}")


def main(argv: list[str]) -> int:
    if not search_enabled():
        print("TAVILY_API_KEY is not set; nothing to probe.")
        return 1
    chosen = [p for p in PLACES if not argv or any(word.lower() in p.label.lower() for word in argv)]
    agent = build_default_agent()
    locale = LocaleResolver(google=agent.place_profile_tool)
    rows = []
    for place in chosen:
        row = probe(place, agent, KeywordResearchPlanner(), locale)
        rows.append(row)
        print(f"  ... {place.label}: {'ok' if row.ok else 'check'} ({row.seconds}s)", flush=True)
    print()
    _print(rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
