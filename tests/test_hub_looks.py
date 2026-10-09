"""Hub looks: every stylesheet in hub/looks/ is a real, self-contained look.

WHY THIS EXISTS
    A look is one CSS file found by scanning (forge_theme.list_looks), and
    the hub swaps the file and a body class, look-<id>. Two ways that goes
    wrong silently: a file without its `/* look: Label | about */` header
    never reaches the Settings dropdown, and a rule not scoped under
    body.look-<id> leaks into every other look for the moment the sheets
    swap. Both are checked here for any look, so nothing names one.

HOW TO RUN
    python3 tests/test_hub_looks.py
"""

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "shared"))

import forge_theme  # noqa: E402

LOOKS = os.path.join(ROOT, "hub", "looks")


def split_top(head):
    """A selector list split at its own commas, not those inside :is() or :not()."""
    parts, depth, buf = [], 0, ""
    for ch in head:
        depth += ch == "("
        depth -= ch == ")"
        if ch == "," and depth == 0:
            parts.append(buf)
            buf = ""
        else:
            buf += ch
    return parts + [buf]


def selectors(css):
    """Top-level selectors of a stylesheet, comments removed, @-blocks skipped."""
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    out, depth, buf, skip = [], 0, "", 0
    for ch in css:
        if ch == "{":
            head = buf.strip()
            if depth == 0:
                if head.startswith("@"):
                    skip = 1
                else:
                    out.extend(s.strip() for s in split_top(head))
            depth += 1
            buf = ""
        elif ch == "}":
            depth -= 1
            if depth == 0:
                skip = 0
            buf = ""
        elif ch == ";" and depth == 0:
            buf = ""
        else:
            buf += ch
    assert skip in (0, 1)
    return out


def test_every_file_is_listed_with_a_label():
    looks = forge_theme.list_looks()
    files = sorted(f[:-4] for f in os.listdir(LOOKS) if f.endswith(".css"))
    assert sorted(looks) == files, (sorted(looks), files)
    assert list(looks)[0] == "classic"
    assert all(v["label"] and v["about"] for v in looks.values())


def test_every_rule_is_scoped_to_its_look():
    for name in os.listdir(LOOKS):
        if not name.endswith(".css"):
            continue
        look = name[:-4]
        with open(os.path.join(LOOKS, name), encoding="utf-8") as fh:
            for sel in selectors(fh.read()):
                assert sel.startswith(
                    f"body.look-{look}"
                ), f"{name}: unscoped rule {sel!r}"


def test_the_setting_offers_every_look_and_cleans_bad_values():
    spec = forge_theme.SETTINGS["look"]
    assert spec["default"] == "classic"
    assert set(spec["choices"]) == set(forge_theme.list_looks())
    assert forge_theme._clean("look", "no-such-look") == "classic"
    assert forge_theme._clean("look", "material") == "material"


def test_a_folder_without_looks_still_has_classic(tmp=None):
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "nohead.css").write_text("body { color: red }\n")
        assert list(forge_theme.list_looks(Path(d))) == ["classic"]


def test_the_hub_swaps_the_sheet_and_the_class():
    with open(os.path.join(ROOT, "hub", "index.html"), encoding="utf-8") as fh:
        hub = fh.read()
    assert 'id="look-css"' in hub
    assert "applyLook(theme.look" in hub
    assert "look: theme.look" in hub  # handed to the apps too


if __name__ == "__main__":
    failed = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS {name}")
            except AssertionError as exc:
                failed += 1
                print(f"FAIL {name}: {exc}")
    sys.exit(1 if failed else 0)
