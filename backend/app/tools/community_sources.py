"""Where people actually talk about a place: forums, Q&A sites, social media and regional communities.

Web search alone returns SEO pages: estate agents, "top 10" listicles, hotel pages. What a place is
*like* is said in threads and comments: Reddit and Quora everywhere, and in most countries a local
forum that an English-language search never reaches (PTT and Dcard in Taiwan, Pantip in Thailand,
Naver cafes in Korea, Zhihu and Douban in China, Pikabu and Otzovik in Russia, Eksi Sozluk in Turkey).

This module is only a curated list of those domains. It carries no claims and no content; the
search tool passes it to Tavily as `include_domains`. What was learned by measuring the live API:

* Tavily *does* index Reddit, PTT and Dcard, but not when they are one of a dozen domains in a single
  English query: the top results then come from whichever listed site ranks best (Pixnet blogs, TripAdvisor),
  and a search for Taiwan appeared to "miss" PTT and Dcard entirely. Searched on their own, and for PTT and
  Dcard in Chinese, all three return real threads. So the country's forums are searched on their own, in the
  place's own language, for research questions (see `regional_domains`).
* Reddit is the exception to `include_domains` altogether. Re-measured against the live API (Erfurt, Germany, and a
  floating train in Thailand): `include_domains=["reddit.com"]` at basic depth returned no thread about the place,
  alone or in a short list, only whatever subreddit matched a stray word (adult, gaming and AI subreddits, and song
  titles for "what is it like"); the app's own community list of eleven domains returned YouTube, Facebook and TikTok
  pages and no Reddit for a place that has a thread titled with its exact name. The same searches with "reddit" as
  the first word of the query and no domain filter returned the threads. Both the live feed (`TavilyLiveFeedTool`)
  and the research community search (`community_query`) now search Reddit that way.
* `include_domains` is a strong preference, not a filter: a Reddit-only search still returned a few
  off-topic pages from other sites, which the place-relevance checks then drop.
* Facebook, Instagram, TikTok and X are mostly behind a login. They are included because they are where
  some conversation is, but expect few results from them.

Search results carry no publication date for these sites; `post_dates.py` reads it from the post itself.
Posts whose date cannot be read are kept and labeled "date unknown". The project's rule against inventing
timestamps is unchanged.
"""

from __future__ import annotations

from app.models.location import Location

# Everywhere. Ordered roughly by how much place-specific conversation each holds.
GLOBAL_COMMUNITY_DOMAINS: tuple[str, ...] = (
    "reddit.com",
    "quora.com",
    "tripadvisor.com",
    "lonelyplanet.com",
    "youtube.com",
    "x.com",
    "facebook.com",
    "instagram.com",
    "tiktok.com",
)

# Region-specific forums and review communities, by ISO 3166-1 alpha-2 country code.
REGIONAL_COMMUNITY_DOMAINS: dict[str, tuple[str, ...]] = {
    # East and Southeast Asia
    "tw": ("ptt.cc", "dcard.tw", "mobile01.com", "pixnet.net", "ipeen.com.tw"),
    "jp": ("5ch.net", "note.com", "ameblo.jp", "hatenablog.com", "tabelog.com", "retty.me", "chiebukuro.yahoo.co.jp"),
    "kr": ("blog.naver.com", "cafe.naver.com", "dcinside.com", "theqoo.net", "clien.net", "tistory.com"),
    "cn": ("zhihu.com", "douban.com", "xiaohongshu.com", "weibo.com", "tieba.baidu.com", "dianping.com"),
    "hk": ("lihkg.com", "openrice.com", "discuss.com.hk"),
    "th": ("pantip.com", "wongnai.com"),
    "vn": ("voz.vn", "webtretho.com", "foody.vn"),
    "id": ("kaskus.co.id", "tripadvisor.co.id"),
    "my": ("lowyat.net",),
    "sg": ("hardwarezone.com.sg",),
    "ph": ("pinoyexchange.com",),
    # South Asia
    "in": ("mouthshut.com", "justdial.com"),
    # Europe
    "de": ("gutefrage.net", "tripadvisor.de"),
    "fr": ("tripadvisor.fr", "jeuxvideo.com", "commentcamarche.net", "doctissimo.fr"),
    "es": ("forocoches.com", "mediavida.com", "tripadvisor.es"),
    "it": ("tripadvisor.it",),
    "pt": ("tripadvisor.pt",),
    "nl": ("tweakers.net", "tripadvisor.nl"),
    "pl": ("wykop.pl", "gazeta.pl"),
    "se": ("flashback.org",),
    "ru": ("vk.com", "pikabu.ru", "otzovik.com", "irecommend.ru"),
    "tr": ("eksisozluk.com", "donanimhaber.com", "sikayetvar.com"),
    "gb": ("mumsnet.com", "thestudentroom.co.uk"),
    # Americas
    "us": ("nextdoor.com", "yelp.com", "city-data.com"),
    "ca": ("redflagdeals.com",),
    "mx": ("taringa.net",),
    "ar": ("taringa.net",),
    "br": ("tripadvisor.com.br", "reclameaqui.com.br"),
    # Oceania
    "au": ("whirlpool.net.au", "ozbargain.com.au"),
    "nz": ("geekzone.co.nz",),
}

# The most Tavily is asked to restrict to in one call.
_MAX_DOMAINS = 24


def native_query(location: Location) -> str:
    """The place's own name in its own script, for searching the country's forums in the language they are
    written in (PTT and Dcard return nothing useful for an English query). Empty where no native name is known."""
    return " ".join(dict.fromkeys(word for word in (location.local_name, location.local_area) if word))[:120]


def regional_domains(country_code: str | None) -> list[str]:
    """Only the country's own forums and review communities (empty where none are listed)."""
    return list(REGIONAL_COMMUNITY_DOMAINS.get((country_code or "").lower(), ()))


def is_community_domain(domain: str) -> bool:
    """Whether `domain` (a host like "www.reddit.com") is one of the listed forums or social sites."""
    host = domain.lower().removeprefix("www.")
    everything = {d for group in REGIONAL_COMMUNITY_DOMAINS.values() for d in group} | set(GLOBAL_COMMUNITY_DOMAINS)
    return any(host == d or host.endswith("." + d) for d in everything)


# Words Google puts in front of a Thai (and some Indonesian) place name: "Chang Wat Lopburi" is the province of Lopburi,
# "Tambon Manao Wan" the subdistrict Manao Wan. Nobody writes them, so a page about the place never contains them.
_ADMIN_PREFIXES: tuple[tuple[str, ...], ...] = (
    ("chang", "wat"),
    ("changwat",),
    ("tambon",),
    ("amphoe",),
    ("khet",),
    ("khwaeng",),
    ("kabupaten",),
    ("kecamatan",),
    ("kelurahan",),
)


def without_admin_prefix(name: str) -> str:
    """"Chang Wat Lopburi" -> "Lopburi", "Tambon Manao Wan" -> "Manao Wan"; any other name is returned as it is."""
    words = name.split()
    lowered = [w.lower() for w in words]
    for prefix in _ADMIN_PREFIXES:
        if tuple(lowered[: len(prefix)]) == prefix and len(words) > len(prefix):
            return " ".join(words[len(prefix) :])
    return name


def place_names(location: Location) -> list[str]:
    """Every name people may use for the place, as they write it: its own (without Google's " - Lop Buri" tag) and the
    variants found for it, each once."""
    names: list[str] = []
    for raw in (location.name, *location.name_variants):
        name = base_name(raw)
        if name and name.lower() not in {n.lower() for n in names}:
            names.append(name)
    return names


def search_area(location: Location) -> str:
    """The area a search is anchored to: the city, unless the city is an administrative subunit (a Thai "Tambon", which
    nobody writes about), and then the province. Without the words nobody writes ("Chang Wat Lopburi" is "Lopburi")."""
    city = location.city or ""
    if city and without_admin_prefix(city) != city and location.region:
        return without_admin_prefix(location.region)
    return without_admin_prefix(city or location.region or location.country or "")


def base_name(name: str) -> str:
    """The place's name as people write it: Google's "Pa Sak Jolasid Dam - Lop Buri" is "Pa Sak Jolasid Dam" (the part
    after " - " tells two listings apart, and no page uses it). Searches and place checks both use this."""
    head = name.split(" - ")[0].strip()
    return head if len(head) >= 3 else name


def community_query(location: Location, question: str) -> str:
    """What to ask the forums. A business is searched by its name; an area by its name plus the question,
    or a general "what is it like" when the question names nothing more specific.

    "reddit" leads the query, and no domain filter is sent with it. Measured against the live API, the domain list
    hid Reddit: for a floating train in Thailand it returned YouTube, Facebook and TikTok pages and no Reddit, though a
    thread titled with the place's exact name exists; the same query with "reddit" first and no filter returned that
    thread and kept TripAdvisor and the rest in the mix. (With "tripadvisor forum" added after it the thread was lost
    again, so it is only the one word.)"""
    name = base_name(location.name)
    area = search_area(location)
    if location.is_business:
        return f'reddit "{name}" {area} reviews opinions experience'.strip()
    label = f"{name}, {area}" if area and area.lower() != name.lower() else name
    return f"reddit {name} {area} {question}".strip()[:200] if question.strip() else f"reddit {label} what is it like"
