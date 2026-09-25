"""The answer-quality cases: ten places and questions chosen to differ in what the free sources can reach.

Places are given as text and resolved once by OpenStreetMap when the evidence is collected (the resolved place is stored with it),
so a run never depends on a geocoder. Nothing here says what the right answer is; the metrics do not need to know.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class QualityCase:
    case_id: str
    place: str
    question: str
    kind: str
    is_business: bool = False


QUALITY_CASES: list[QualityCase] = [
    QualityCase("harvard_broad", "Harvard Square, Cambridge, MA", "Would this be a good place for a college student?", "broad question, well-covered place"),
    QualityCase("harvard_nightlife", "Harvard Square, Cambridge, MA", "What's the nightlife like around here?", "narrow question, well-covered place"),
    QualityCase("northern_quarter", "Northern Quarter, Manchester, UK", "Is this a good area to live in as a young professional?", "broad question, English-speaking city"),
    QualityCase("shibuya_safety", "Shibuya, Tokyo, Japan", "Is it safe here at night?", "safety question, non-English country"),
    QualityCase("gion_tourist", "Gion, Kyoto, Japan", "Is this a good area for a first-time tourist?", "tourism question, non-English country"),
    QualityCase("zhongshan_food", "Zhongshan District, Taipei, Taiwan", "What is the food scene like?", "narrow question, non-English country"),
    QualityCase("erfurt_weekend", "Altstadt, Erfurt, Germany", "Is this a good place for a weekend visit?", "smaller city, non-English country"),
    QualityCase("kurume_family", "Kurume, Fukuoka, Japan", "Is this a good place to raise a family?", "thinly covered place"),
    QualityCase("hunts_bank", "Hunts Bank, Manchester, UK", "Is it safe to walk here at night?", "obscure street, thin coverage"),
    QualityCase("tatte_cafe", "Tatte Bakery & Cafe, Brattle Street, Cambridge, MA", "How are the reviews of this cafe?", "a specific business without Google reviews", True),
]
