"""Emerson's three calm-down asks (2026-10-08, task 109 notes) in a real
browser, with real mouse clicks and keys through Chrome DevTools:

- the details drawer closes on a click outside it and on Esc; a click on
  another session switches it; a drag out of the drawer or a moved press
  leaves it; a dialog closes on a backdrop click, the note dialog only
  while it holds no words;
- a session that drops out of the list while open stays readable, marked
  ended, instead of "Session gone";
- the cards keep their places when only the activity order changes and
  move when a group changes.

The page's /api/overview answers are made up (window.__fake), so the live
machine's sessions do not matter."""

from __future__ import annotations

import asyncio
import copy
import json
import shutil
import sys
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP.parents[1] / "tests"))
cdp = pytest.importorskip("cdp_driver")
if not shutil.which("flatpak"):
    pytest.skip("no flatpak Chrome here", allow_module_level=True)

from mc import overview  # noqa: E402
from test_map_browser import _row  # noqa: E402

FAKE = (
    "window.__fake = {data};"
    "const f0 = window.fetch.bind(window);"
    "window.fetch = (u, o) => String(u).includes('/api/overview')"
    " ? Promise.resolve(new Response(JSON.stringify(window.__fake), {{headers: {{'content-type': 'application/json'}}}}))"
    " : f0(u, o);"
    "localStorage.clear();"
)
OPEN = "!document.getElementById('drawer').hidden"
ORDER = "[...document.querySelectorAll('#grid .s-card')].map((c) => c.dataset.open).join(',')"


async def _center(p, sel: str) -> tuple[float, float]:
    r = await p.js(
        f"(() => {{ const b = document.querySelector({json.dumps(sel)}).getBoundingClientRect();"
        " return [b.left + b.width / 2, b.top + b.height / 2]; })()"
    )
    return r[0], r[1]


async def _mouse(p, kind: str, x: float, y: float) -> None:
    await p.call(
        "Input.dispatchMouseEvent",
        type=kind,
        x=x,
        y=y,
        button="left",
        buttons=1 if kind != "mouseReleased" else 0,
        clickCount=1,
    )


async def _click(p, x: float, y: float) -> None:
    await _mouse(p, "mousePressed", x, y)
    await _mouse(p, "mouseReleased", x, y)
    await asyncio.sleep(0.25)


async def _drag(p, a: tuple[float, float], b: tuple[float, float]) -> None:
    await _mouse(p, "mousePressed", *a)
    await _mouse(p, "mouseMoved", (a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
    await _mouse(p, "mouseMoved", *b)
    await _mouse(p, "mouseReleased", *b)
    await asyncio.sleep(0.25)


async def _poll(p, sessions: list[dict]) -> None:
    await p.js(
        f"window.__fake.sessions = {json.dumps(sessions)}; window.MissionApp.pollNow();"
    )
    await asyncio.sleep(0.7)


async def _run(tmp: Path, port: int, data: dict) -> list[str]:
    fails: list[str] = []

    def check(ok, what: str) -> None:
        if not ok:
            fails.append(what)

    async with cdp.chrome_page(tmp, "1600,1000") as p:
        await p.call(
            "Emulation.setDeviceMetricsOverride",
            width=1600,
            height=1000,
            deviceScaleFactor=1,
            mobile=False,
        )
        await p.call(
            "Page.addScriptToEvaluateOnNewDocument",
            source=FAKE.format(data=json.dumps(data)),
        )
        await p.go(f"http://127.0.0.1:{port}/?t=away#sessions")
        await p.wait("document.querySelectorAll('#grid .s-card').length >= 4", 10)
        await asyncio.sleep(0.5)
        # an empty spot: the bottom left of the main area, on no card or button
        spot = await p.js(
            "(() => { const m = document.querySelector('.mc-main').getBoundingClientRect();"
            " const x = m.left + 14, y = m.bottom - 14, e = document.elementFromPoint(x, y);"
            " return [x, y, !!(e && e.closest('button, a, input, [data-open], [data-node], #drawer'))]; })()"
        )
        empty = (spot[0], spot[1])
        check(not spot[2], f"the empty spot {empty} lands on something clickable")
        card0 = await _center(p, '[data-open="fake00"]')

        # click away closes
        await _click(p, *card0)
        check(await p.js(OPEN), "a card click did not open the drawer")
        await _click(p, *empty)
        check(not await p.js(OPEN), "a click outside left the drawer open")

        # Esc closes
        await _click(p, *card0)
        await p.key("Escape", "Escape", vk=27)
        await asyncio.sleep(0.2)
        check(not await p.js(OPEN), "Esc left the drawer open")

        # another card switches it
        await _click(p, *card0)
        await _click(p, *(await _center(p, '#grid [data-open="fake01"]')))
        check(await p.js(OPEN), "a click on another card closed the drawer")
        title = await p.js("document.getElementById('dTitle').textContent")
        check("Agent 1" in title, f"the drawer did not switch: {title!r}")

        # a drag out of the drawer, or a moved press outside, leaves it
        await _drag(p, await _center(p, "#dBody"), empty)
        check(await p.js(OPEN), "a drag out of the drawer closed it")
        await _drag(p, empty, (empty[0] + 60, empty[1] - 40))
        check(await p.js(OPEN), "a moved press outside closed the drawer")

        # the note dialog: a backdrop click keeps it while it has words
        await _click(p, *(await _center(p, '#dHead [data-msg="fake01"]')))
        check(
            await p.js("document.getElementById('compose').open"),
            "Message did not open",
        )
        await p.type("half a thought")
        await _click(p, 8, 8)
        check(
            await p.js("document.getElementById('compose').open"),
            "a backdrop click dropped typed words",
        )
        await p.js("document.getElementById('composeText').value = ''")
        await _click(p, 8, 8)
        check(
            not await p.js("document.getElementById('compose').open"),
            "a backdrop click left the empty note dialog open",
        )
        check(await p.js(OPEN), "closing the dialog closed the drawer under it")

        # a session that leaves while open stays, marked ended
        rows = data["sessions"]
        await _poll(p, [r for r in rows if r["id"] != "fake01"])
        check(await p.js(OPEN), "the drawer closed when its session left")
        title = await p.js("document.getElementById('dTitle').textContent")
        check("Agent 1" in title and "Ended" in title, f"left session title: {title!r}")
        check(
            await p.js("!!document.querySelector('#dHead .gone-note')"),
            "no note that the session left",
        )
        check(
            await p.js("!!document.querySelector('#grid [data-open=\"fake01\"].gone')"),
            "the card of the session that left is not dimmed",
        )
        body = await p.js("document.getElementById('dBody').textContent")
        check("Session gone" not in body, "still says Session gone")
        await p.screenshot(tmp / "gone.png")
        await _click(p, *empty)

        # calm order: activity alone moves nothing, a group change does
        before = await p.js(ORDER)
        swapped = copy.deepcopy([r for r in rows if r["id"] != "fake01"])
        for i, r in enumerate(swapped):
            r["last_active"] = 1000 + i
        swapped.reverse()
        await _poll(p, swapped)
        after = await p.js(ORDER)
        check(before == after, f"cards moved on activity alone: {before} -> {after}")
        swapped[-1]["group"] = "needs_you"
        moved_id = swapped[-1]["id"]
        await _poll(p, swapped)
        after = await p.js(ORDER)
        check(
            after.split(",")[0] == moved_id,
            f"{moved_id} needs you but is not on top: {after}",
        )
    return fails


def test_click_away_gentle_leaving_and_calm_order(laptop, tmp_path):
    base = overview.collect(laptop["src"], now=laptop["now"])
    data = copy.deepcopy(base)
    rows = [_row(base["sessions"][0], k) for k in range(4)]
    for i, r in enumerate(rows):
        r["last_active"] = laptop["now"] - 10 * i
    data.update(sessions=rows, sig="fake-away")
    with cdp.serve(APP) as port:
        fails = asyncio.run(_run(tmp_path, port, data))
    assert not fails, "\n".join(fails)
