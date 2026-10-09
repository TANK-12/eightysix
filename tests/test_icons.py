"""The shared app icons (shared/forge_icons.js) cover every app and draw cleanly.

The registry is JavaScript, so node runs it with a stand-in `window` and hands
back every glyph's SVG markup; the checks here are on that markup. Emerson's
asks behind these (2026-10-07): one shared style, Jan Tune and Power clearly
different, and a Mission Control icon built on the Claude logo. Later the same
night: a switch back to the old emoji (Classic), with no repeats in it.
"""

import json
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
ICONS = ROOT / "shared" / "forge_icons.js"
SVG = "{http://www.w3.org/2000/svg}"

DUMP = """
// A small stand-in for the page: elements with child nodes, enough for paint()
// and setStyle() to run as they do in the hub.
class Text { constructor(t) { this.nodeType = 3; this.text = t; } }
class Svg { constructor(m) { this.nodeType = 1; this.markup = m; } matches(q) { return q === "svg.forge-glyph"; } }
class El {
  constructor() { this.nodeType = 1; this.dataset = {}; this.childNodes = []; this.writes = 0; }
  get firstChild() { return this.childNodes[0] || null; }
  set innerHTML(m) { this.writes++; this.childNodes = [new Svg(m)]; }
  set textContent(t) { this.writes++; this.childNodes = t ? [new Text(t)] : []; }
  matches() { return false; }
  replaceChild(n, old) { this.writes++; this.childNodes[this.childNodes.indexOf(old)] = n; }
  prepend(n) { this.writes++; this.childNodes.unshift(n); }
  append(n) { this.childNodes.push(n); }
  face() { const f = this.firstChild; return !f ? "" : f.nodeType === 3 ? f.text : f.markup ? "svg" : "?"; }
}
const page = [];
global.document = {
  createElement: () => { const t = { content: {} }; Object.defineProperty(t, "innerHTML", { set: (m) => { t.content.firstChild = new Svg(m); } }); return t; },
  createTextNode: (t) => new Text(t),
  querySelectorAll: () => page.filter((e) => e.dataset.icon !== undefined),
};
global.window = {};
require(process.argv[1]);
const I = window.ForgeIcons;
const el = () => { const e = new El(); page.push(e); return e; };

const a = I.paint(el(), "power", "x");
const painted = a.face() === "svg" && a.dataset.glyph === "power";
const before = a.writes; I.paint(a, "power", "x"); const repaint_writes = a.writes - before;
const c = I.paint(el(), "no-such-app", "Z");
const fallback = { text: c.face(), glyph: c.dataset.glyph === undefined };

// a dock item: its icon, then a tooltip that must survive every switch
const dock = I.paint(el(), "jan-tune", "x"); const tip = new El(); tip.tip = true; dock.append(tip);
const folder = el(); folder.append(new El()); // a folder's member grid, not marked
// a picture that failed to load: the icon replaces it, never sits beside it
const art = el(); art.append(new El());
I.paint(art, "power", "x");
const over_picture = art.childNodes.length === 1 && art.face() === "svg";
const gone = el(); I.paint(gone, "power", "x"); I.forget(gone);
const trip = [];
const look = () => ({ style: I.style(), a: a.face(), c: c.face(), dock: dock.face(),
  tip: dock.childNodes.length === 2 && dock.childNodes[1] === tip, folder: folder.childNodes.length });
trip.push(look());
trip.push({ changed: I.setStyle("classic"), ...look() });
trip.push({ changed: I.setStyle("classic"), ...look() });
const late = I.paint(el(), "mission", "x").face();
trip.push({ changed: I.setStyle("new"), ...look() });
trip.push({ changed: I.setStyle("nonsense"), ...look() });
trip.push({ changed: I.setStyle(undefined), ...look() });

console.log(JSON.stringify({
  ids: I.ids(),
  classic_ids: I.classicIds(),
  classic: Object.fromEntries(I.classicIds().map((id) => [id, I.classic(id)])),
  styles: I.styles,
  svg: Object.fromEntries(I.ids().map((id) => [id, I.svg(id)])),
  unknown: I.svg("no-such-app"),
  painted, repaint_writes, fallback, trip, late, over_picture,
  forgotten: gone.dataset.icon === undefined && gone.dataset.glyph === undefined,
}));
"""


@pytest.fixture(scope="module")
def reg():
    out = subprocess.run(
        ["node", "-e", DUMP, str(ICONS)],
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    return json.loads(out.stdout)


def apps():
    folders = [p.stem for p in (ROOT / "groups").glob("*.json")]
    return sorted(
        [p.parent.name for p in (ROOT / "apps").glob("*/forge_app.json")] + folders
    )


def test_every_app_and_folder_has_a_glyph(reg):
    missing = [a for a in apps() if a not in reg["ids"]]
    assert not missing, missing


def test_every_glyph_is_well_formed_svg_in_the_shared_style(reg):
    for app, markup in reg["svg"].items():
        root = ET.fromstring(markup)
        assert root.tag == SVG + "svg", app
        assert root.get("viewBox") == "0 0 24 24", app
        assert root.get("stroke") == "currentColor", app
        assert root.get("stroke-width") == "1.8", app
        assert root.get("stroke-linecap") == "round", app
        assert root.get("class") == "forge-glyph", app
        assert len(list(root)) > 0, app
        assert 'class="d"' not in markup and 'class="s"' not in markup, app


def test_glyphs_are_all_different(reg):
    seen = {}
    for app, markup in reg["svg"].items():
        assert markup not in seen, (app, seen.get(markup))
        seen[markup] = app


def test_jan_tune_and_power_do_not_look_alike(reg):
    tune = ET.fromstring(reg["svg"]["jan-tune"])
    power = ET.fromstring(reg["svg"]["power"])
    # sliders: three tracks and three solid knobs; power: a broken ring and a bar
    assert len(tune.findall(SVG + "rect")) == 3
    assert not power.findall(SVG + "rect")
    assert any("a8 8" in (p.get("d") or "") for p in power.findall(SVG + "path"))


def test_mission_is_built_on_the_claude_spark(reg):
    mission = reg["svg"]["mission"]
    assert "#e8875f" in mission  # Claude's orange, only on Mission's spark
    assert sum("#e8875f" in m for m in reg["svg"].values()) == 1
    # the Claude app's bubble carries the same spark outline, in its own colour
    spark = ET.fromstring(mission).findall(SVG + "path")[1].get("d")
    assert spark and spark in reg["svg"]["claude"]


def test_unknown_app_falls_back_to_its_emoji(reg):
    assert reg["unknown"] == ""
    assert reg["fallback"] == {"text": "Z", "glyph": True}


def test_paint_marks_the_glyph_and_skips_a_same_repaint(reg):
    assert reg["painted"]
    assert reg["repaint_writes"] == 0


# --- the two styles: New (the glyphs) and Classic (the emoji from before them)


def test_every_app_and_folder_has_a_classic_icon(reg):
    missing = [a for a in apps() if not reg["classic"].get(a)]
    assert not missing, missing
    # and nothing stale: every classic entry is a real app or folder
    assert sorted(reg["classic_ids"]) == sorted(reg["ids"])


def test_no_two_apps_share_a_classic_icon(reg):
    seen = {}
    for app, emoji in reg["classic"].items():
        bare = emoji.replace("\ufe0f", "")  # the emoji-style mark aside
        assert bare not in seen, (app, seen.get(bare), emoji)
        seen[bare] = app


def test_classic_fixes_emerson_asked_for(reg):
    classic = reg["classic"]
    # Jan Tune and Power were both a bolt; Mission Control shared Jan Hollow's
    # satellite. Each gets its own now, and Power keeps its bolt.
    assert classic["power"] == "⚡"
    assert classic["jan-tune"] not in ("⚡", "🎚️")
    assert classic["mission"] != classic["janhollow"] == "🛰️"


def test_classic_is_the_old_emoji_from_before_the_glyphs(reg):
    # Every app that already had an emoji before commit acc42c6 keeps it in
    # Classic, except the repeats fixed here (one of each pair moves).
    changed = {
        "jan-tune",
        "mission",
        "files",
        "inkforge",
        "codec-player",
        "terminal",
        "pixel-games",
    }
    old = old_emoji()
    if not old:
        pytest.skip("no git history to compare with")
    for app, emoji in old.items():
        if app in reg["classic"] and app not in changed:
            assert reg["classic"][app] == emoji, (app, reg["classic"][app], emoji)


def test_the_style_switch_round_trips_in_place(reg):
    t = reg["trip"]
    assert reg["styles"] == ["new", "classic"]
    start, classic, again, back, odd, unset = t
    assert start["style"] == "new" and start["a"] == "svg" and start["dock"] == "svg"
    assert classic["changed"] and classic["style"] == "classic"
    assert classic["a"] == "⚡" and classic["dock"] == reg["classic"]["jan-tune"]
    assert classic["c"] == "Z"  # no classic entry: the app's own emoji
    assert not again["changed"]  # the same style again does nothing
    assert reg["late"] == reg["classic"]["mission"]  # painted while classic
    assert (
        back["changed"]
        and back["style"] == "new"
        and back["a"] == "svg"
        and back["dock"] == "svg"
    )
    assert not odd["changed"] and odd["style"] == "new"  # unknown = new
    assert not unset["changed"] and unset["style"] == "new"
    for step in t:
        assert step["tip"], step  # the dock tooltip survives every switch
        assert step["folder"] == 1, step  # an unmarked folder grid is left be


def test_an_icon_painted_over_something_else_replaces_it(reg):
    assert reg["over_picture"]
    assert reg["forgotten"]


def test_the_icons_setting_is_saved_and_cleaned(tmp_path):
    import sys

    sys.path.insert(0, str(ROOT / "shared"))
    import forge_theme

    spec = forge_theme.SETTINGS["icon_style"]
    assert spec["choices"] == ["new", "classic"] and spec["default"] == "new"
    assert spec["label"] == "Icons" and not spec.get("custom")  # reaches theme.js
    path = tmp_path / "settings.json"
    assert forge_theme.save({"icon_style": "classic"}, path)["icon_style"] == "classic"
    assert forge_theme.load(path)["icon_style"] == "classic"
    assert forge_theme.save({"icon_style": "sparkly"}, path)["icon_style"] == "new"


def old_emoji():
    """{app: emoji} from the manifests as they were before the glyphs."""
    try:
        names = subprocess.run(
            ["git", "-C", str(ROOT), "ls-tree", "-r", "--name-only", "acc42c6^"],
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        ).stdout.split()
    except (OSError, subprocess.SubprocessError):
        return {}
    out = {}
    for name in names:
        parts = name.split("/")
        if parts[-1] == "forge_app.json" and len(parts) == 3 and parts[0] == "apps":
            app = parts[1]
        elif len(parts) == 2 and parts[0] == "groups" and name.endswith(".json"):
            app = parts[1][:-5]
        else:
            continue
        text = subprocess.run(
            ["git", "-C", str(ROOT), "show", f"acc42c6^:{name}"],
            capture_output=True,
            text=True,
            timeout=30,
        ).stdout
        try:
            icon = json.loads(text).get("icon")
        except ValueError:
            continue
        if icon:
            out[app] = icon
    return out
