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
  Dcard in Chinese, all three return real threads. So the sources are searched in separate groups: Reddit
  with the country's forums for the live feed, and the country's forums in the place's own language for
  research questions (see `regional_domains` and `feed_domains`).
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


def community_domains(country_code: str | None, include_regional: bool = True) -> list[str]:
    """The domains for an English community search in `country_code`: the country's forums first (unless
    they are searched separately, in the local language), then the global ones."""
    regional = regional_domains(country_code) if include_regional else []
    return list(dict.fromkeys((*regional, *GLOBAL_COMMUNITY_DOMAINS)))[:_MAX_DOMAINS]


def native_query(location: Location) -> str:
    """The place's own name in its own script, for searching the country's forums in the language they are
    written in (PTT and Dcard return nothing useful for an English query). Empty where no native name is known."""
    return " ".join(dict.fromkeys(word for word in (location.local_name, location.local_area) if word))[:120]


def regional_domains(country_code: str | None) -> list[str]:
    """Only the country's own forums and review communities (empty where none are listed)."""
    return list(REGIONAL_COMMUNITY_DOMAINS.get((country_code or "").lower(), ()))


def feed_domains(country_code: str | None) -> list[str]:
    """What the live feed searches for conversation: Reddit and the country's own forums, nothing else.
    TripAdvisor, YouTube and the social networks are left out of the feed on purpose: they crowd the results
    with listings and videos, and the feed is about what people are saying."""
    return list(dict.fromkeys((*regional_domains(country_code), "reddit.com")))


def is_community_domain(domain: str) -> bool:
    """Whether `domain` (a host like "www.reddit.com") is one of the listed forums or social sites."""
    host = domain.lower().removeprefix("www.")
    everything = {d for group in REGIONAL_COMMUNITY_DOMAINS.values() for d in group} | set(GLOBAL_COMMUNITY_DOMAINS)
    return any(host == d or host.endswith("." + d) for d in everything)


def community_query(location: Location, question: str) -> str:
    """What to ask the forums. A business is searched by its name; an area by its name plus the question,
    or a general "what is it like" when the question names nothing more specific."""
    area = location.city or location.region or location.country or ""
    if location.is_business:
        return f'"{location.name}" {area} reviews opinions experience'.strip()
    label = ", ".join(part for part in (location.name, area) if part and part != location.name) or location.name
    return f"{location.name} {area} {question}".strip()[:200] if question.strip() else f"{label} what is it like"
