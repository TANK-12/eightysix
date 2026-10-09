"""Mission Control speaks through the Forge voice service (Relay task 113).

The chat composer gets the shared mic and speak-replies buttons beside the
paperclip, and a turn that ends live in the open chat is read aloud when the
toggle is on; a history replay never is. Headless Chrome (Flatpak) through
~/Forge/tests/cdp_driver.py on Mission's real static files, with the fake
Claude app from test_convos_browser.py. ForgeVoice.speak is replaced in the
page, so nothing reaches the real voice service.
"""

from __future__ import annotations

import asyncio
import json
import random
import threading
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import test_convos_browser as base  # skips the module when there is no Chrome

cdp = base.cdp

ENDED = {"type": "result", "subtype": "success", "is_error": False, "duration_ms": 1200}
LIVE = [
    {
        "type": "assistant",
        "seq": 3,
        "message": {"content": [{"type": "text", "text": "Live answer here."}]},
    },
    {**ENDED, "seq": 4, "result": "Live answer here."},
]
# speak() is swapped the moment forge_voice.js defines ForgeVoice, before any
# chat is drawn, and the speak toggle starts on
STUB = """
window.__spoken = [];
localStorage.setItem('forge.voice.speak.mission', '1');
Object.defineProperty(window, 'ForgeVoice', {
  configurable: true,
  get() { return window.__fv; },
  set(v) {
    v.speak = (text, opts) => { window.__spoken.push([text, (opts || {}).app]); return Promise.resolve(); };
    window.__fv = v;
  },
});
"""


class Live(base.Fake):
    """The fake Claude app: history ends with a finished turn, and once `go` is
    set the next poll of each chat brings one more turn that ends live."""

    go = threading.Event()
    sent: set = set()

    def do_GET(self):
        parts = self.path.split("/")
        if self.path.startswith("/api/options") or len(parts) < 4:
            return super().do_GET()
        conv = parts[3]
        meta = {"title": f"task {conv}", "model": "opus", "effort": "high"}
        if "after=-1" in self.path:
            events = [
                {"type": "forge_user", "text": f"hello {conv}", "seq": 0},
                {
                    "type": "assistant",
                    "seq": 1,
                    "message": {"content": [{"type": "text", "text": "Old answer."}]},
                },
                {**ENDED, "seq": 2, "result": "Old answer."},
            ]
        elif Live.go.is_set() and conv not in Live.sent:
            Live.sent.add(conv)
            events = LIVE
        else:
            return super().do_GET()
        self._send(
            {
                "events": events,
                "busy": False,
                "meta": meta,
                "boot": "b1",
                "reset": False,
            }
        )


async def _run(tmp: Path, port: int, rows: list[dict]) -> list[str]:
    fails: list[str] = []
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/overview") as r:
        fake = json.load(r)
    fake.update(sessions=rows, sig="fake")
    async with cdp.chrome_page(tmp, "1400,900") as p:
        await p.call(
            "Page.addScriptToEvaluateOnNewDocument",
            source=f"window.__fake={json.dumps(fake)};" + base.SHIM + STUB,
        )
        await p.go(f"http://127.0.0.1:{port}/#convos")
        await p.wait("!!(window.MissionConvos && MissionConvos.selected)", 15)
        await asyncio.sleep(1.0)
        look = json.loads(await p.js("""JSON.stringify((() => {
                  const b = [...document.querySelectorAll('#fxForm .fx-voice')];
                  const a = document.getElementById('fxAttach');
                  return {
                    n: b.length,
                    after: a.nextElementSibling === b[0] && b[0].nextElementSibling === b[1],
                    text: b.map((x) => x.textContent),
                    pressed: b.map((x) => x.getAttribute('aria-pressed')),
                    on: b.map((x) => x.classList.contains('on')),
                    size: b.map((x) => Math.round(x.getBoundingClientRect().width)),
                  };
                })())"""))
        if look["n"] != 2 or not look["after"]:
            fails.append(f"mic and speak buttons not beside the paperclip: {look}")
        if look["text"] != ["🎤", "🔊"] or look["pressed"] != ["false", "true"]:
            fails.append(f"buttons do not show idle mic and speaking on: {look}")
        if look["on"] != [False, True]:
            fails.append(f"the speak button lost its on highlight: {look}")
        if any(w < 30 for w in look["size"]):
            fails.append(f"buttons drawn too small: {look}")
        if json.loads(await p.js("JSON.stringify(window.__spoken)")):
            fails.append("a history replay was spoken")
        Live.go.set()
        try:
            await p.wait("window.__spoken.length > 0", 10)
        except Exception:
            fails.append("the live turn end was not spoken")
        await asyncio.sleep(1.0)
        spoken = json.loads(await p.js("JSON.stringify(window.__spoken)"))
        if spoken and spoken != [["Live answer here.", "mission"]]:
            fails.append(f"spoken: {spoken}")
        errs = json.loads(await p.js("JSON.stringify(window.__errs)"))
        if errs:
            fails.append(f"page errors: {errs}")
        await p.screenshot(tmp / "mission-voice.png")
    return fails


def test_mission_mic_and_spoken_turn_end(tmp_path):
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Live)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    Live.posts, Live.meta, Live.sent = [], {}, set()
    Live.go.clear()
    rng = random.Random(113)
    rows = base._sessions(rng, 4)
    rows[0]["claude_tab"] = rows[0]["claude_tab"] or "conv00"
    try:
        with cdp.serve(
            base.APP, {"MISSION_PORT_CLAUDE": str(srv.server_address[1])}
        ) as port:
            fails = asyncio.run(_run(tmp_path, port, rows))
    finally:
        srv.shutdown()
        srv.server_close()
    assert not fails, "\n".join(fails)
