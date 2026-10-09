"""Drive the real Exo Lab page in headless Chrome and photograph each view.

    .venv/bin/python tests/check_ui.py [--port N] [--shots DIR]

Not collected by pytest (it needs the Flatpak Chrome). Without --port it
starts its own backend on a free port with profiles in a scratch folder
(EXOLAB_DATA), so a save in the check never touches the real profiles. With
--port it uses a backend that is already running (and saves nothing).
Screenshots go to --shots (default /tmp/exolab-shots). Prints PASS/FAIL lines
and exits non-zero on any FAIL.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import shutil
import sys
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP.parents[1] / "tests"))

from cdp_driver import (  # noqa: E402  # pyright: ignore[reportMissingImports]
    CTRL,
    Page,
    chrome_page,
    serve,
)

results: list[str] = []

# Collects page errors before any script of the page runs.
CATCH = """
window.__errs = [];
addEventListener('error', e => __errs.push(`${e.message} @ ${e.filename}:${e.lineno}`));
addEventListener('unhandledrejection', e => __errs.push(`rejected: ${e.reason && e.reason.stack || e.reason}`));
const _ce = console.error;
console.error = (...a) => { __errs.push('console: ' + a.map(x => x && x.stack || String(x)).join(' ')); _ce(...a); };
"""


def check(name: str, ok: bool, extra: str = "") -> None:
    results.append(
        f"{'PASS' if ok else 'FAIL'} :: {name}{' :: ' + extra if extra else ''}"
    )


async def errors(p: Page) -> list[str]:
    return list(await p.js("window.__errs.splice(0)") or [])


async def tester(p: Page, port: int, model: str, test: str, edit: bool = False) -> None:
    q = f"model={model}&test={test}" + ("&edit=1&tab=parts" if edit else "")
    await p.go(f"http://127.0.0.1:{port}/#tester?{q}")


async def run(p: Page, port: int, shots: Path, saving: bool) -> None:
    await p.call("Page.addScriptToEvaluateOnNewDocument", source=CATCH)

    # Home menu.
    await p.go(f"http://127.0.0.1:{port}/#home")
    ok = await p.wait(
        "document.querySelectorAll('#home-models .mcard').length >= 6", 10
    )
    n = await p.js("document.querySelectorAll('#home-models .mcard').length")
    check("home lists the models", ok, f"{n} model cards")
    modes = await p.js(
        "[...document.querySelectorAll('.mode b')].map(b => b.textContent).join(' | ')"
    )
    check(
        "home has the tester and game modes", modes == "Real-world tester | Game", modes
    )
    await p.screenshot(shots / "1-home.png")
    errs = await errors(p)
    check("home: no page errors", not errs, "; ".join(errs)[:900])

    # Tester: shoulder range on the full suit.
    await tester(p, port, "exo_full", "shoulder_rom")
    ok = await p.wait("!!document.querySelector('#verdict .verdict')", 30)
    verdict = await p.js("document.querySelector('#verdict .verdict b')?.textContent")
    check("shoulder range runs and shows a verdict", ok, str(verdict))
    ok = await p.wait("document.getElementById('v3d-note').textContent === ''", 40)
    note = await p.js("document.getElementById('v3d-note').textContent")
    check("3D person and suit load", ok, note)
    skin = await p.js("document.getElementById('c3d').dataset.skin")
    check("the full suit puts the skin under its undersuit", skin == "undersuit", skin)
    shown = await p.js("!document.getElementById('map-sec').hidden")
    check("range map is shown for the range test", shown)
    await p.js("new Promise(r => setTimeout(r, 1200))")
    await p.screenshot(shots / "2-tester-rom.png")
    errs = await errors(p)
    check("tester: no page errors", not errs, "; ".join(errs)[:900])

    # The visual pass: the reach dome, the lock cones, the cameras, plain
    # words and the headline.
    c3d = "document.getElementById('c3d').dataset"
    ok = await p.wait(f"Number({c3d}.reach) > 300", 10)
    check("the reach dome draws the reachable cells", ok, await p.js(f"{c3d}.reach"))
    lock = await p.js(f"{c3d}.lock")
    check("four gimbal-lock cones round axis 1", lock == "4", str(lock))
    cam = str(await p.js(f"{c3d}.view"))
    dist = float(cam.split()[-1]) if cam.split()[-1:] else 0.0
    check(
        "the Shoulder camera sits about 0.6 m from the joint",
        cam.startswith("shoulder") and 0.5 <= dist <= 0.7,
        cam,
    )
    await p.screenshot(shots / "2a-shoulder-cam.png")
    await p.js("document.querySelector('[data-cam=front]').click()")
    await p.js("new Promise(r => setTimeout(r, 600))")
    cam = str(await p.js(f"{c3d}.view"))
    check("the Front camera frames the body", cam.startswith("front "), cam)
    await p.screenshot(shots / "2b-reach-dome.png")
    await p.js("document.querySelector('[data-cam=back]').click()")
    await p.js("new Promise(r => setTimeout(r, 600))")
    await p.screenshot(shots / "2c-lock-cones.png")
    head = await p.js(
        """(() => { const b = document.querySelector('#verdict .verdict b').textContent;
        const cards = [...document.querySelectorAll('#cards .card')];
        const orange = cards.some(c => c.classList.contains('lv-warn'));
        return [b, orange]; })()"""
    )
    head = head or ["", False]
    want = head[0] != "Pass" or not head[1]
    want = want and (head[0] != "Pass, with warnings" or head[1])
    check("the headline says Pass, with warnings when a card warns", want, str(head))
    jays = await p.js(
        """[...document.querySelectorAll('#cards, #readout, #parts, #compare')]
        .map(e => e.textContent).join(' ').match(/\\bJ[123]\\b/g)"""
    )
    check("cards, tiles and tables name the motors in plain words", not jays, str(jays))
    hint = await p.js(
        "[...document.querySelectorAll('#parts td')].find(t => t.textContent.includes('lift motor'))?.title || ''"
    )
    check(
        "a motor's hover line comes from its data",
        "drive" in str(hint).lower() or ":" in str(hint),
        str(hint)[:160],
    )
    await p.js("document.querySelector('[data-cam=shoulder]').click()")
    # Pose the arm into the lock zone: the lock tile goes red, the cone bright.
    await p.js("document.getElementById('btn-pose').click()")
    await p.wait("!document.getElementById('posebox').hidden", 5)
    await p.js("""(() => { for (const [k, v] of [['plane', '-30'], ['elev', '140']]) {
        const s = document.getElementById('pose-' + k);
        s.value = v; s.dispatchEvent(new Event('input', {bubbles: true})); } })()""")
    ok = await p.wait(
        "[...document.querySelectorAll('#readout .tile')].some(t => t.textContent.startsWith('Gimbal-lock') && t.classList.contains('lv-fail'))",
        10,
    )
    check("posing into the lock zone turns the lock tile red", ok)
    await p.js("new Promise(r => setTimeout(r, 500))")
    await p.screenshot(shots / "2d-lock-pose.png")
    await p.js("document.getElementById('btn-pose').click()")
    errs = await errors(p)
    check("visual pass: no page errors", not errs, "; ".join(errs)[:900])

    # Editor open on the parts tab.
    await p.js("document.getElementById('btn-editor').click()")
    ok = await p.wait(
        "document.querySelectorAll('#editor details.fold').length > 3", 10
    )
    n = await p.js("document.querySelectorAll('#editor details.fold').length")
    check("editor opens with part folds", ok, f"{n} folds")
    hash_ok = await p.js("location.hash.includes('edit=1')")
    check("editor state is in the address", hash_ok, await p.js("location.hash"))
    await p.screenshot(shots / "3-editor-parts.png")

    # The cuff liner is comfort only: a note, not a pick.
    liner = await p.js(
        """(() => { const w = document.querySelector('#editor .field[title="models/exo_full: cuffs.0.width_mm"]');
        if (!w) return 'no cuff fold';
        const f = w.closest('details.fold'); f.open = true; f.scrollIntoView({block: 'center'});
        const pick = document.querySelector('#editor .field[title="models/exo_full: cuffs.0.liner"]');
        const note = [...f.querySelectorAll('p')].map(e => e.textContent).find(t => t.startsWith('Liner:'));
        return (pick ? 'a liner pick; ' : '') + (note || 'no liner note'); })()"""
    )
    check(
        "a cuff's liner shows as a note, not a pick",
        bool(re.fullmatch(r"Liner: .+ · comfort only, not modelled", str(liner))),
        str(liner),
    )
    await p.screenshot(shots / "3b-editor-cuff.png")

    # Every editor tab builds without an error.
    tabs = await p.js(
        "[...document.querySelectorAll('#ed-tabs .tab')].map(b => b.dataset.tab)"
    )
    for tab in tabs or []:
        await p.js(f"document.querySelector('#ed-tabs [data-tab={tab}]').click()")
        await p.wait(
            f"document.querySelector('#ed-tabs [data-tab={tab}]').classList.contains('on')",
            5,
        )
        rows = await p.js(
            "document.querySelectorAll('#editor .knob, #editor .field').length"
        )
        errs = await errors(p)
        check(
            f"editor tab {tab} builds",
            bool(rows) and not errs,
            f"{rows} rows; " + "; ".join(errs)[:600],
        )

    # Knob help says what power costs: a motor's is a heavier drive, the
    # battery's is more cells.
    await p.js("document.querySelector('#ed-tabs [data-tab=parts]').click()")
    helps = await p.js("""[...document.querySelectorAll('#editor .knob .k-name')]
        .filter(s => /^power$/i.test(s.textContent.trim())).map(s => s.title)""")
    helps = helps or []
    check(
        "power knob help names its cost (motor weight, battery cells)",
        any("weight" in s for s in helps) and any("cells" in s for s in helps),
        " | ".join(sorted(set(helps)))[:300],
    )
    await p.js("document.querySelector('#ed-tabs [data-tab=materials]').click()")
    await p.js(
        "for (const d of document.querySelectorAll('#editor details.fold')) d.open = true"
    )
    await p.js("new Promise(r => setTimeout(r, 400))")
    await p.screenshot(shots / "4-editor-materials.png")

    # A knob edit re-runs the test live, Undo puts it back.
    await p.js("document.querySelector('#ed-tabs [data-tab=materials]').click()")
    before = await p.js("document.querySelector('#derive')?.textContent")
    await p.js(
        """(() => { const f = [...document.querySelectorAll('#editor details.fold')]
            .find(d => d.querySelector('summary').textContent.includes('7075'));
        const k = [...(f || document).querySelectorAll('.knob')]
            .find(r => r.querySelector('.k-name').textContent === 'Weight') || document.querySelector('#editor .knob');
        const s = k.querySelector('input[type=range]');
        s.value = String(Math.log10(3)); s.dispatchEvent(new Event('input', {bubbles: true})); })()"""
    )
    dirty = await p.wait(
        "document.getElementById('ed-dirty').textContent === 'unsaved edits'", 5
    )
    check(
        "a knob edit marks the profile unsaved",
        dirty,
        await p.js("document.getElementById('ed-dirty').textContent"),
    )
    changed = await p.wait(
        f"document.querySelector('#derive')?.textContent !== {before!r}", 15
    )
    check("a knob edit re-runs the test and changes the numbers", changed)
    chips = await p.wait(
        "!!document.querySelector('#editor .knob .k-delta span.up')", 15
    )
    chip = await p.js(
        "document.querySelector('#editor .knob .k-delta')?.textContent || ''"
    )
    check(
        "chips under the knob say what the edit did, before -> after",
        chips and "Suit mass ▲" in str(chip) and "→" in str(chip),
        str(chip)[:200],
    )
    await p.js(
        "document.querySelector('#editor .knob .k-delta')?.scrollIntoView({block: 'center'})"
    )
    await p.screenshot(shots / "4b-edit-chips.png")
    await p.key("z", "KeyZ", CTRL, 90)
    undone = await p.wait(
        "document.getElementById('ed-dirty').textContent !== 'unsaved edits'", 5
    )
    check(
        "Ctrl+Z undoes the edit",
        undone,
        await p.js("document.getElementById('ed-dirty').textContent"),
    )
    errs = await errors(p)
    check("editing: no page errors", not errs, "; ".join(errs)[:900])

    # A typed 0 in a width is held at the field's limit and the run still works.
    width_in = """[...document.querySelectorAll('#editor .field')]
        .find(r => r.textContent.includes('Width') && r.querySelector('input[type=number]'))
        ?.querySelector('input[type=number]')"""
    await p.js("document.querySelector('#ed-tabs [data-tab=parts]').click()")
    await p.js(
        f"(() => {{ const i = {width_in}; i.value = '0';"
        " i.dispatchEvent(new Event('change', {bubbles: true})); })()"
    )
    held = await p.wait(
        "document.getElementById('toast').textContent.includes('stays between')", 5
    )
    await p.js("new Promise(r => setTimeout(r, 2500))")
    width, low = await p.js(f"[{width_in}?.value, {width_in}?.getAttribute('min')]")
    fine = await p.js(
        "document.getElementById('err').hidden"
        " && !document.getElementById('verdict').textContent.includes('No result')"
    )
    check(
        "a typed 0 width is held at the field's limit and still runs",
        bool(held and width == low and float(low or 0) > 0 and fine),
        f"value {width}, limit {low}, toast {held}, run fine {fine}",
    )
    await p.key("z", "KeyZ", CTRL, 90)
    await p.js("new Promise(r => setTimeout(r, 1000))")

    # A failed run clears the last verdict instead of leaving it on screen.
    await p.js("""window.__fetch = window.fetch;
        window.fetch = (u, o) => String(u).includes('/api/run')
          ? Promise.resolve(new Response('{"detail": "forced failure"}',
              {status: 500, headers: {'content-type': 'application/json'}}))
          : window.__fetch(u, o);""")
    await p.js("document.getElementById('btn-run').click()")
    cleared = await p.wait(
        "document.getElementById('verdict').textContent.includes('No result')"
        " && !document.getElementById('err').hidden"
        " && document.getElementById('cards').children.length === 0"
        " && document.getElementById('derive-sec').hidden"
        " && document.getElementById('parts-sec').hidden"
        " && document.getElementById('readout').children.length === 0",
        10,
    )
    check(
        "a failed run clears the old verdict, cards, game stats and parts",
        cleared,
        await p.js("document.getElementById('verdict').textContent"),
    )
    await p.js("window.fetch = window.__fetch")
    await errors(p)

    # An id that is an Object property ("constructor") is no model.
    await p.go(f"http://127.0.0.1:{port}/#tester?model=constructor&test=shoulder_hold")
    await p.js("new Promise(r => setTimeout(r, 1500))")
    errs = await errors(p)
    picked = await p.js("document.getElementById('sel-model').value")
    check(
        "a model id like 'constructor' is ignored",
        not errs and picked in ("exo_full", "exo_lite"),
        f"model {picked!r}; " + "; ".join(errs)[:400],
    )

    # A link with only &tab= opens the editor on that tab.
    await tester(p, port, "exo_full", "shoulder_hold")
    await p.wait("document.getElementById('editor').hidden", 5)
    await p.go(
        f"http://127.0.0.1:{port}/#tester?model=exo_full&test=shoulder_hold&tab=mechanism"
    )
    opened = await p.wait(
        "!document.getElementById('editor').hidden && document.querySelector("
        "'#ed-tabs [data-tab=mechanism]')?.classList.contains('on')",
        5,
    )
    check(
        "a link with only &tab= opens the editor there",
        opened,
        await p.js("location.hash"),
    )

    # Motions on the lite suit: the motion list, the charts, playback.
    await tester(p, port, "exo_lite", "shoulder_motions")
    ok = await p.wait("document.querySelectorAll('#sub .pick').length > 3", 30)
    check(
        "motions list their moves",
        ok,
        str(await p.js("document.querySelectorAll('#sub .pick').length")),
    )
    shown = await p.js("!document.getElementById('chart-sec').hidden")
    check("motions show the charts", shown)
    reach = await p.js("document.getElementById('c3d').dataset.reach")
    check("the reach dome goes away on another test", reach == "0", str(reach))
    await p.wait("document.getElementById('v3d-note').textContent === ''", 40)
    skin = str(await p.js("document.getElementById('c3d').dataset.skin"))
    faces = int(skin.split()[-1]) if skin.startswith("shorts ") else 0
    check("the light suit gets dark shorts, limbs bare", faces > 100, skin)
    await p.js("document.getElementById('btn-play').click()")
    await p.js("new Promise(r => setTimeout(r, 1500))")
    frame = await p.js("Number(document.getElementById('scrub').value)")
    check("Play moves through the frames", (frame or 0) > 0, f"frame {frame}")
    await p.screenshot(shots / "5-tester-motions.png")
    errs = await errors(p)
    check("motions: no page errors", not errs, "; ".join(errs)[:900])

    # Close fit on the full suit: motions, the shell tables, and a jump from
    # the worst shell row to its frame, where the 3D view marks the clash.
    await tester(p, port, "exo_full", "close_fit")
    ok = await p.wait(
        "document.querySelectorAll('#sub .pick').length > 3"
        " && document.querySelectorAll('#sub .fit-shells tr.lv-row').length > 5",
        90,
    )
    check(
        "close fit lists motions and shells",
        ok,
        str(
            await p.js("document.querySelectorAll('#sub .fit-shells tr.lv-row').length")
        ),
    )
    await p.wait("document.getElementById('v3d-note').textContent === ''", 40)
    # Start from the first frame of the last motion, so the jump must move.
    where = (
        "document.querySelector('#sub .pick.on')?.textContent + '|'"
        " + document.getElementById('scrub').value"
    )
    await p.js("[...document.querySelectorAll('#sub .pick')].at(-1).click()")
    await p.js(
        "(() => { const s = document.getElementById('scrub'); s.value = 0;"
        " s.dispatchEvent(new Event('input')); })()"
    )
    before = await p.js(where)
    row = await p.js(
        "(() => { const r = document.querySelector('#sub .fit-pairs tr.lv-row.lv-fail');"
        " if (r) r.click(); return !!r; })()"
    )
    marked = row and await p.wait(
        "Number(document.getElementById('c3d').dataset.clash || 0) > 0"
        " && !!document.getElementById('c3d').dataset.tinted"
        f" && {where} !== {json.dumps(before)}",
        10,
    )
    check(
        "a shell pair row jumps to a frame with clash marks",
        marked,
        f"row {row}, from {before} to {await p.js(where)}, "
        + str(await p.js("JSON.stringify(document.getElementById('c3d').dataset)")),
    )
    tiles = await p.js(
        "[...document.querySelectorAll('#readout .tile span')].map(e => e.textContent).join('|')"
    )
    check(
        "close fit frame shows the fit tiles",
        "Closest shell to skin" in (tiles or ""),
        tiles,
    )
    await p.screenshot(shots / "5b-tester-close-fit.png")
    errs = await errors(p)
    check("close fit: no page errors", not errs, "; ".join(errs)[:900])

    # Hold: the pose table and pose mode.
    await tester(p, port, "exo_full", "shoulder_hold")
    ok = await p.wait("document.querySelectorAll('#sub tr.lv-row').length > 2", 30)
    check("hold lists its poses", ok)
    await p.js("document.getElementById('btn-pose').click()")
    ok = await p.wait("!document.getElementById('posebox').hidden", 5)
    await p.js("""(() => { const s = document.getElementById('pose-elev');
        s.value = '120'; s.dispatchEvent(new Event('input', {bubbles: true})); })()""")
    posed = await p.wait(
        "!!document.querySelector('.ro-pose')?.textContent.includes('raised 120')", 10
    )
    check(
        "pose mode answers a slider",
        ok and posed,
        await p.js("document.querySelector('.ro-pose')?.textContent"),
    )
    await p.screenshot(shots / "6-tester-hold-pose.png")

    # Lift, then the planned models show as planned.
    await tester(p, port, "exo_lite", "lift_cycle")
    ok = await p.wait("!!document.querySelector('#verdict .verdict')", 30)
    check("lift runs", ok)
    await tester(p, port, "spider_mech", "shoulder_rom")
    ok = await p.wait("!!document.querySelector('#verdict .verdict.lv-out')", 10)
    check("a planned model says it is planned", ok)
    planned = await p.js(
        """[document.getElementById('c3d').dataset.blank, !document.getElementById('plan').hidden,
        document.querySelector('#plan .plan-text')?.textContent.length || 0,
        document.getElementById('readout').children.length,
        document.getElementById('posebox').hidden]"""
    )
    check(
        "a planned model clears the stage and shows its plan large",
        planned is not None
        and planned[0] == "true"
        and planned[1]
        and planned[2] > 20
        and planned[3] == 0
        and planned[4],
        str(planned),
    )
    await p.js("new Promise(r => setTimeout(r, 400))")
    await p.screenshot(shots / "6b-planned.png")
    await tester(p, port, "exo_full", "shoulder_hold")
    ok = await p.wait(
        "document.getElementById('c3d').dataset.blank === 'false' && document.getElementById('plan').hidden",
        20,
    )
    check("a ready model after a planned one brings the stage back", ok)
    errs = await errors(p)
    check("hold, lift, planned: no page errors", not errs, "; ".join(errs)[:900])

    # The game's stats panel adds up: total = body + suit + kit.
    await p.go(f"http://127.0.0.1:{port}/game.html?model=exo_lite")
    mass_js = (
        "[...document.querySelectorAll('div > span')]"
        ".find(s => s.textContent === 'Mass')?.nextElementSibling?.textContent || ''"
    )
    await p.wait(rf"/kit [\d.]+/.test({mass_js})", 40)
    row = await p.js(mass_js)
    nums = [float(x) for x in re.findall(r"[\d.]+", row or "")]
    check(
        "game mass row adds up (body + suit + kit)",
        len(nums) == 4 and abs(nums[0] - sum(nums[1:])) < 0.15,
        row,
    )

    if saving:
        await tester(p, port, "exo_full", "shoulder_rom", edit=True)
        await p.wait("document.querySelectorAll('#editor details.fold').length > 3", 10)
        await p.js(
            """(() => { const s = document.querySelector('#editor .knob input[type=range]');
            s.value = String(Math.log10(0.5)); s.dispatchEvent(new Event('input', {bubbles: true})); })()"""
        )
        await p.wait(
            "document.getElementById('ed-dirty').textContent === 'unsaved edits'", 5
        )
        await p.js(
            "document.querySelector('#ed-saveas') && (document.querySelector('#ed-saveas').hidden = false)"
        )
        await p.js("document.getElementById('ed-name').value = 'ui check'")
        await p.js("document.querySelector('#ed-saveas button.primary').click()")
        ok = await p.wait(
            "[...document.getElementById('ed-prof').options].some(o => o.value === 'ui check')",
            10,
        )
        check("Save as makes a new profile", ok)

        # A power knob on J1, then J1 swapped for a free bearing: the knob
        # goes (a passive drive has no motor to scale), so Save still works.
        await tester(p, port, "exo_full", "shoulder_rom", edit=True)
        j1 = "document.querySelector('#editor .field[title=\"mechanisms/girdle_tracking: joints.0.actuator\"]')"
        await p.wait(f"!!{j1}", 10)
        await p.js(f"""(() => {{ const f = {j1}.closest('details.fold'); f.open = true;
            const k = [...f.querySelectorAll('.knob')].find(r => /^power$/i.test(r.querySelector('.k-name').textContent.trim()));
            const s = k.querySelector('input[type=range]'); s.value = String(Math.log10(2));
            s.dispatchEvent(new Event('input', {{bubbles: true}})); }})()""")
        await p.js("new Promise(r => setTimeout(r, 1500))")
        await p.js(
            f"""(() => {{ const s = {j1}.querySelector('select'); s.value = 'free_bearing';
            s.dispatchEvent(new Event('change', {{bubbles: true}})); }})()"""
        )
        dropped = await p.wait(
            "/Dropped knobs nothing reads now: .*J1 power/.test(document.getElementById('toast').textContent)",
            15,
        )
        check(
            "J1 swapped for a free bearing drops its power knob",
            dropped,
            str(await p.js("document.getElementById('toast').textContent")),
        )
        await p.js("document.getElementById('ed-save').click()")
        saved = await p.wait(
            "/Saved the profile ui check/.test(document.getElementById('toast').textContent)",
            10,
        )
        stored = await p.js(
            """fetch('/api/profiles/' + encodeURIComponent('ui check')).then(r => r.json())
            .then(d => JSON.stringify([d.knobs?.parts?.['exo_full/J1'] ?? null,
              d.overrides?.mechanisms?.girdle_tracking?.['joints.0.actuator'] ?? null]))"""
        )
        said = await p.js("document.getElementById('toast').textContent")
        check(
            "then Save works and stores the swap without the knob",
            saved and stored == '[null,"free_bearing"]',
            f"{said} {stored}",
        )

        # Both suits share the girdle tracker: a J1 power knob set on the
        # full suit goes when J1 is swapped for a bearing on the light one.
        full = json.loads((APP / "data/models/exo_full.json").read_text())["name"]
        await p.js(
            f"""(() => {{ const s = {j1}.querySelector('select'); s.value = 'harmonic_m';
            s.dispatchEvent(new Event('change', {{bubbles: true}})); }})()"""
        )
        await p.js("new Promise(r => setTimeout(r, 1500))")
        await p.js(f"""(() => {{ const f = {j1}.closest('details.fold'); f.open = true;
            const k = [...f.querySelectorAll('.knob')].find(r => /^power$/i.test(r.querySelector('.k-name').textContent.trim()));
            const s = k.querySelector('input[type=range]'); s.value = String(Math.log10(2));
            s.dispatchEvent(new Event('input', {{bubbles: true}})); }})()""")
        await p.js("new Promise(r => setTimeout(r, 1500))")
        await tester(p, port, "exo_lite", "shoulder_rom", edit=True)
        await p.wait(f"!!{j1}", 10)
        await p.js("new Promise(r => setTimeout(r, 1500))")
        await p.js(
            f"""(() => {{ const s = {j1}.querySelector('select'); s.value = 'free_bearing';
            s.dispatchEvent(new Event('change', {{bubbles: true}})); }})()"""
        )
        said = f"Dropped knobs nothing reads now: J1 power ({full})."
        other = await p.wait(
            f"document.getElementById('toast').textContent === {said!r}", 15
        )
        check(
            "a swap on the light suit drops the full suit's J1 power knob",
            other,
            str(await p.js("document.getElementById('toast').textContent")),
        )
        # One more edit (the bearing's weight), so there is something to save.
        await p.js(f"""(() => {{ const f = {j1}.closest('details.fold'); f.open = true;
            const k = [...f.querySelectorAll('.knob')].find(r => /^weight$/i.test(r.querySelector('.k-name').textContent.trim()));
            const s = k.querySelector('input[type=range]'); s.value = String(Math.log10(1.5));
            s.dispatchEvent(new Event('input', {{bubbles: true}})); }})()""")
        await p.js("new Promise(r => setTimeout(r, 1000))")
        await p.js("document.getElementById('ed-save').click()")
        saved = await p.wait(
            "/Saved the profile ui check/.test(document.getElementById('toast').textContent)",
            10,
        )
        stored = await p.js(
            """fetch('/api/profiles/' + encodeURIComponent('ui check')).then(r => r.json())
            .then(d => JSON.stringify([d.knobs?.parts?.['exo_full/J1'] ?? null, d.knobs?.parts?.['exo_lite/J1'] ?? null]))"""
        )
        check(
            "then Save works on the light suit too",
            saved and stored == '[null,{"weight":1.5}]',
            f"{await p.js('document.getElementById(`toast`).textContent')} {stored}",
        )

        # A spring type's strength says it reaches only arm joints.
        await p.js("document.querySelector('#ed-tabs [data-tab=joints]').click()")
        await p.wait("document.querySelectorAll('#editor .k-name').length > 3", 10)
        spring = await p.js(
            "[...document.querySelectorAll('#editor .k-name')].some(s => /leg spring is weight only/.test(s.title))"
        )
        check(
            "the spring's strength help says a leg spring is weight only", bool(spring)
        )
        errs = await errors(p)
        check("saving: no page errors", not errs, "; ".join(errs)[:900])


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=0)
    ap.add_argument("--shots", default="/tmp/exolab-shots")
    ap.add_argument("--size", default="1500,950")
    args = ap.parse_args()
    shots = Path(args.shots)
    shots.mkdir(parents=True, exist_ok=True)
    box = Path.home() / ".cache" / f"exolab-ui-{os.getpid()}"
    box.mkdir(parents=True)
    gl = ("--enable-unsafe-swiftshader", "--use-angle=swiftshader")
    try:
        if args.port:
            async with chrome_page(box, args.size, gl) as page:
                await run(page, args.port, shots, saving=False)
        else:
            env = {
                "FORGE_SHARED_DIR": str(APP.parents[1] / "shared"),
                "EXOLAB_DATA": str(box / "data"),
            }
            with serve(APP, env) as port:
                async with chrome_page(box, args.size, gl) as page:
                    await run(page, port, shots, saving=True)
    finally:
        shutil.rmtree(box, ignore_errors=True)
    print("\n".join(results))
    return 1 if any(r.startswith("FAIL") for r in results) else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
