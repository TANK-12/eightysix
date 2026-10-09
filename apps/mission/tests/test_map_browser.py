"""The map in a real browser (task 73): with 1, 6, 15 and 40 sessions, at
the widths Emerson runs Mission Control, no two cards or lanes overlap,
nothing scrolls sideways, text stays readable and the lanes fill the width.

Runs headless Chrome (Flatpak) through ~/Forge/tests/cdp_driver.py; the
page's /api/overview answers are replaced by made-up waves, so the live
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

from mc import graph, overview  # noqa: E402

SIZES = [(900, 800), (1300, 840), (1536, 864)]

CHECK = """(() => {
  const r = (e) => e.getBoundingClientRect();
  const apart = (a, b) => a.right <= b.left + 0.5 || b.right <= a.left + 0.5 || a.bottom <= b.top + 0.5 || b.bottom <= a.top + 0.5;
  const inside = (a, b) => a.left >= b.left - 0.5 && a.right <= b.right + 0.5 && a.top >= b.top - 0.5 && a.bottom <= b.bottom + 0.5;
  const map = document.getElementById("map"), main = document.querySelector(".mc-main");
  const lanes = [...map.querySelectorAll(":scope > .lane")], cards = [...map.querySelectorAll(".mcard")];
  const bad = [];
  lanes.forEach((a, i) => lanes.slice(i + 1).forEach((b) => { if (!apart(r(a), r(b))) bad.push("lanes " + a.className + " / " + b.className); }));
  cards.forEach((a, i) => cards.slice(i + 1).forEach((b) => { if (!apart(r(a), r(b))) bad.push("cards " + a.dataset.node + " / " + b.dataset.node); }));
  for (const c of cards) if (!inside(r(c), r(c.closest(".lane")))) bad.push("card out of lane " + c.dataset.node);
  for (const l of lanes) if (!inside(r(l), r(map))) bad.push("lane out of map " + l.className);
  for (const t of map.querySelectorAll(".lane-head > *")) if (!inside(r(t), r(t.closest(".lane")))) bad.push("title out of lane " + t.textContent.slice(0, 30));
  const texts = [...map.querySelectorAll("*")].filter((e) => [...e.childNodes].some((c) => c.nodeType === 3 && c.textContent.trim()));
  const names = [...map.querySelectorAll(".mc-name")].filter((e) => e.scrollWidth > e.clientWidth + 1).map((e) => e.textContent);
  const m = r(map);
  const left = Math.min(...lanes.map((l) => r(l).left)), right = Math.max(...lanes.map((l) => r(l).right));
  const area = lanes.reduce((s, l) => s + r(l).width * r(l).height, 0);
  return {
    bad, lanes: lanes.length, cards: cards.length, clipped: names,
    sideways: [document.scrollingElement.scrollWidth - document.scrollingElement.clientWidth, main.scrollWidth - main.clientWidth, map.scrollWidth - map.clientWidth],
    minFont: Math.min(...texts.map((e) => parseFloat(getComputedStyle(e).fontSize))),
    used: (right - left) / m.width, filled: area / (m.width * m.height),
    zoom: document.getElementById("zoomPct").textContent,
  };
})()"""


def _row(base: dict, k: int, helpers: int = 0, group: str = "working") -> dict:
    row = copy.deepcopy(base)
    row.update(
        id=f"fake{k:02d}",
        name=f"ejb-{k:02d}",
        label=f"Agent {k} " + ("with a rather long name " if k % 7 == 3 else ""),
        group=group,
        action=(
            "checking the browser suite and re-measuring the parallax layers"
            if k % 2
            else "reading notes"
        ),
        family=["opus", "sonnet", "haiku"][k % 3],
        place="~",
        helpers=[
            {
                "id": f"h{k}-{j}",
                "state": "working",
                "task": "a helper job",
                "type": "crew-worker",
            }
            for j in range(helpers)
        ],
    )
    return row


def _crew(name: str, commander: str | None, members: list[str]) -> dict:
    return {
        "name": name,
        "active": True,
        "commander": commander,
        "goal": f"goal of {name}",
        "members": [
            {"name": m, "persona": "", "role": "helper", "session": ""} for m in members
        ],
        "tasks": [],
        "notes": [],
        "last": 0,
    }


def _waves(base: dict) -> dict:
    tmpl = base["sessions"][0]
    one = [_row(tmpl, 0)]
    six = [
        _row(
            tmpl,
            k,
            helpers=2 if k == 1 else 0,
            group=["working", "idle", "needs_you"][k % 3],
        )
        for k in range(6)
    ]
    fifteen = [_row(tmpl, k) for k in range(15)]
    forty = [_row(tmpl, k, helpers=k % 3) for k in range(40)]
    relay = lambda ids: {
        "present": True,
        "counts": {"queued": 1},
        "running": [  # noqa: E731
            {"id": f"r{i}", "session": s, "task": str(60 + i), "alive": True}
            for i, s in enumerate(ids)
        ],
    }
    jan = {
        "models": [
            {"id": "q", "name": "qwen3-4b", "cpu": 40},
            {"id": "g", "name": "gemma", "cpu": 3},
        ]
    }
    return {
        "1": (one, [], {}, None),
        "6": (six, [], relay(["fake02"]), None),
        "15": (
            fifteen,
            [_crew("wave", "ejb-00", [f"ejb-{k:02d}" for k in range(12)])],
            relay(["fake12", "fake13"]),
            None,
        ),
        "40": (
            forty,
            [
                _crew("a", "ejb-00", [f"ejb-{k:02d}" for k in range(8)]),
                _crew(
                    "b-" + "a-very-long-crew-name-" * 5,
                    "ejb-08",
                    [f"ejb-{k:02d}" for k in range(8, 16)],
                ),
                _crew("forge", None, [f"ejb-{k:02d}" for k in range(16, 22)]),
            ],
            relay([f"fake{k:02d}" for k in range(22, 28)]),
            jan,
        ),
    }


def _overview(base: dict, rows, crews, relay, jan, tag: str) -> dict:
    data = copy.deepcopy(base)
    data.update(sessions=rows, crews=crews, sig="fake-" + tag)
    data["graph"] = graph.build(rows, crews, relay, jan)
    # the top bar as on his laptop: two account meters in the Relay strip
    data["relay"] = {
        "present": True,
        "counts": {"queued": 1},
        "running": [],
        **(relay or {}),
        "meters": {"default": {"five": 78}, "hey": {"five": 100}},
    }
    return data


async def _check_all(tmp: Path, port: int, waves: dict) -> list[str]:
    fails = []
    async with cdp.chrome_page(tmp, "1600,1000") as p:
        for tag, data in waves.items():
            for w, h in SIZES:
                await p.call(
                    "Emulation.setDeviceMetricsOverride",
                    width=w,
                    height=h,
                    deviceScaleFactor=1,
                    mobile=False,
                )
                script = (
                    f"window.__fake = {json.dumps(data)};"
                    "const f0 = window.fetch.bind(window);"
                    "window.fetch = (u, o) => String(u).includes('/api/overview')"
                    " ? Promise.resolve(new Response(JSON.stringify(window.__fake), {headers: {'content-type': 'application/json'}}))"
                    " : f0(u, o);"
                    "localStorage.clear();"
                )
                ident = await p.call(
                    "Page.addScriptToEvaluateOnNewDocument", source=script
                )
                # a new query each time: the same URL with a #hash would not reload
                await p.go(f"http://127.0.0.1:{port}/?w={tag}-{w}#map")
                await p.wait("document.querySelectorAll('#map .mcard').length > 0", 10)
                await asyncio.sleep(0.6)
                got = await p.js(CHECK)
                await p.call(
                    "Page.removeScriptToEvaluateOnNewDocument",
                    identifier=ident["identifier"],
                )
                where = f"{tag} sessions at {w}px"
                if got["cards"] < len(data["sessions"]):
                    fails.append(f"{where}: only {got['cards']} cards drawn")
                if got["bad"]:
                    fails.append(f"{where}: overlap {got['bad'][:3]}")
                if max(got["sideways"]) > 0:
                    fails.append(f"{where}: sideways scroll {got['sideways']}")
                if got["minFont"] < 13:
                    fails.append(f"{where}: text at {got['minFont']}px")
                if got["clipped"]:
                    fails.append(f"{where}: names cut {got['clipped'][:2]}")
                if got["lanes"] > 1 and got["used"] < 0.98:
                    fails.append(f"{where}: lanes use {got['used']:.2f} of the width")
                if got["lanes"] > 2 and got["filled"] < 0.7:
                    fails.append(f"{where}: lanes fill {got['filled']:.2f} of the map")
                if tag == "6" and w == 1300:
                    # drawer open: the map narrows and must still fit
                    await p.js(
                        "document.querySelector('#map .mcard.k-session').click()"
                    )
                    await asyncio.sleep(0.8)
                    got = await p.js(CHECK)
                    if got["bad"] or max(got["sideways"]) > 0:
                        fails.append(f"drawer open: {got['bad'][:2]} {got['sideways']}")
                    await p.js("document.getElementById('dClose').click()")
                if tag == "15" and w == 900:
                    # biggest zoom on the narrowest window: still no sideways scroll
                    for _ in range(12):
                        await p.js("document.querySelector('[data-zoom=in]').click()")
                    await asyncio.sleep(0.4)
                    got = await p.js(CHECK)
                    if got["bad"] or max(got["sideways"]) > 0 or got["zoom"] != "200%":
                        fails.append(f"zoom 200%: {got}")
    return fails


def test_map_lanes_never_overlap_or_scroll_sideways(laptop, tmp_path):
    base = overview.collect(laptop["src"], now=laptop["now"])
    waves = {tag: _overview(base, *args, tag=tag) for tag, args in _waves(base).items()}
    assert [len(w["sessions"]) for w in waves.values()] == [1, 6, 15, 40]
    with cdp.serve(APP) as port:
        fails = asyncio.run(_check_all(tmp_path, port, waves))
    assert not fails, "\n".join(fails)
