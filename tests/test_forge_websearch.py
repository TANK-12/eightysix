"""shared/forge_websearch.py: the DuckDuckGo result parsers, offline."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "shared"))

import forge_websearch  # noqa: E402

HTML_PAGE = """
<div class="result results_links"><h2><a rel="nofollow" class="result__a"
 href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fwiki.archlinux.org%2Ftitle%2FHyprland&amp;rut=x">
 <b>Hyprland</b> - ArchWiki</a></h2>
<a class="result__snippet" href="x">Hyprland is a tiling &amp; dynamic compositor.</a></div>
<div class="result results_links"><a class="result__a"
 href="https://duckduckgo.com/y.js?ad_domain=x">An advert</a></div>
<div class="result results_links"><a class="result__a" href="https://hypr.land/">Hyprland</a></div>
"""

LITE_PAGE = """
<tr><td><a rel="nofollow" href="https://docs.python.org/3/library/asyncio.html"
 class='result-link'>asyncio - Python docs</a></td></tr>
<tr><td class='result-snippet'>Asynchronous <b>I/O</b>.</td></tr>
"""


def test_html_results_unwrap_links_and_skip_adverts():
    found = forge_websearch.parse_html(HTML_PAGE)
    assert [r.url for r in found] == [
        "https://wiki.archlinux.org/title/Hyprland",
        "https://hypr.land/",
    ]
    assert found[0].title == "Hyprland - ArchWiki"
    assert found[0].snippet == "Hyprland is a tiling & dynamic compositor."
    assert found[1].snippet == ""


def test_lite_results():
    (r,) = forge_websearch.parse_lite(LITE_PAGE)
    assert (r.title, r.url, r.snippet) == (
        "asyncio - Python docs",
        "https://docs.python.org/3/library/asyncio.html",
        "Asynchronous I/O.",
    )


def test_text_numbers_results_and_reports_failure(monkeypatch):
    monkeypatch.setattr(
        forge_websearch,
        "search",
        lambda q, n: [forge_websearch.Result("A", "https://a.example", "about a")],
    )
    assert forge_websearch.text("a") == "1. A\n   https://a.example\n   about a"

    def down(q, n):
        raise OSError("offline")

    monkeypatch.setattr(forge_websearch, "search", down)
    assert "failed: offline" in forge_websearch.text("a")
