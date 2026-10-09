"""
Metadata lookups for the Library Organiser.

  * AniList  -- GraphQL, no key, best canonical anime titles + year + format
  * Jikan    -- MyAnimeList proxy, no key, fallback
  * TMDB     -- needs a free key, for general TV / movies

All return a normalised dict:
  {title, year, format ('TV'|'MOVIE'|'OVA'|...), episodes, id, source}
or None.
"""

import time
import requests

_CACHE = {}
_LAST = {"anilist": 0.0, "jikan": 0.0}


def _throttle(k, gap):
    dt = time.time() - _LAST.get(k, 0)
    if dt < gap:
        time.sleep(gap - dt)
    _LAST[k] = time.time()


def _norm(title, year, fmt, eps, _id, src):
    return {"title": (title or "").strip(), "year": year, "format": fmt,
            "episodes": eps, "id": _id, "source": src}


def anilist(query, is_movie=False):
    key = ("anilist", query.lower(), is_movie)
    if key in _CACHE:
        return _CACHE[key]
    q = """
    query ($search: String, $type: MediaFormat) {
      Media(search: $search, type: ANIME, sort: SEARCH_MATCH, format: $type) {
        id episodes seasonYear startDate { year } format
        title { english romaji }
      }
    }"""
    variables = {"search": query}
    if is_movie:
        variables["type"] = "MOVIE"
    try:
        _throttle("anilist", 0.8)
        r = requests.post("https://graphql.anilist.co",
                          json={"query": q, "variables": variables}, timeout=15)
        if r.status_code == 429:
            time.sleep(3)
            r = requests.post("https://graphql.anilist.co",
                              json={"query": q, "variables": variables}, timeout=15)
        m = (r.json().get("data") or {}).get("Media")
        if not m:
            _CACHE[key] = None
            return None
        title = (m["title"].get("english") or m["title"].get("romaji") or query).strip()
        year = m.get("seasonYear") or (m.get("startDate") or {}).get("year")
        res = _norm(title, year, m.get("format"), m.get("episodes"), m.get("id"), "anilist")
        _CACHE[key] = res
        return res
    except Exception:
        _CACHE[key] = None
        return None


def jikan(query):
    key = ("jikan", query.lower())
    if key in _CACHE:
        return _CACHE[key]
    try:
        _throttle("jikan", 1.1)
        r = requests.get("https://api.jikan.moe/v4/anime",
                         params={"q": query, "limit": 1, "sfw": "false"}, timeout=15)
        data = (r.json().get("data") or [])
        if not data:
            _CACHE[key] = None
            return None
        m = data[0]
        year = m.get("year") or ((m.get("aired") or {}).get("prop") or {}).get("from", {}).get("year")
        res = _norm(m.get("title_english") or m.get("title"), year,
                    (m.get("type") or "").upper(), m.get("episodes"), m.get("mal_id"), "jikan")
        _CACHE[key] = res
        return res
    except Exception:
        _CACHE[key] = None
        return None


def tmdb(query, api_key, is_movie=False):
    if not api_key:
        return None
    key = ("tmdb", query.lower(), is_movie)
    if key in _CACHE:
        return _CACHE[key]
    kind = "movie" if is_movie else "tv"
    try:
        r = requests.get(f"https://api.themoviedb.org/3/search/{kind}",
                         params={"api_key": api_key, "query": query}, timeout=15)
        results = r.json().get("results") or []
        if not results:
            _CACHE[key] = None
            return None
        m = results[0]
        date = m.get("release_date") or m.get("first_air_date") or ""
        year = int(date[:4]) if date[:4].isdigit() else None
        res = _norm(m.get("title") or m.get("name"), year,
                    "MOVIE" if is_movie else "TV", None, m.get("id"), "tmdb")
        _CACHE[key] = res
        return res
    except Exception:
        _CACHE[key] = None
        return None


def lookup(query, provider="anilist", tmdb_key="", is_movie=False):
    if not query:
        return None
    if provider == "none":
        return None
    if provider == "tmdb":
        return tmdb(query, tmdb_key, is_movie) or anilist(query, is_movie)
    if provider == "jikan":
        return jikan(query) or anilist(query, is_movie)
    return anilist(query, is_movie) or jikan(query)
