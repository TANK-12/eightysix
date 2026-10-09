"""Emerson's ask (2026-10-08): "Go to it" on a session that runs in no
window (Relay runs its sessions headless) opens that session's chat in
Mission's Conversations view, instead of a red "not in a terminal or in
the Claude app". A real click in Chrome; /api/overview and /api/go are
made up, so the live machine's sessions do not matter."""

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
    " : String(u).includes('/api/go/')"
    " ? Promise.resolve(new Response(JSON.stringify({{ok: false, nowhere: true, reason: 'no window'}}), {{headers: {{'content-type': 'application/json'}}}}))"
    " : f0(u, o);"
    "localStorage.clear();"
)


async def _run(tmp: Path, port: int, data: dict) -> dict:
    async with cdp.chrome_page(tmp, "1600,1000") as p:
        await p.call(
            "Page.addScriptToEvaluateOnNewDocument",
            source=FAKE.format(data=json.dumps(data)),
        )
        await p.go(f"http://127.0.0.1:{port}/?t=go#sessions")
        await p.wait("document.querySelector('#grid [data-go=\"ejb-01\"]')", 10)
        await p.js("document.querySelector('#grid [data-go=\"ejb-01\"]').click()")
        await p.wait("location.hash === '#convos'", 5)
        await asyncio.sleep(0.5)
        return await p.js(
            "({view: location.hash, sel: window.MissionConvos.selected,"
            " toast: document.getElementById('toast').textContent})"
        )


def test_go_to_a_headless_session_opens_its_chat_here(laptop, tmp_path):
    base = overview.collect(laptop["src"], now=laptop["now"])
    data = copy.deepcopy(base)
    data.update(sessions=[_row(base["sessions"][0], k) for k in range(3)], sig="go")
    with cdp.serve(APP) as port:
        got = asyncio.run(_run(tmp_path, port, data))
    assert got["view"] == "#convos"
    assert got["sel"] == "fake01"
    assert "chat opened here" in got["toast"]
