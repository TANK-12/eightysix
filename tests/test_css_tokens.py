"""Every var(--token) in an app's CSS resolves to a token that exists.

WHY THIS EXISTS
    Dossier's mind map drew its labels with `fill: var(--fg)`. No Forge
    stylesheet has ever defined `--fg`. An unresolved var() with no fallback
    makes the whole declaration invalid, so `fill` fell back to its initial
    value -- black -- and every label on the Connections tab was black text on
    a near-black canvas. Nothing errored; it just could not be read.

    The failure is silent by nature, which is what makes it worth a test. The
    check is generic, so a new app under apps/ is covered the moment it has a
    stylesheet: nothing here names an app.

HOW TO RUN
    python3 tests/test_css_tokens.py
"""

import glob
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# A token used with a fallback -- var(--x, #fff) -- is fine by construction,
# so only the no-fallback form is collected.
USE = re.compile(r"var\(\s*(--[A-Za-z0-9_-]+)\s*\)")
DEFINE = re.compile(r"(--[A-Za-z0-9_-]+)\s*:")
COMMENT = re.compile(r"/\*.*?\*/", re.S)


def _tokens_defined(text):
    return set(DEFINE.findall(COMMENT.sub("", text)))


def _stylesheets():
    """Every app stylesheet, plus the hub shell's inline one. Discovered, the
    same way forge.py discovers apps -- no list of names anywhere."""
    sheets = sorted(glob.glob(os.path.join(ROOT, "apps", "*", "static", "*.css")))
    sheets += sorted(glob.glob(os.path.join(ROOT, "shared", "*.css")))
    return sheets


def test_no_stylesheet_uses_an_undefined_token():
    # Tokens every app inherits, plus the ones a page may define for itself.
    base = _tokens_defined(open(os.path.join(ROOT, "shared", "forge.css")).read())
    broken = {}
    for path in _stylesheets():
        text = open(path).read()
        known = base | _tokens_defined(text)
        used = set(USE.findall(COMMENT.sub("", text)))
        missing = sorted(used - known)
        if missing:
            broken[os.path.relpath(path, ROOT)] = missing
    assert not broken, f"stylesheets using tokens nothing defines: {broken}"


def test_the_mind_map_labels_are_not_black():
    """The specific regression: Dossier's graph labels must carry a real
    colour, not an unresolvable token."""
    path = os.path.join(ROOT, "apps", "dossier", "static", "app.css")
    text = COMMENT.sub("", open(path).read())
    rule = re.search(r"\.gnode\s+text\s*\{([^}]*)\}", text)
    assert rule, ".gnode text rule is gone from Dossier's stylesheet"
    fill = re.search(r"fill:\s*([^;]+);", rule.group(1))
    assert fill, ".gnode text no longer sets a fill"
    value = fill.group(1).strip()
    assert value != "var(--fg)", "the undefined token is back"
    token = USE.search(value)
    if token:
        base = _tokens_defined(open(os.path.join(ROOT, "shared", "forge.css")).read())
        assert token.group(1) in base | _tokens_defined(
            text
        ), f"{value} resolves to nothing"


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS :: {name}")
            except AssertionError as e:
                failures += 1
                print(f"FAIL :: {name} :: {e}")
    print()
    print("ALL PASS" if not failures else f"{failures} FAILED")
    sys.exit(1 if failures else 0)
