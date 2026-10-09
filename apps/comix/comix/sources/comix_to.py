"""comix.to, through its own rendered pages in headless Chrome.

Why not the site's JSON API: it answers 403 "Missing token" unless a token
built by an obfuscated in-page script comes with the request, and some pages
are scrambled and only put back together by the reader. Letting the real
reader run and capturing what it draws avoids both, and survives the site
changing its token scheme. Approach and selectors follow PanelForge's proven
``panelforge/sources/comix.py`` (verified live 2026-09-20); this version adds
the login cookies, page-at-a-time capture for the resumable queue, direct
re-downloads of stalled images, and a reader reload between passes.

Reader page slots are ``.rpage-page[data-page=N]``, holding either a plain
``img.rpage-page__img`` (downloaded directly, with cookies and a Referer) or a
``canvas.rpage-page__img`` (a scrambled page, captured with a clipped,
stability-checked screenshot; ``canvas.toDataURL()`` returns blank there).
"""

from __future__ import annotations

import os
import re
import sys
import time
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from typing import Callable
from urllib.parse import parse_qsl, urlencode, urlparse, urlsplit, urlunsplit

sys.path.insert(
    0,
    os.environ.get(
        "FORGE_SHARED_DIR", str(Path(__file__).resolve().parents[4] / "shared")
    ),
)
import forge_mangafetch as mf  # noqa: E402

from comix.sources import UNKNOWN_GROUP  # noqa: E402

SITE = "comix.to"
DOMAIN = "comix.to"
HOME = "https://comix.to/"
_CHAP_RE = re.compile(r"-chapter-([0-9]+(?:\.[0-9]+)?)$")
# Listing browsers use their own profile; the web app runs one listing at a time.
LIST_PROFILE = "comix-list"
_TITLE_RE = re.compile(r"^/title/[^/?#]+$")

Log = Callable[[str], None]


def matches(url: str) -> bool:
    host = urlparse(url).netloc
    return host == DOMAIN or host.endswith("." + DOMAIN)


def chapter_number(href: str) -> float | None:
    m = _CHAP_RE.search(href.split("?")[0])
    return float(m.group(1)) if m else None


def absolute(href: str) -> str:
    return "https://comix.to" + href if href.startswith("/") else href


def _chrome(cookies: list[dict], profile: str) -> mf.ChromeCDP:
    chrome = mf.ChromeCDP(profile=profile)
    chrome.start()
    if cookies:
        chrome.call("Network.setCookies", cookies=cookies)
    return chrome


def _cookie_header(cookies: list[dict]) -> str:
    return "; ".join(f"{c['name']}={c['value']}" for c in cookies)


# --- listing --------------------------------------------------------------------

Fetch = Callable[[str, int], dict]  # (page url, attempt) -> parse_page(...)
# Loads of one page before it counts as missing (slow load, a 520 error page).
PAGE_TRIES = 3
_TOTAL_RE = re.compile(r"\bof\s+([0-9][0-9,]*)\s+items\b")


class _PageParser(HTMLParser):
    """Chapter rows, series links, pager numbers and the heading of a rendered
    comix.to page. Parsed here rather than by in-page JavaScript so the tests
    run the same code over pages saved from the site."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.head: dict = {"title": ""}
        self.rows: list[dict] = []
        self.links: list[dict] = []
        self.pager: list[int] = []
        self._row: dict | None = None
        self._li_depth = 0
        self._grab: tuple[str, dict, str] | None = None  # end tag, target, key
        self._text: list[str] = []

    def _start(self, tag: str, target: dict, key: str) -> None:
        self._grab = (tag, target, key)
        self._text = []

    def handle_starttag(self, tag: str, attrs: list) -> None:
        a = {k: v or "" for k, v in attrs}
        cls = a.get("class", "").split()
        if tag == "li":
            if self._row is not None:
                self._li_depth += 1
            elif "mchap-item" in cls:
                self._row = {"href": "", "label": "", "group": "", "uploader": ""}
                self.rows.append(self._row)
                self._li_depth = 1
            return
        if self._grab:
            # A library card names its series in an inner title attribute.
            if self._grab[2] == "text" and "card__title" in cls and a.get("title"):
                self._grab[1]["text"] = a["title"]
                self._grab = None
            return
        row = self._row
        if row is not None:
            if tag == "a" and "mchap-row__primary" in cls:
                row["href"] = a.get("href", "")
            elif tag == "a" and not row["href"] and "chapter" in a.get("href", ""):
                row["href"] = a["href"]
            if tag == "span" and "mchap-row__ch" in cls:
                self._start("span", row, "label")
            elif tag == "a" and "mchap-row__group" in cls:
                self._start("a", row, "group")
            elif tag == "a" and "mchap-row__uploader" in cls:
                self._start("a", row, "uploader")
        elif tag == "a" and a.get("href", "").startswith("/title/"):
            link = {"href": a["href"], "text": a.get("title", "")}
            self.links.append(link)
            if not link["text"]:
                self._start("a", link, "text")
        elif tag == "button" and "npager__num" in cls:
            self._start("button", {}, "pager")
        elif tag == "h1" and not self.head["title"]:
            self._start("h1", self.head, "title")

    def handle_endtag(self, tag: str) -> None:
        if self._grab and tag == self._grab[0]:
            _, target, key = self._grab
            text = " ".join("".join(self._text).split())
            if key == "pager":
                if text.isdigit():
                    self.pager.append(int(text))
            else:
                target[key] = text[:120]
            self._grab = None
        if tag == "li" and self._row is not None:
            self._li_depth -= 1
            if self._li_depth == 0:
                self._row = None

    def handle_data(self, data: str) -> None:
        if self._grab:
            self._text.append(data)


def parse_page(html: str) -> dict:
    """{"title", "rows", "links", "last_page", "total"} of one rendered page.

    last_page is the highest page number the pager shows (it shows a window
    of numbers, so it grows while walking); total is the chapter list's
    "Showing 1 to 20 of N items" count, None where the page has none.
    """
    p = _PageParser()
    p.feed(html)
    p.close()
    m = _TOTAL_RE.search(html)
    return {
        "title": p.head["title"],
        "rows": rows_from_dom(p.rows),
        "links": title_links(p.links),
        "last_page": max(p.pager, default=0),
        "total": int(m.group(1).replace(",", "")) if m else None,
    }


def group_name(raw: dict) -> str:
    """The scan group, else the uploader, else UNKNOWN_GROUP: the site lists
    some chapters with neither."""
    if raw.get("group"):
        return raw["group"]
    if raw.get("uploader"):
        return f"{raw['uploader']} (uploader)"
    return UNKNOWN_GROUP


def rows_from_dom(raw: list[dict]) -> list[dict]:
    """Turn the chapter list's DOM rows into chapter rows; drops non-chapters."""
    out = []
    for r in raw:
        num = chapter_number(r.get("href") or "")
        if num is None:
            continue
        out.append(
            {
                "number": num,
                "group": group_name(r),
                "url": absolute(r["href"]),
                "label": r.get("label") or f"Chapter {num:g}",
            }
        )
    return out


def title_links(raw: list[dict]) -> list[dict]:
    """Unique series links from a page's anchors, first title seen wins."""
    seen: dict[str, dict] = {}
    for a in raw:
        href = (a.get("href") or "").split("?")[0].split("#")[0]
        if _TITLE_RE.match(href) and href not in seen:
            seen[href] = {"url": absolute(href), "title": (a.get("text") or "")[:120]}
    return list(seen.values())


def page_url(url: str, n: int) -> str:
    """Page n of a paged list, whichever page ``url`` itself points at.

    Page 1 has no page number in its address; later pages use the style the
    link used: ``?page=N`` (comix.to's own) or a ``/page/N`` path.
    """
    parts = urlsplit(url.split("#")[0])
    path = re.sub(r"/page/[0-9]+/?$", "", parts.path)
    path_style = path != parts.path
    query = [(k, v) for k, v in parse_qsl(parts.query, True) if k != "page"]
    if n > 1:
        if path_style:
            path = path.rstrip("/") + f"/page/{n}"
        else:
            query.append(("page", str(n)))
    return urlunsplit((parts.scheme, parts.netloc, path, urlencode(query), ""))


def walk(
    link: str, fetch: Fetch, key: str, log: Log, what: str, max_pages: int
) -> tuple[str, list[dict]]:
    """(title, items) over every page of a list, page 1 first.

    ``key`` picks the items of a parsed page ("rows" or "links"). A page that
    adds nothing is loaded again while the pager or the item count says more
    pages exist, and skipped (logged) if it still fails, so one slow page or
    520 error no longer cuts the list short. Past the known last page, a page
    that adds nothing is the end.
    """
    found: dict[str, dict] = {}
    title = ""
    last = 1
    for n in range(1, max_pages + 1):
        new = 0
        for attempt in range(PAGE_TRIES):
            page = fetch(page_url(link, n), attempt)
            items = page.get(key) or []
            if n == 1 and items:
                title = title or page.get("title", "")
                if page.get("total"):
                    last = max(last, -(-page["total"] // len(items)))
            last = max(last, page.get("last_page") or 0)
            for item in items:
                if item["url"] not in found:
                    found[item["url"]] = item
                    new += 1
            if new or n > last:
                break
        if not new:
            if n >= last:
                break
            log(f"{what} page {n} would not load; skipped, so a few may be missing")
            continue
        log(f"{what} page {n} of {last}: {len(found)} so far")
    return title, list(found.values())


def _chrome_fetch(chrome: mf.ChromeCDP) -> Fetch:
    loads = [0]

    def fetch(url: str, attempt: int) -> dict:
        # A fresh browser's first page waits longer; each retry waits more.
        settle = (6.0 if loads[0] == 0 else 2.5) + 3.0 * attempt
        loads[0] += 1
        chrome.navigate(url, settle=settle)
        return parse_page(chrome.eval("document.documentElement.outerHTML") or "")

    return fetch


def list_series(
    url: str, cookies: list[dict], log: Log, fetch: Fetch | None = None
) -> dict:
    base = url.split("?")[0].split("#")[0]
    chrome = None
    if fetch is None:
        chrome = _chrome(cookies, LIST_PROFILE)
        fetch = _chrome_fetch(chrome)
    try:
        title, raw = walk(base, fetch, "rows", log, "list", 400)
    finally:
        if chrome:
            chrome.close()
    # One row per chapter and group; the newest upload wins a tie.
    found: dict[tuple[float, str], dict] = {}
    for row in raw:
        found.setdefault((row["number"], row["group"]), row)
    rows = [found[k] for k in sorted(found)]
    groups = sorted({r["group"] for r in rows})
    return {"title": title or "Untitled", "groups": groups, "rows": rows}


def list_library(
    link: str, cookies: list[dict], log: Log, fetch: Fetch | None = None
) -> list[dict]:
    """Every series linked from Emerson's library/bookmarks page, all pages."""
    chrome = None
    if fetch is None:
        chrome = _chrome(cookies, LIST_PROFILE)
        fetch = _chrome_fetch(chrome)
    try:
        _, found = walk(link, fetch, "links", log, "library", 200)
    finally:
        if chrome:
            chrome.close()
    return found


# --- reading one chapter ----------------------------------------------------------

_HIDE_CHROME_JS = (
    "(()=>{const st=document.createElement('style');"
    "st.textContent='body *{visibility:hidden !important} "
    "canvas.rpage-page__img, img.rpage-page__img{visibility:visible !important}';"
    "document.head.appendChild(st)})()"
)


def _slot_js(idx: int) -> str:
    return f"""(()=>{{const p=document.querySelector('.rpage-page[data-page="{idx}"]');
      if(!p) return {{kind:'none'}};
      const c=p.querySelector('canvas.rpage-page__img');
      const i=p.querySelector('img.rpage-page__img');
      if(c&&c.width>0&&!p.classList.contains('is-loading')) return {{kind:'canvas'}};
      if(i&&i.complete&&i.naturalWidth>0) return {{kind:'img',src:i.currentSrc||i.src,done:true}};
      if(i&&(i.currentSrc||i.src)) return {{kind:'img',src:i.currentSrc||i.src,done:false}};
      return {{kind:'wait'}}}})()"""


def _rect_js(idx: int) -> str:
    return (
        f"document.querySelector('.rpage-page[data-page=\"{idx}\"]')"
        ".scrollIntoView({block:'start'});"
        f"(()=>{{const c=document.querySelector('.rpage-page[data-page=\"{idx}\"] canvas');"
        "if(!c)return null;const b=c.getBoundingClientRect();"
        "return {x:b.left+scrollX,y:b.top+scrollY,w:b.width,h:b.height,cw:c.width}})()"
    )


class Reader:
    """One headless Chrome showing one chapter at a time.

    with source.reader(cookies, slot) as r:
        total = r.load(url)
        data, ext, why = r.capture(1)
    """

    def __init__(self, cookies: list[dict], slot: str | int = 0) -> None:
        self.cookies = cookies
        self.slot = slot
        self.url = ""
        self._chrome: mf.ChromeCDP | None = None
        self._ua = ""

    def __enter__(self) -> "Reader":
        self._chrome = _chrome(self.cookies, f"comix-fetch-{self.slot}")
        self._ua = self._chrome.user_agent()
        return self

    def __exit__(self, *exc) -> None:
        if self._chrome:
            self._chrome.close()

    def load(self, url: str) -> int:
        """Open the chapter; returns how many page slots the reader shows."""
        assert self._chrome
        self.url = url
        self._chrome.navigate(url, settle=8.0)
        self._chrome.eval(_HIDE_CHROME_JS)
        return int(
            self._chrome.eval("document.querySelectorAll('.rpage-page').length") or 0
        )

    def reload(self) -> int:
        return self.load(self.url)

    def _download(self, src: str) -> bytes:
        headers = {"User-Agent": self._ua, "Referer": HOME}
        if self.cookies:
            headers["Cookie"] = _cookie_header(self.cookies)
        req = urllib.request.Request(src, headers=headers)
        with urllib.request.urlopen(req, timeout=45) as resp:
            return resp.read()

    def capture(self, idx: int, wait: float = 12.0) -> tuple[bytes | None, str, str]:
        """(data, ext, reason). data is None when the page could not be had."""
        chrome = self._chrome
        assert chrome
        chrome.eval(
            f"(document.querySelector('.rpage-page[data-page=\"{idx}\"]')||"
            "{scrollIntoView(){}}).scrollIntoView({block:'center'})"
        )
        info: dict = {"kind": "wait"}
        deadline = time.time() + wait
        while time.time() < deadline:
            info = chrome.eval(_slot_js(idx)) or {"kind": "wait"}
            if info["kind"] == "canvas" or (info["kind"] == "img" and info["done"]):
                break
            time.sleep(0.3)
        if info["kind"] == "none":
            return None, "", "page slot not in the reader"
        if info["kind"] == "canvas":
            data = mf.capture_canvas_stable(chrome, _rect_js(idx), tries=12)
            if data is None:
                return None, "", "scrambled page never finished drawing"
            return data, "png", ""
        if info["kind"] == "img":
            # Even when the reader's own <img> stalled, its address is known:
            # fetch it directly, which is what beats the site's slow loading.
            last = ""
            for attempt in range(3):
                try:
                    data = self._download(info["src"])
                    return data, mf.sniff_ext(data), ""
                except Exception as e:
                    last = f"download failed: {e}"
                    time.sleep(2 * (attempt + 1))
            return None, "", last
        return None, "", "page never started loading"


def reader(cookies: list[dict], slot: str | int = 0) -> Reader:
    return Reader(cookies, slot)
