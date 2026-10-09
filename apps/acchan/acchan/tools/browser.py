"""Web: Firefox tabs, the Forge Browser, reading pages, searching.

Firefox has no remote-control port by default, so tabs are handled the way a
person would: the list comes from Firefox's own session file (rewritten every
15 seconds while it runs), switching uses the address bar's open-tab search
("% words" then Enter), and closing is Ctrl+W on the switched-to tab.

Web players (Qobuz, YouTube, Spotify web...) are driven through media_control
when it is play/pause/next, and through these tab tools otherwise.
"""

from __future__ import annotations

import html
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from typing import Annotated

from ..registry import ToolError, tool
from ..sysutil import clip, spawn
from . import windows

TOOLSET = "browser"
TOOLSET_SUMMARY = "Firefox tabs (list/open/switch/close), read any web page in full, web search, Forge Browser"

TOOLSET_KEYWORDS = (
    "tab",
    "tabs",
    "firefox",
    "browser",
    "website",
    "web",
    "page",
    "site",
    "url",
    "google",
    "search",
    "youtube",
    "online",
    "internet",
    "http",
    "www",
    ".com",
    "look up",
)
# (what a person says, tool, arguments): few-shot lines for the prompt
TOOLSET_EXAMPLES = [
    ("what tabs do I have open", "browser_tabs", {}),
    (
        "search the web for cheap flights to Bali",
        "web_search",
        {"query": "cheap flights to Bali"},
    ),
]

FORGE_BROWSER = "http://127.0.0.1:8444"
UA = "Mozilla/5.0 (X11; Linux x86_64; rv:140.0) Gecko/20100101 Firefox/140.0"


def _profile() -> Path | None:
    browser_app = Path.home() / "Forge" / "apps" / "browser"
    if str(browser_app) not in sys.path:
        sys.path.append(str(browser_app))
    try:
        import firefox  # the Browser app's stdlib profile finder

        return firefox.find_profile()
    except Exception:
        for root in (
            Path.home() / ".mozilla/firefox",
            Path.home() / ".config/mozilla/firefox",
        ):
            hits = sorted(
                root.glob("*/sessionstore-backups"), key=lambda p: p.stat().st_mtime
            )
            if hits:
                return hits[-1].parent
    return None


def _mozlz4(file: Path) -> dict:
    import lz4.block

    raw = file.read_bytes()
    if raw[:8] != b"mozLz40\0":
        raise ToolError("Firefox session file has an unknown format.")
    return json.loads(lz4.block.decompress(raw[8:]))


def firefox_tabs() -> list[dict]:
    profile = _profile()
    if profile is None:
        raise ToolError("No Firefox profile found.")
    backups = profile / "sessionstore-backups"
    candidates = [backups / "recovery.jsonlz4", profile / "sessionstore.jsonlz4"]
    source = next((c for c in candidates if c.exists()), None)
    if source is None:
        raise ToolError("Firefox is not running (no session file).")
    session = _mozlz4(source)
    tabs = []
    for w, window in enumerate(session.get("windows", []), 1):
        selected = window.get("selected", 1)
        for t, tab in enumerate(window.get("tabs", []), 1):
            entries = tab.get("entries") or []
            if not entries:
                continue
            entry = entries[
                max(0, min(len(entries), tab.get("index", len(entries))) - 1)
            ]
            tabs.append(
                {
                    "window": w,
                    "index": t,
                    "title": entry.get("title") or "",
                    "url": entry.get("url") or "",
                    "active": t == selected,
                }
            )
    return tabs


def _host(url: str) -> str:
    host = urllib.parse.urlparse(url).netloc or url[:40]
    return host.removeprefix("www.")


@tool(
    TOOLSET,
    show=True,
    phrases=[
        "what tabs do i have open",
        "what tabs are open",
        "list tabs",
        "list my tabs",
    ],
    voice="ok",
)
def browser_tabs() -> str:
    """List every tab open in Firefox (number, title, site). The front tab of each window is marked *."""
    tabs = firefox_tabs()
    if not tabs:
        return "Firefox has no tabs open."
    count = len({t["window"] for t in tabs})
    several = count > 1
    rows = [
        f"{'*' if t['active'] else ' '} "
        f"{'w' + str(t['window']) + ' ' if several else ''}#{t['index']} "
        f"{t['title'][:60] or 'Untitled'} ({_host(t['url'])})"
        for t in tabs
    ]
    head = (
        f"{len(tabs)} tabs open in {count} window{'s' if several else ''}"
        " (* is the tab in front):"
    )
    return head + "\n" + "\n".join(rows)


def _as_url(text: str) -> str:
    text = text.strip()
    if re.match(r"^[a-z]+://|^about:[a-z]+$", text):
        return text
    if re.match(r"^[\w.-]+\.[a-z]{2,}(/\S*)?$", text) and " " not in text:
        return "https://" + text
    return "https://duckduckgo.com/?q=" + urllib.parse.quote_plus(text)


@tool(
    TOOLSET,
    example={"address": "youtube.com"},
    phrases=[
        "search for {address}",
        "search web for {address}",
        "google {address}",
        "look up {address}",
        "go to {address}",
        "open {address} in browser",
    ],
    voice="ok",
)
def open_web(
    address: Annotated[str, "A web address, or words to search for"],
    new_window: Annotated[bool, "Open in a new window instead of a new tab"] = False,
    private: Annotated[bool, "Open in a private (incognito) window"] = False,
) -> str:
    """Open a web page (or a search) in Firefox, in a new tab, a new window or a private window."""
    if private:
        url = _as_url(address) if address.strip() else ""
        spawn(["firefox", "--private-window", *([url] if url else [])])
        return f"Opened a private Firefox window{' at ' + url if url else ''}."
    url = _as_url(address or "about:newtab")
    spawn(["firefox", "--new-window" if new_window else "--new-tab", url])
    where = "a new window" if new_window else "a new tab"
    return f"Opened {'an empty page' if url == 'about:newtab' else url} in {where} in Firefox."


def _switch(query: str) -> dict:
    tabs = firefox_tabs()
    q = query.lower().strip()
    best = None
    for tab in tabs:
        hay = (tab["title"] + " " + tab["url"]).lower()
        if q.isdigit() and int(q) == tab["index"]:
            best = tab
            break
        if q in hay and (best is None or tab["active"]):
            best = tab
    if best is None:
        titles = "; ".join(t["title"][:40] for t in tabs[:15])
        raise ToolError(f"No Firefox tab matches {query!r}. Open tabs: {titles}")
    windows.focus(windows.find_window("firefox"))
    if not best["active"]:
        # The address bar's "%" prefix searches open tabs; Enter switches.
        needle = best["title"][:40] or best["url"]
        windows.send_keys(["ctrl+l"])
        time.sleep(0.15)
        windows.type_into("% " + needle)
        time.sleep(0.6)
        windows.send_keys(["down", "enter"])
        time.sleep(0.3)
    return best


@tool(
    TOOLSET,
    example={"tab": "qobuz"},
    phrases=[
        "switch to {tab} tab",
        "go to {tab} tab",
        "show me {tab} tab",
        "open {tab} tab",
    ],
    voice="ok",
)
def switch_tab(
    tab: Annotated[str, "Words from the tab's title or address, or its number"],
) -> str:
    """Bring a Firefox tab to the front."""
    found = _switch(tab)
    return f"Switched to {found['title'][:70]}."


@tool(TOOLSET, example={"tab": "youtube"}, risky=True)
def close_tab(
    tab: Annotated[
        str, "Words from the tab's title or address; empty for the front tab"
    ] = "",
) -> str:
    """Close a Firefox tab."""
    if tab:
        found = _switch(tab)
        name = found["title"][:70]
    else:
        windows.focus(windows.find_window("firefox"))
        name = "the front tab"
    windows.send_keys(["ctrl+w"])
    return f"Closed {name}."


class _Text(HTMLParser):
    SKIP = {
        "script",
        "style",
        "noscript",
        "svg",
        "nav",
        "footer",
        "header",
        "form",
        "button",
    }
    BLOCK = {
        "p",
        "div",
        "br",
        "li",
        "h1",
        "h2",
        "h3",
        "h4",
        "tr",
        "section",
        "article",
        "pre",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skip = 0
        self.title = ""
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.skip += 1
        if tag == "title":
            self._in_title = True
        if tag in self.BLOCK:
            self.parts.append("\n")
        if tag in ("h1", "h2", "h3"):
            self.parts.append("## ")

    def handle_endtag(self, tag):
        if tag in self.SKIP and self.skip:
            self.skip -= 1
        if tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        elif not self.skip:
            self.parts.append(data)

    def text(self) -> str:
        joined = "".join(self.parts)
        joined = re.sub(r"[ \t\r\f\v]+", " ", joined)
        joined = re.sub(r"\n\s*\n+", "\n\n", joined)
        return joined.strip()


def fetch(url: str, timeout: float = 20) -> tuple[str, str]:
    """(title, readable text) of a web page."""
    request = urllib.request.Request(
        url, headers={"User-Agent": UA, "Accept-Language": "en"}
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        kind = response.headers.get("Content-Type", "")
        raw = response.read(6_000_000)
    if "pdf" in kind or url.lower().endswith(".pdf"):
        from .docs import pdf_bytes_to_text

        return url, pdf_bytes_to_text(raw)
    charset = "utf-8"
    match = re.search(r"charset=([\w-]+)", kind)
    if match:
        charset = match.group(1)
    page = raw.decode(charset, "replace")
    if "html" not in kind and "<html" not in page[:2000].lower():
        return url, page
    parser = _Text()
    parser.feed(page)
    return html.unescape(parser.title.strip()), parser.text()


def current_tab_url() -> tuple[str, str]:
    for tab in firefox_tabs():
        if tab["active"]:
            return tab["title"], tab["url"]
    raise ToolError("Firefox has no front tab.")


@tool(TOOLSET, example={"url": "", "start": 0}, voice="ok")
def read_web_page(
    url: Annotated[str, "Address to read; empty for the tab in front in Firefox"] = "",
    start: Annotated[int, "Character offset to continue from, for long pages"] = 0,
) -> str:
    """Read the whole text of a web page (not just what is on screen). Empty url = the Firefox tab in front."""
    if not url:
        _title, url = current_tab_url()
    url = _as_url(url)
    try:
        title, text = fetch(url)
    except Exception as exc:
        raise ToolError(
            f"Could not fetch {url}: {exc}. If it needs a login, use look_at_screen instead."
        )
    total = len(text)
    piece = text[start : start + 9000]
    more = (
        f"\n[characters {start}-{start + len(piece)} of {total}; call again with start={start + len(piece)} for more, or use ask_document with the url]"
        if start + len(piece) < total
        else ""
    )
    return f"# {title}\n<{url}>\n\n{piece}{more}"


@tool(TOOLSET, example={"query": "python list comprehension"}, voice="ok")
def web_search(query: Annotated[str, "What to search for"]) -> str:
    """Search the web (DuckDuckGo). Returns titles, addresses and snippets."""
    url = "https://html.duckduckgo.com/html/?q=" + urllib.parse.quote_plus(query)
    request = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            page = response.read().decode("utf-8", "replace")
    except Exception as exc:
        raise ToolError(f"Search failed: {exc}")
    results = []
    for block in re.findall(
        r'<div class="result[^"]*results_links.*?</div>\s*</div>', page, re.S
    )[:8]:
        link = re.search(
            r'class="result__a" href="([^"]+)"[^>]*>(.*?)</a>', block, re.S
        )
        snip = re.search(r'class="result__snippet"[^>]*>(.*?)</a>', block, re.S)
        if not link:
            continue
        href = html.unescape(link.group(1))
        real = urllib.parse.parse_qs(urllib.parse.urlparse(href).query).get(
            "uddg", [href]
        )[0]
        title = re.sub("<[^>]+>", "", html.unescape(link.group(2))).strip()
        body = (
            re.sub("<[^>]+>", "", html.unescape(snip.group(1))).strip() if snip else ""
        )
        results.append(f"- {title}\n  {real}\n  {body[:220]}")
    return "\n".join(results) or "No results."


@tool(TOOLSET, example={"action": "open", "url": "wikipedia.org"}, voice="ok")
def forge_browser(
    action: Annotated[
        str, "open, search, read, tabs, back, forward, reload, switch or close"
    ],
    url: Annotated[str, "Address or search words (for open/search)"] = "",
    tab: Annotated[
        str, "Tab number or id (for switch/close/read); empty for the front tab"
    ] = "",
) -> str:
    """Control the Forge Browser app (the browser inside Forge): open pages, list/switch/close its tabs, read a tab."""
    args: dict = {}
    if url:
        args["url"] = url
        args["query"] = url
    if tab:
        args["tab"] = int(tab) if tab.isdigit() else tab
    body = json.dumps({**args, "op": action, "timeout": 45}).encode()
    request = urllib.request.Request(
        f"{FORGE_BROWSER}/api/agent/do",
        data=body,
        headers={"Content-Type": "application/json", "X-Forge": "1"},
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            result = json.loads(response.read())
    except Exception as exc:
        raise ToolError(
            f"The Forge Browser is not reachable ({exc}). Open Forge and its Browser app, or use Firefox tools."
        )
    if not result.get("ok", True):
        raise ToolError(str(result.get("error") or result))
    return clip(
        json.dumps(result.get("result", result), ensure_ascii=False, indent=1), 9000
    )
