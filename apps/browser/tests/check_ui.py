"""Drive the Browser page in headless Chrome inside a stand-in hub.

    .venv/bin/python tests/check_ui.py [--shots DIR] [--port N]

Not collected by pytest (it needs the Flatpak Chrome). It starts its own
backend on a free port with a throwaway data dir (FORGE_BROWSER_DATA) inside a
sandbox folder in tests/, so it never touches the real records. The stand-in
hub is a file page that frames the app, collects the view messages the app
sends forge.py and can post the hub's own messages back (visible, view-event).
The app frame is another origin, so the check attaches DevTools to the frame
itself: a small probe put there before the app's scripts run counts fetch,
timer and rAF callbacks, and expressions are evaluated in the frame directly.
--port N runs the backend on port N (default: any free port).

Checks: the page rests while the hub hides it (only the command long-poll
stays); with the server gone the command loop backs off, says so calmly, still
opens typed web addresses, and recovers by itself when the server is back; a
double click on the star bookmarks once; notes show above the page area (a
native page covers anything drawn over it); the side panel has empty states
and scrolls a long list inside itself; a closed tab can be reopened; with
many tabs the open one and the + stay in view; after a boot with the server
away the saved tabs come back, are not written over, and the strip clears
within one backoff step.
--shots DIR also saves half-scale screenshots at 760, 1100, 1500 and 1920 px.
Prints PASS/FAIL lines and exits non-zero on any FAIL.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP.parents[1] / "tests"))

from cdp_driver import (  # noqa: E402  # pyright: ignore[reportMissingImports]
    Page,
    chrome_page,
    free_port,
    wait_http,
)

WIDTHS = (760, 1100, 1500, 1920)
results: list[str] = []

# The open tab sits left of the +, and the + is inside the strip.
IN_VIEW = """(() => {
  const s = $('tabs').getBoundingClientRect();
  const a = $('tabs').querySelector('.tab.active').getBoundingClientRect();
  const n = $('new-tab').getBoundingClientRect();
  return [a.left >= s.left - 1 && a.right <= n.left + 1, n.left >= s.left - 1 && n.right <= s.right + 1];
})()"""

PROBE = """
window.__counts = { fetch: 0, raf: 0, interval: 0, timeout: 0, urls: [] };
const __f = window.fetch;
window.fetch = function (u) {
  __counts.fetch++;
  __counts.urls.push(String(u).slice(0, 80));
  // sessionStorage "__down": the app's own requests fail as from a dead server.
  if (sessionStorage.getItem("__down") && String(u).includes("/api/"))
    return Promise.reject(new TypeError("Failed to fetch"));
  return __f.apply(this, arguments);
};
const __r = window.requestAnimationFrame;
window.requestAnimationFrame = (cb) => __r.call(window, (t) => { __counts.raf++; cb(t); });
const __si = window.setInterval;
window.setInterval = (cb, ms, ...a) =>
  __si.call(window, () => { __counts.interval++; if (typeof cb === "function") cb(...a); }, ms);
const __st = window.setTimeout;
window.setTimeout = (cb, ms, ...a) =>
  __st.call(window, () => { __counts.timeout++; if (typeof cb === "function") cb(...a); }, ms);
"""

HUB = """<!doctype html><meta charset="utf-8"><title>stand-in hub</title>
<style>html,body{margin:0;height:100%;background:#0f1115}
iframe{border:0;width:100%;height:100%;display:block}</style>
<iframe id="f" src="APP_URL"></iframe>
<script>
window.views = [];
addEventListener("message", (e) => {
  const m = e.data || {};
  if (m.forge === "view") views.push(m);
});
function toApp(msg) { f.contentWindow.postMessage(msg, "*"); }
function viewEvent(ev) { toApp({ forge: "view-event", event: ev }); }
function setVisible(v) { toApp({ forge: "visible", visible: v }); }
</script>"""
FRAME = {"session": ""}


def check(name: str, ok: bool, extra: str = "") -> None:
    line = f"{'PASS' if ok else 'FAIL'} :: {name}"
    if extra and not ok:
        line += f" :: {extra}"
    results.append(line)
    print(line, flush=True)


class Backend:
    """The app's uvicorn on one fixed port, so it can be stopped and started
    again where the page expects it."""

    def __init__(self, data: Path, port: int = 0) -> None:
        self.port = port or free_port()
        self.data = data
        self.proc: subprocess.Popen | None = None

    def start(self) -> None:
        env = {
            **os.environ,
            "FORGE_BROWSER_DATA": str(self.data),
            "FORGE_SHARED_DIR": str(APP.parents[1] / "shared"),
        }
        self.proc = subprocess.Popen(
            [str(APP / ".venv/bin/python"), "-m", "uvicorn", "web_app:app"]
            + ["--host", "127.0.0.1", "--port", str(self.port)],
            cwd=APP,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        wait_http(f"http://127.0.0.1:{self.port}/")

    def stop(self) -> None:
        """Gone at once, like a crash: a held long-poll would keep a polite
        shutdown waiting for up to 25 s."""
        if self.proc is not None:
            self.proc.kill()
            self.proc.wait(10)
            self.proc = None


def seed(data: Path) -> None:
    """Bookmarks and a long history in the throwaway records."""
    os.environ["FORGE_BROWSER_DATA"] = str(data)
    sys.path.insert(0, str(APP))
    import store

    now = time.time()
    for i in range(300):
        store.record_visit(
            f"https://site{i}.example.org/page", f"Visited page {i}", 1 + i % 7, now - i
        )
    names = ["Arch Wiki", "Hacker News", "MDN", "日本語のページ", "GitHub", "YouTube"]
    for i, name in enumerate(names):
        store.add_bookmark(f"https://mark{i}.example.com/", name, "Toolbar")


async def frame_call(p: Page, method: str, **params):
    """A DevTools call into the app frame's own target."""
    p.n += 1
    mid = p.n
    message = {"id": mid, "method": method, "params": params}
    await p.ws.send(json.dumps(dict(message, sessionId=FRAME["session"])))
    while True:
        msg = json.loads(await p.ws.recv())
        if msg.get("id") == mid:
            if "error" in msg:
                raise RuntimeError(msg["error"])
            return msg.get("result", {})


async def app_js(p: Page, code: str) -> Any:
    """Evaluate `code` in the app frame; an exception comes back as a string."""
    r = await frame_call(
        p, "Runtime.evaluate", expression=code, awaitPromise=True, returnByValue=True
    )
    if "exceptionDetails" in r:
        return "error: " + str(r["exceptionDetails"].get("text"))
    return r["result"].get("value")


async def attach_frame(p: Page) -> bool:
    """Find the app frame, put the probe in it and load it again, so the
    probe runs before the app's own scripts."""
    for _ in range(100):
        targets = (await p.call("Target.getTargets"))["targetInfos"]
        frame = next(
            (t for t in targets if t["type"] == "iframe" and "127.0.0.1" in t["url"]),
            None,
        )
        if frame:
            break
        await asyncio.sleep(0.1)
    else:
        return False
    attached = await p.call(
        "Target.attachToTarget", targetId=frame["targetId"], flatten=True
    )
    FRAME["session"] = attached["sessionId"]
    await frame_call(p, "Page.enable")
    await frame_call(p, "Page.addScriptToEvaluateOnNewDocument", source=PROBE)
    await app_wait(p, "typeof state === 'object' && state.tabs.length === 1")
    await p.js("views.length = 0")
    await app_js(p, "location.reload(), 1")
    await asyncio.sleep(0.5)
    return await app_wait(p, "typeof __counts === 'object'")


async def app_wait(p: Page, code: str, timeout: float = 8.0) -> bool:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if await app_js(p, code) is True:
            return True
        await asyncio.sleep(0.2)
    return False


async def reset_counts(p: Page) -> None:
    await app_js(
        p,
        "Object.assign(__counts, {fetch: 0, raf: 0, interval: 0, timeout: 0, urls: []}), 1",
    )


async def shoot(p: Page, folder: Path, name: str, width: int) -> None:
    r = await p.call(
        "Page.captureScreenshot",
        format="png",
        clip={"x": 0, "y": 0, "width": width, "height": 860, "scale": 0.5},
    )
    import base64

    (folder / f"{name}-{width}.png").write_bytes(base64.b64decode(r["data"]))


async def shots(p: Page, folder: Path) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    await app_js(
        p,
        "$('show-bar').checked = true, $('show-bar').dispatchEvent(new Event('change')), 1",
    )
    for width in WIDTHS:
        await p.call(
            "Emulation.setDeviceMetricsOverride",
            width=width,
            height=860,
            deviceScaleFactor=1,
            mobile=False,
        )
        await asyncio.sleep(0.6)
        await shoot(p, folder, "start", width)
        await app_js(p, "openSide('history'), 1")
        await asyncio.sleep(0.8)
        await shoot(p, folder, "history", width)
        await app_js(p, "$('side-search').value = 'zzz-nothing', renderSide(), 1")
        await asyncio.sleep(0.6)
        await shoot(p, folder, "history-empty", width)
        await app_js(p, "openSide('history'), 1")
        await app_js(p, "toggleMenu(true), 1")
        await asyncio.sleep(0.5)
        await shoot(p, folder, "menu", width)
        await app_js(p, "toggleMenu(false), 1")
    await p.call("Emulation.clearDeviceMetricsOverride")
    await app_js(
        p,
        "$('show-bar').checked = false, $('show-bar').dispatchEvent(new Event('change')), 1",
    )


async def run(p: Page, backend: Backend, box: Path, shot_dir: Path | None) -> None:
    hub = box / "hub.html"
    hub.write_text(HUB.replace("APP_URL", f"http://127.0.0.1:{backend.port}/"))
    await p.go(hub.as_uri())
    booted = await attach_frame(p) and await app_wait(
        p,
        "typeof state === 'object' && state.tabs.length === 1 && state.bookmarks.length === 6",
    )
    check(
        "the page boots inside the hub with its records",
        booted,
        str(
            await app_js(
                p, "[typeof __counts, state.tabs.length, state.bookmarks.length]"
            )
        ),
    )
    if not booted:
        return
    creates = await p.js("views.filter((m) => m.op === 'create').length")
    check("the first tab asks forge.py for a view", creates == 1, str(creates))

    if shot_dir:
        await shots(p, shot_dir)

    # --- rests while the hub hides it -------------------------------------------------
    await asyncio.sleep(1.5)  # the boot's own session save (0.8 s after the first tab)
    await reset_counts(p)
    await p.js("setVisible(false)")
    await asyncio.sleep(10)
    c = await app_js(p, "__counts")
    others = [u for u in c["urls"] if "/api/agent/next" not in u]
    check(
        "hidden for 10 s: no timers, frames or requests but the command long-poll",
        c["raf"] == 0
        and c["interval"] == 0
        and c["timeout"] == 0
        and not others
        and c["fetch"] <= 1,
        json.dumps(c),
    )
    await p.js("setVisible(true)")

    # --- the side panel ---------------------------------------------------------------
    sent = await p.js("views.length")
    await app_js(p, "openSide('history'), 1")
    listed = await app_wait(
        p, "document.querySelectorAll('#side-list .row').length === 200"
    )
    check("history lists 200 rows", listed)
    scrolls = await app_js(
        p,
        "(() => { const l = $('side-list'); return l.scrollHeight > l.clientHeight + 100"
        " && document.scrollingElement.scrollHeight <= innerHeight + 1; })()",
    )
    check("a long history scrolls inside the panel, not the page", scrolls is True)
    narrower = await p.wait(
        f"views.slice({sent}).some((m) => m.op === 'rect' && m.rect[2] < innerWidth - 300)",
        3,
    )
    check("opening the panel moves the page view out of its way", narrower)
    await app_js(p, "$('side-search').value = 'zzz-nothing', renderSide(), 1")
    nothing = await app_wait(
        p,
        "!document.querySelector('#side-list .row')"
        " && /nothing/i.test($('side-list').textContent)",
    )
    check("a search with no match says so", nothing)
    await app_js(
        p, "openSide('bookmarks'), $('side-search').value = '', renderSide(), 1"
    )
    await app_js(p, "state.bookmarks = [], renderSide(), 1")
    empty = await app_wait(p, "/no bookmarks/i.test($('side-list').textContent)")
    check("no bookmarks has an empty state", empty)
    await app_js(p, "openSide('bookmarks'), 1")
    await app_js(
        p, "api('/api/state').then((b) => { state.bookmarks = b.bookmarks; return 1; })"
    )

    # --- a page in the tab, the star and notes ------------------------------------------
    tab = await app_js(p, "state.active")
    await p.js(
        "viewEvent("
        + json.dumps(
            {
                "event": "state",
                "id": tab,
                "url": "https://example.com/",
                "title": "Example",
                "loading": False,
                "progress": 1,
                "back": False,
                "forward": False,
            }
        )
        + ")"
    )
    await app_wait(p, "activeTab().url === 'https://example.com/'")
    await reset_counts(p)
    await app_js(p, "$('star').click(), $('star').click(), 1")
    await app_wait(p, "state.bookmarks.some((b) => b.url === 'https://example.com/')")
    await asyncio.sleep(0.8)
    c = await app_js(p, "__counts")
    posts = [u for u in c["urls"] if "/api/bookmarks" in u]
    starred = await app_js(p, "$('star').textContent")
    check(
        "a double click on the star bookmarks once",
        len(posts) == 1 and starred == "★",
        f"{posts} {starred}",
    )
    above = await app_js(
        p,
        "(() => { note('Saved file.pdf to Downloads'); const n = $('note').getBoundingClientRect();"
        " const v = $('viewport').getBoundingClientRect();"
        " return n.height > 0 && n.bottom <= v.top + 1; })()",
    )
    check(
        "a note shows above the page area, where a page cannot cover it", above is True
    )

    # --- reopen a closed tab ------------------------------------------------------------
    await p.js(
        "viewEvent({event: 'open', id: "
        + json.dumps(tab)
        + ", url: 'https://reopen.example.net/'})"
    )
    await app_wait(p, "state.tabs.length === 2")
    await app_js(p, "closeTab(activeTab().id), 1")
    await app_wait(p, "state.tabs.length === 1")
    sent = await p.js("views.length")
    await app_js(
        p,
        "document.dispatchEvent(new KeyboardEvent('keydown',"
        " {key: 'T', ctrlKey: true, shiftKey: true, bubbles: true})), 1",
    )
    back = await app_wait(
        p,
        "state.tabs.length === 2 && activeTab().url === 'https://reopen.example.net/'",
    )
    made = await p.js(
        f"views.slice({sent}).some((m) => m.op === 'create' && m.url === 'https://reopen.example.net/')"
    )
    check("Ctrl+Shift+T reopens the tab closed last", back and made)
    await app_js(
        p,
        "document.dispatchEvent(new KeyboardEvent('keydown',"
        " {key: 't', ctrlKey: true, bubbles: true})), 1",
    )
    plain = await app_wait(p, "state.tabs.length === 3 && isBlank(activeTab().url)")
    check("Ctrl+T still opens a new tab", plain)
    await app_js(p, "closeTab(activeTab().id), 1")

    # --- many tabs in a narrow window: the open tab and the + stay in view ------------------
    await p.call(
        "Emulation.setDeviceMetricsOverride",
        width=760,
        height=860,
        deviceScaleFactor=1,
        mobile=False,
    )
    await asyncio.sleep(0.5)
    await app_js(
        p, "for (let i = 0; i < 12; i++) newTab(`https://many${i}.example.com/`), 1"
    )
    last = await app_js(p, IN_VIEW)
    if shot_dir:
        await app_js(
            p, "note('Could not save the bookmark: the server is not answering'), 1"
        )
        await asyncio.sleep(0.4)
        await shoot(p, shot_dir, "many-tabs-note", 760)
    await app_js(p, "selectTab(state.tabs[0].id), 1")
    first = await app_js(p, IN_VIEW)
    check(
        "with many tabs at 760 px the open tab and the + stay in view",
        last == [True, True] and first == [True, True],
        f"last {last}, first {first}",
    )
    await app_js(p, "state.tabs.slice(2).forEach((t) => closeTab(t.id)), 1")
    await p.call("Emulation.clearDeviceMetricsOverride")

    # --- the server goes away and comes back ----------------------------------------------
    await reset_counts(p)
    backend.stop()
    await asyncio.sleep(10)
    first = (await app_js(p, "__counts"))["fetch"]
    calm = await app_js(p, "!$('offline').classList.contains('hidden')")
    check("with the server gone, the page says so calmly", calm is True)
    sent = await p.js("views.length")
    await app_js(
        p,
        "$('address').value = 'https://typed.example.org/x', $('address-form').requestSubmit(), 1",
    )
    typed = await p.wait(
        f"views.slice({sent}).some((m) => m.op === 'navigate' && m.url === 'https://typed.example.org/x')",
        3,
    )
    check("a typed web address still opens while the server is gone", typed)
    await asyncio.sleep(20)
    total = (await app_js(p, "__counts"))["fetch"]
    later = total - first
    check(
        "the command loop backs off while the server is gone",
        later / 20 < first / 10 and total <= 8,
        f"0-10 s: {first}, 10-30 s: {later}",
    )
    backend.start()
    recovered = await app_wait(
        p,
        "$('offline').classList.contains('hidden') && state.engines !== undefined",
        40,
    )
    check("the page recovers by itself when the server is back", recovered)
    await reset_counts(p)
    await asyncio.sleep(4)
    c = await app_js(p, "__counts")
    polls = [u for u in c["urls"] if "/api/agent/next" in u]
    check("after recovery one command loop runs, not two", len(polls) <= 1, str(polls))

    # --- a boot with the server away keeps the saved tabs ---------------------------------
    saved = [f"https://saved{i}.example.com/" for i in range(3)]
    await asyncio.sleep(1)
    tabs = json.dumps({"tabs": [{"url": u, "title": u} for u in saved], "active": 1})
    await app_js(
        p, f"api('/api/session', {{method: 'POST', body: '{tabs}'}}).then(() => 1)"
    )
    await app_js(p, "sessionStorage.setItem('__down', '1'), location.reload(), 1")
    await asyncio.sleep(1)
    away = await app_wait(
        p,
        "typeof state === 'object' && state.tabs.length === 1"
        " && !$('offline').classList.contains('hidden')",
        10,
    )
    await asyncio.sleep(2)  # the session timer runs while the saved tabs are missing
    await app_js(p, "sessionStorage.removeItem('__down'), 1")
    t0 = time.monotonic()
    back = await app_wait(
        p, "$('offline').classList.contains('hidden') && state.loaded === true", 15
    )
    took = time.monotonic() - t0
    check(
        "the strip clears within one backoff step of the server answering",
        away and back and took < 9,
        f"{took:.1f} s",
    )
    now = await app_js(
        p, "[state.tabs.map((t) => t.url), state.tabs.indexOf(activeTab())]"
    )
    check(
        "after a boot with the server away, the saved tabs come back",
        now == [saved, 1],
        str(now),
    )
    await asyncio.sleep(2)
    kept = await app_js(
        p, "api('/api/state').then((b) => b.session.tabs.map((t) => t.url))"
    )
    check("... and the saved tabs are not written over", kept == saved, str(kept))


async def main() -> int:
    shot_dir = None
    if "--shots" in sys.argv:
        shot_dir = Path(sys.argv[sys.argv.index("--shots") + 1]).resolve()
    box = APP / "tests" / f".ui-{os.getpid()}"
    box.mkdir()
    data = box / "data"
    seed(data)
    port = int(sys.argv[sys.argv.index("--port") + 1]) if "--port" in sys.argv else 0
    backend = Backend(data, port)
    try:
        backend.start()
        async with chrome_page(box, size="1500,860") as p:
            await run(p, backend, box, shot_dir)
    finally:
        try:
            backend.stop()
        finally:
            shutil.rmtree(box, ignore_errors=True)
    fails = [r for r in results if r.startswith("FAIL")]
    print(f"\n{len(results) - len(fails)} passed, {len(fails)} failed")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
