"""What belongs in the live feed, and what kind of thing each item is.

The feed is for new information about a place that a person weighing it up would care about: crime and safety, accidents and
traffic, weather alerts, a business opening or closing, an event, tourism, building and transport, and what people in the
community are saying. It is not for politics, or for things that merely mention the place (a film shot there, a sports
score, a stock price). These rules are plain keyword patterns on the headline: deterministic, free, instant, and
explainable, and therefore blunt. They will occasionally drop something worth keeping or keep something that is not; they
are tuned to err towards keeping what is about the place, and each rule is a line below to change.

Municipal matters (a council approving a bike lane, roadworks, planning) are kept: they are about the place. Politics here
means elections, parties and their politicians, and national or international political news.
"""

from __future__ import annotations

import re

CATEGORIES = (
    "Crime & safety",
    "Accidents & traffic",
    "Weather & alerts",
    "Business",
    "Events & tourism",
    "Development & transport",
    "Community",
    "News",
)


def _words(*patterns: str) -> re.Pattern[str]:
    return re.compile(r"\b(?:" + "|".join(patterns) + r")\b", re.IGNORECASE)


# ------------------------------------------------------------------------------------------------ what is left out
_POLITICS = _words(
    r"election\w*", r"electoral", r"ballots?", r"(?:state |general |party )?primary (?:results?|election|race|vote|day)",
    r"state primary", r"caucus\w*", r"senators?", r"senate", r"congress(?:man|woman|ional)?", r"parliament\w*", r"lawmakers?",
    r"legislat\w*", r"politic\w*", r"partisan", r"democrat\w*", r"republicans?", r"gop", r"trump\w*", r"biden", r"harris",
    r"obama", r"starmer", r"sunak", r"labou?r party", r"tories", r"tory", r"conservative party", r"liberal party",
    r"green party", r"reform uk", r"prime minister", r"presidential", r"president (?:trump|biden|xi|putin|macron)",
    r"white house", r"downing street", r"voters?", r"polling", r"referendum", r"impeach\w*", r"foreign policy", r"sanctions",
    r"geopolit\w*", r"mayoral (?:race|candidate|election)", r"campaign (?:trail|rally|finance)",
    r"government (?:announce\w*|policy|policies|minister|plans?)", r"whitehall", r"cabinet (?:minister|reshuffle|meeting)",
)
# Community posts are people asking for things or looking for each other: real, but not information about the place.
_PERSONAL = _words(
    r"missed connections?", r"roommates?", r"flatmates?", r"sublet\w*", r"looking for (?:a |an |some )?(?:friends?|roommates?|flatmates?|rooms?|partner|date|dates)",
    r"recommendations?", r"recs", r"advice", r"anyone know", r"does anyone", r"where can i", r"how do i", r"need help", r"for sale",
    r"free stuff", r"dating", r"lost (?:cat|dog|wallet|phone|keys)", r"found (?:cat|dog|wallet|phone|keys)", r"tea anyone",
    r"looking for", r"ISO", r"wanted",
)
_IRRELEVANT = _words(
    # entertainment and celebrity
    r"horoscopes?", r"zodiac", r"lottery", r"powerball", r"mega millions", r"celebrit\w+", r"red carpet", r"box office",
    r"movie review", r"film review", r"trailer", r"netflix", r"hbo", r"disney\+", r"episode recap", r"season finale",
    r"oscars?", r"grammys?", r"emmys?", r"filmed", r"streaming",
    # sport results (an event at a stadium is an event; a score is not information about the place)
    r"final score", r"match report", r"full[- ]time", r"transfer (?:news|window|rumou?rs?)", r"league table", r"play-?offs?",
    r"nfl", r"nba", r"mlb", r"nhl", r"premier league", r"champions league", r"super bowl", r"world series",
    # markets, deals, jobs, obituaries
    r"stock price", r"share price", r"shares (?:rise|fall|jump|slide|tumble|surge)", r"earnings (?:call|report)", r"nasdaq",
    r"nyse", r"ftse", r"dow jones", r"s&p 500", r"ipo", r"coupons?", r"promo codes?", r"black friday", r"cyber monday",
    r"discount codes?", r"best deals?", r"obituar\w+", r"is hiring", r"now hiring", r"job (?:openings?|listings?|vacanc\w+)",
)


def excluded(title: str, text: str = "", *, community: bool = False) -> str | None:
    """"politics" or "irrelevant" when the item should not be in the feed, else None. `community` adds the personal asks that
    fill a city's subreddit (roommate wanted, "best cat vet?"): a person's request is not news about the place."""
    haystack = f"{title} {text}"
    if _POLITICS.search(haystack):
        return "politics"
    if _IRRELEVANT.search(haystack):
        return "irrelevant"
    if community and _PERSONAL.search(title):
        return "irrelevant"  # judged on the headline only: a post's body can ask for anything
    return None


# ------------------------------------------------------------------------------------------------ what kind of item it is
# In this order: the first that matches names the item, so a fire that closes a road is "Crime & safety".
_KINDS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "Crime & safety",
        _words(
            r"police", r"arrest\w*", r"shoot\w*", r"shot", r"stabb\w*", r"robber\w*", r"burglar\w*", r"theft", r"stolen",
            r"assault\w*", r"murder\w*", r"homicide", r"suspects?", r"crimes?", r"criminal", r"gunman", r"gunfire", r"kidnap\w*",
            r"missing (?:person|man|woman|child|teen\w*|girl|boy)", r"fraud", r"scams?", r"manhunt", r"lockdown", r"evacuat\w*",
            r"charged with", r"sentenced", r"fire", r"fires", r"blaze", r"explosion", r"gas leak", r"firefighters?", r"rescue\w*",
            r"ambulance", r"emergency", r"threat\w*", r"vandal\w*", r"drugs?",
        ),
    ),
    (
        "Accidents & traffic",
        _words(
            r"crash\w*", r"collision", r"accident", r"hit-and-run", r"road (?:closure|closed|closures)", r"closed to traffic",
            r"traffic", r"gridlock", r"roadworks", r"road works", r"diversions?", r"delays?", r"derail\w*", r"injur\w*",
            r"cyclists?", r"pedestrians?", r"signal failure", r"roadblock", r"killed", r"dies after", r"died after",
        ),
    ),
    (
        "Weather & alerts",
        _words(
            r"storms?", r"flood\w*", r"heat ?wave", r"snow\w*", r"blizzard", r"hurricane", r"typhoon", r"tornado", r"weather (?:warning|alert)",
            r"earthquake", r"wildfire", r"air quality", r"smog", r"power outage", r"outage",
        ),
    ),
    (
        "Business",
        _words(
            r"opens", r"opening", r"opened", r"to open", r"closes", r"closing", r"closed for good", r"shuts", r"restaurants?",
            r"caf[eé]s?", r"bars?", r"pubs?", r"shops?", r"stores?", r"retail\w*", r"hotels?", r"lease", r"startups?", r"start-ups?",
            r"compan(?:y|ies)", r"business\w*", r"invest\w*", r"headquarters", r"office space", r"acqui\w+", r"launch\w*", r"brewery",
        ),
    ),
    (
        "Events & tourism",
        _words(
            r"festivals?", r"concerts?", r"gigs?", r"exhibitions?", r"parades?", r"fairs?", r"events?", r"tours?", r"tourists?",
            r"tourism", r"attractions?", r"museums?", r"galler(?:y|ies)", r"things to do", r"weekend", r"holidays?", r"theat(?:re|er)",
            r"comedy", r"markets?", r"carnival", r"fireworks", r"marathon", r"celebration", r"visit\w*", r"sightseeing",
        ),
    ),
    (
        "Development & transport",
        _words(
            r"construction", r"development\w*", r"developers?", r"planning", r"approved", r"proposals?", r"zoning", r"housing",
            r"apartments?", r"rents?", r"redevelop\w*", r"bridges?", r"tunnels?", r"stations?", r"rail\w*", r"metro", r"subway",
            r"trams?", r"bus routes?", r"buses", r"airport", r"highway", r"cycle lanes?", r"bike lanes?", r"infrastructure",
            r"permits?", r"transit",
        ),
    ),
)


def categorize(title: str, text: str = "", *, community: bool = False) -> str:
    """The kind of item, from its headline: one of `CATEGORIES`. A community post is "Community" unless it is plainly
    one of the others (a post about a crash is still a post, but "Accidents & traffic" tells a reader more)."""
    haystack = f"{title} {text}"
    for name, pattern in _KINDS:
        if pattern.search(haystack):
            return name
    return "Community" if community else "News"
