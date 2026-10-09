"""Live blur stays on single panes (task 63, 2026-10-07).

WHY THIS EXISTS
    Emerson's Forge froze when he picked Frosted or Liquid glass in
    Alt+Shift+M. Both put backdrop-filter (a live blur of whatever is behind)
    on every app tile, filter chip and widget: 52 blurred panes. WebKitGTK
    repaints what lies behind each blurred pane on every frame and the cost
    climbs steeply with their number. Measured in a headless GNOME at
    3072x1728 (tests/browser/check_hub_hang_webkit.py --fps, numbers in
    docs/library/forge/2026-10-07-glass-blur-freeze.md): 8 blurred panes ran
    at 60 fps, 13 at about 9, 17 at 1, and the 52 at 0 until the page hung.
    So a live blur may only go on a pane there is one of (the bar, the
    search, the dock, a popup, an overlay); things that come many at a time
    draw their glass instead. This test lists every live blur in the hub,
    the desktop page and shared/ and fails on one that is not in ALLOWED.
    The first fix missed that the hub builds its tiles as "tile glass", so
    the single-pane .glass rule still blurred all of them: the class lists
    the pages build are checked too.

HOW TO RUN
    python3 -m pytest tests/test_glass_budget.py

ADDING A BLURRED PANE
    Only for a single pane, never a selector that matches a list of things
    (tiles, chips, widgets, cards, rows). Add its selector to ALLOWED with
    a reason, and keep the panes shown at once well under eight.
"""

import glob
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# selector -> why there is only one of it on screen
ALLOWED = {
    "body.glass-frosted .glass:not(.tile)": ".glass is the bar, search, dock, popups, the app card",
    "body.glass-liquid .glass:not(.tile)": ".glass is the bar, search, dock, popups, the app card",
    "#overview": "Alt+Space overview, one full-screen overlay",
    "#fx-hud": "the one Alt+V hint line",
    "#relax": "the one Relax overlay",
    "#dk-edit, #dk-settings": "the desktop page's two corner buttons",
}

# classes of things that come many at a time
REPEATED = (".tile", ".fchip", ".wg", ".card", ".row", ".chip", ".dock-item", "li")

# repeated-looking classes that do wear .glass and keep its live blur, and why
# there is still only one on screen
GLASS_SINGLES = {"card": "the one loading or error card of the app on screen"}

PAGES = ("hub/*.html", "desktop/*.html")

SOURCES = (
    "shared/**/*.css",
    "hub/*.html",
    "hub/*.css",
    "desktop/*.html",
    "desktop/*.css",
)


def live_blurs():
    """(file, selector, value) for every backdrop-filter that is not none."""
    found = []
    files = sorted(
        {
            f
            for pat in SOURCES
            for f in glob.glob(os.path.join(ROOT, pat), recursive=True)
        }
    )
    for path in files:
        with open(path, encoding="utf-8") as f:
            text = f.read()
        # blank the comments out, keeping offsets
        text = re.sub(r"/\*.*?\*/", lambda m: " " * len(m.group()), text, flags=re.S)
        for m in re.finditer(
            r"(?<![-\w])(?:-webkit-)?backdrop-filter\s*:\s*([^;}]+)", text
        ):
            value = m.group(1).strip()
            if value.startswith("none"):
                continue
            brace = text.rfind("{", 0, m.start())
            start = max(text.rfind(c, 0, brace) for c in "};{") + 1
            selector = " ".join(text[start:brace].split())
            found.append((os.path.relpath(path, ROOT), selector, value))
    return found


def glass_classed():
    """Classes the pages put on an element together with glass, as in the
    hub's make("button", "tile glass"), iconEl("button", "dock-item glass")
    or class="card glass"."""
    found = set()
    files = sorted({f for pat in PAGES for f in glob.glob(os.path.join(ROOT, pat))})
    for path in files:
        with open(path, encoding="utf-8") as f:
            text = f.read()
        quoted = r"([\"'`])(.*?)\1"
        lead = r"(?:\bclass(?:Name)?\s*=\s*|\b(?:make|iconEl)\(\s*[\"'][\w-]+[\"']\s*,\s*|classList\.(?:add|toggle)\(\s*)"
        for m in re.finditer(lead + quoted, text):
            words = set(re.split(r"[^\w-]+", m.group(2)))
            if "glass" in words:
                found |= words - {"glass", ""}
    return found


def test_the_scan_finds_the_glass_panes():
    selectors = {s for _, s, _ in live_blurs()}
    assert (
        "body.glass-frosted .glass:not(.tile)" in selectors
    ), "the scan itself is broken"
    assert {"tile", "card"} <= glass_classed(), "the class scan itself is broken"


def test_every_live_blur_is_a_single_pane_on_the_list():
    stray = [(f, s) for f, s, _ in live_blurs() if s not in ALLOWED]
    assert not stray, (
        "live blur (backdrop-filter) on a selector not in ALLOWED; many blurred"
        f" panes freeze WebKitGTK, see this file's docstring: {stray}"
    )


def test_no_allowed_selector_names_a_repeated_item():
    for selector in ALLOWED:
        kept = re.sub(r":not\([^)]*\)", "", selector)  # what it leaves out is fine
        for part in REPEATED:
            assert not re.search(re.escape(part) + r"(?![-\w])", kept), (selector, part)


def test_repeated_items_wearing_the_glass_class_are_left_out_of_its_blur():
    """Tiles are built as "tile glass": every live-blur rule on .glass
    must leave them out, or the single-pane rule blurs dozens of tiles."""
    repeated = {p.lstrip(".") for p in REPEATED}
    worn = (glass_classed() & repeated) - set(GLASS_SINGLES)
    assert "tile" in worn, "the hub's tiles no longer wear glass: update this test"
    for selector in (s for s in ALLOWED if re.search(r"\.glass(?![-\w])", s)):
        for cls in worn:
            assert re.search(r":not\([^)]*\." + cls + r"(?![-\w])", selector), (
                selector,
                cls,
            )


def test_the_glass_kinds_draw_their_tiles_chips_and_widgets():
    """The repeated items still get a glass look, just a drawn one."""
    for kind in ("frosted", "liquid"):
        with open(
            os.path.join(ROOT, "shared/glass", kind + ".css"), encoding="utf-8"
        ) as f:
            css = f.read()
        for item in (".tile", ".fchip", ".widgets .wg"):
            assert item in css, (kind, item)
