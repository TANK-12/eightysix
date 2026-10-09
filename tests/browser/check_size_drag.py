"""Drag the App size and Text size sliders like a hand does, and log what happens.

    apps/terminal/.venv/bin/python tests/browser/check_size_drag.py [--shots DIR] [--json OUT]

Emerson (2026-10-07): "when I change the size it will keep switching ... also
just make it faster". App size is WebKit page zoom on the one view that holds
the hub and every app, so a slider that applies it mid-drag rescales itself
under a pointer that has not moved, the next pointer move reads another value,
and the page zooms again.

This loads a copy of the REAL hub/index.html with the REAL Settings app
mounted in it (served from a throwaway config, never Emerson's), then drags
with real CDP mouse events: in the hub's Aa panel and in Settings > Size, App
size and Text size each. forge.py's page zoom is played by CSS zoom on the
hub's root, applied a tick after the hub asks, as the GTK side does; the
pointer stays on the same screen pixel while the page scales under it, exactly
as on screen. For every drag it logs each value the slider took, each zoom
asked for and applied, each save, each theme broadcast to the apps, the time
spent in applyTheme and how long each pointer move took to be handled.

A drag passes when the slider's values only ever move one way (no
flip-flop), the zoom changes once and is saved once, on release.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import sys
import tempfile
import time
from pathlib import Path

FORGE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(FORGE / "tests"))
sys.path.insert(0, str(FORGE / "shared"))

from cdp_driver import chrome_page, serve  # noqa: E402

import forge_theme  # noqa: E402

WIDTH, HEIGHT = 1400, 900
STEPS = 40  # pointer moves per drag
STEP_MS = 16  # one per frame, a steady hand
HOLD = 20  # moves of a pixel either way at the end, before letting go

# Runs in every frame before the page's own scripts. In the hub (file://) it
# stands in for forge.py: zoom requests become CSS zoom on the root one tick
# later; saves are logged. In Settings (http) it logs fetches. Both log every
# range slider's input event.
STUB = r"""
(() => {
  const log = [];
  window.__sizeLog = log;
  const now = () => Math.round(performance.now() * 10) / 10;
  const top = location.protocol === "file:";
  // Settings is another origin: its entries go up to the hub's log by message.
  const put = top ? (e) => log.push(e) : (e) => parent.postMessage({ __size: e }, "*");
  document.addEventListener("input", (e) => {
    const t = e.target;
    if (t && t.type === "range") put({ t: now(), input: t.dataset.key || t.id, value: Number(t.value) });
  }, true);
  if (top) {
    window.__sizeGeo = null;
    window.__sizeReady = false;
    addEventListener("message", (e) => {
      const m = e.data;
      if (!m || typeof m !== "object") return;
      if (m.__size) log.push(Object.assign({ app: 1 }, m.__size));
      if (m.__sizeGeo) window.__sizeGeo = m.__sizeGeo;
      if (m.__sizeReady) window.__sizeReady = true;
    });
    window.webkit = { messageHandlers: { forge: { postMessage(m) {
      const msg = JSON.parse(m);
      if ("zoom" in msg) {
        log.push({ t: now(), zoom: msg.zoom });
        setTimeout(() => {
          document.documentElement.style.zoom = String(msg.zoom);
          log.push({ t: now(), zoomed: msg.zoom });
        }, 0);
      }
      if (msg.settings) log.push({ t: now(), save: msg.settings });
    } } } };
  } else {
    const real = window.fetch;
    window.fetch = (url, opts) => {
      if (String(url).includes("/api/settings")) {
        const method = (opts && opts.method) || "GET";
        put({ t: now(), fetch: method, body: opts && opts.body ? JSON.parse(opts.body) : null });
      }
      return real(url, opts);
    };
    const ready = setInterval(() => {
      if (!document.querySelector("input[type=range][data-key=ui_scale]")) return;
      clearInterval(ready);
      parent.postMessage({ __sizeReady: 1 }, "*");
    }, 100);
    // The harness asks where a slider is on the screen.
    addEventListener("message", (e) => {
      const key = e.data && e.data.__sizeProbe;
      if (!key) return;
      const r = document.querySelector(`input[type=range][data-key="${key}"]`);
      // Settings shows one section at a time: pick the slider's from the nav.
      const sec = r.closest("[data-section]");
      const nav = sec && [...document.querySelectorAll("button[data-section]")]
        .find((b) => b.dataset.section === sec.dataset.section);
      if (nav && !r.getBoundingClientRect().width) nav.click();
      r.scrollIntoView({ block: "center" });
      const b = r.getBoundingClientRect();
      parent.postMessage({ __sizeGeo: { left: b.left, top: b.top, width: b.width, height: b.height,
        innerWidth, min: +r.min, max: +r.max, value: +r.value } }, "*");
    });
  }
})();
"""

# Wraps the hub's applyTheme and sendTheme once it has loaded, to count and
# time them. Function declarations in a classic script are globals, so the
# hub's own calls go through the wrappers.
WRAP = r"""
(() => {
  const log = window.__sizeLog;
  const now = () => Math.round(performance.now() * 10) / 10;
  const apply = window.applyTheme, send = window.sendTheme;
  window.applyTheme = function (next) {
    const t0 = performance.now();
    const r = apply.apply(this, arguments);
    log.push({ t: now(), applyTheme: Object.keys(next || {}).join(","), ms: performance.now() - t0 });
    return r;
  };
  window.sendTheme = function () { log.push({ t: now(), broadcast: 1 }); return send.apply(this, arguments); };
  return true;
})()
"""


def stage(sandbox: Path, settings_port: int) -> Path:
    """A hub copy with the shared scripts it loads and fixture status/theme."""
    hub = sandbox / "hub"
    shutil.copytree(
        FORGE / "hub", hub, ignore=shutil.ignore_patterns("status.*", "theme.js")
    )
    shared = sandbox / "shared"
    shared.mkdir()
    for f in (FORGE / "shared").iterdir():
        if f.is_file() and f.suffix in (".js", ".css"):
            shutil.copy(f, shared)
    shutil.copytree(FORGE / "shared/glass", shared / "glass")
    status = {
        "settings": {
            "available": True,
            "state": "up",
            "label": "Settings",
            "tagline": "settings",
            "url": f"http://127.0.0.1:{settings_port}/",
            "accent": "",
            "icon": "S",
            "role": "settings",
            "fullscreen": "",
        }
    }
    (hub / "status.js").write_text(f"window.FORGE_STATUS = {json.dumps(status)};\n")
    theme = {
        "accent": "#6ea8fe",
        "accent_2": "#4f8cf7",
        "on_accent": "#0b1220",
        "animations": False,
        "dock_size": 46,
        "tile_width": 236,
        "ui_scale": 1.0,
        "text_scale": 1.0,
        "icon_scale": 1.0,
        "size_presets": forge_theme.SIZE_PRESETS,
        "particles": False,
        "surfaces": {
            "bg": "#101418",
            "panel": "#18202a",
            "panel_2": "#1f2833",
            "border": "#2c3a48",
            "text": "#eef3f8",
            "muted": "#a9b8c8",
        },
    }
    (hub / "theme.js").write_text(f"window.FORGE_THEME = {json.dumps(theme)};\n")
    return hub / "index.html"


async def session_call(page, session: str, method: str, **params):
    """A DevTools call into another target (the Settings frame runs out of
    process, so the hub's session cannot reach it)."""
    page.n += 1
    mid = page.n
    await page.ws.send(
        json.dumps(
            {"id": mid, "method": method, "params": params, "sessionId": session}
        )
    )
    while True:
        msg = json.loads(await page.ws.recv())
        if msg.get("id") == mid:
            if "error" in msg:
                raise RuntimeError(msg["error"])
            return msg.get("result", {})


async def stub_settings_frame(page) -> None:
    """Put the logging stub into the Settings frame once it exists."""
    for _ in range(150):
        targets = (await page.call("Target.getTargets"))["targetInfos"]
        frame = next(
            (t for t in targets if t["type"] == "iframe" and "127.0.0.1" in t["url"]),
            None,
        )
        if frame:
            break
        await asyncio.sleep(0.1)
    else:
        raise RuntimeError("the Settings frame never appeared")
    session = (
        await page.call(
            "Target.attachToTarget", targetId=frame["targetId"], flatten=True
        )
    )["sessionId"]
    await session_call(page, session, "Runtime.evaluate", expression=STUB)


def flips(values: list[float]) -> int:
    """How many times the slider's value turned back on itself."""
    turns, last_dir = 0, 0
    for a, b in zip(values, values[1:]):
        d = (b > a) - (b < a)
        if d and last_dir and d != last_dir:
            turns += 1
        if d:
            last_dir = d
    return turns


async def drag(page, where: str, key: str, target: float) -> dict:
    """Press on the slider's thumb, move to `target` in STEPS frames, let go.

    `where` is "hub" (the Aa panel) or "settings" (inside the Settings frame).
    Returns the summary of everything logged from press to 1.5 s after release.
    """
    if where == "hub":
        geo = await page.js(f"""(() => {{
              const r = $("sz-{key}");
              const b = r.getBoundingClientRect();
              return {{ left: b.left, top: b.top, width: b.width, height: b.height,
                        min: +r.min, max: +r.max, value: +r.value }};
            }})()""")
    else:
        await page.js(
            f"window.__sizeGeo = null; document.querySelector('.workspace iframe[src*=\"127.0.0.1\"]')"
            f".contentWindow.postMessage({{ __sizeProbe: '{key}' }}, '*'); true"
        )
        await page.wait("!!window.__sizeGeo", 5)
        await asyncio.sleep(0.2)
        await page.js(
            f"window.__sizeGeo = null; document.querySelector('.workspace iframe[src*=\"127.0.0.1\"]')"
            f".contentWindow.postMessage({{ __sizeProbe: '{key}' }}, '*'); true"
        )
        await page.wait("!!window.__sizeGeo", 5)
        geo = await page.js("""(() => {
              const f = document.querySelector('.workspace iframe[src*="127.0.0.1"]');
              const fb = f.getBoundingClientRect(), g = window.__sizeGeo, k = fb.width / g.innerWidth;
              return { left: fb.left + g.left * k, top: fb.top + g.top * k, width: g.width * k,
                       height: g.height * k, min: g.min, max: g.max, value: g.value };
            })()""")
    span = geo["max"] - geo["min"]
    # WebKit and Chrome both map the pointer across the track less a thumb.
    thumb = 16

    def x_for(v: float) -> float:
        return (
            geo["left"] + thumb / 2 + (v - geo["min"]) / span * (geo["width"] - thumb)
        )

    y = geo["top"] + geo["height"] / 2
    x0, x1 = x_for(geo["value"]), x_for(target)
    await page.js("window.__sizeLog.length = 0; true")
    lag = []
    t0 = time.monotonic()
    await page.call("Input.dispatchMouseEvent", type="mouseMoved", x=x0, y=y)
    await page.call(
        "Input.dispatchMouseEvent",
        type="mousePressed",
        x=x0,
        y=y,
        button="left",
        buttons=1,
        clickCount=1,
    )
    for i in range(1, STEPS + 1):
        x = x0 + (x1 - x0) * i / STEPS
        s = time.monotonic()
        await page.call(
            "Input.dispatchMouseEvent",
            type="mouseMoved",
            x=x,
            y=y,
            button="left",
            buttons=1,
        )
        lag.append((time.monotonic() - s) * 1000)
        await asyncio.sleep(STEP_MS / 1000)
    # A hand never holds perfectly still: a pixel either way, for a moment.
    for i in range(HOLD):
        x = x1 + (1 if i % 2 else -1)
        s = time.monotonic()
        await page.call(
            "Input.dispatchMouseEvent",
            type="mouseMoved",
            x=x,
            y=y,
            button="left",
            buttons=1,
        )
        lag.append((time.monotonic() - s) * 1000)
        await asyncio.sleep(STEP_MS / 1000)
    s = time.monotonic()
    await page.call(
        "Input.dispatchMouseEvent",
        type="mouseReleased",
        x=x1,
        y=y,
        button="left",
        buttons=0,
        clickCount=1,
    )
    release_ms = (time.monotonic() - s) * 1000
    drag_ms = (time.monotonic() - t0) * 1000
    await asyncio.sleep(1.5)  # Settings saves 180 ms after release, then tells the hub
    every = await page.js("window.__sizeLog.slice()")
    hub = [e for e in every if not e.get("app")]
    app = [e for e in every if e.get("app")]
    slider = [
        e["value"]
        for e in (hub if where == "hub" else app)
        if e.get("input") in (key, f"sz-{key}")
    ]
    zooms = [e["zoom"] for e in hub if "zoom" in e]
    saves = [e["save"] for e in hub if "save" in e] + [
        e["body"] for e in app if e.get("fetch") == "POST"
    ]
    final = await page.js("Number(theme.%s)" % key)
    zoom_now = await page.js("Number(document.documentElement.style.zoom || 1)")
    return {
        "where": where,
        "key": key,
        "from": geo["value"],
        "target": target,
        "slider_values": slider,
        "distinct_values": len(set(slider)),
        "flip_flops": flips(slider),
        "zoom_requests": zooms,
        "saves": saves,
        "settings_refetches": sum(1 for e in app if e.get("fetch") == "GET"),
        "applyTheme_calls": sum(1 for e in hub if "applyTheme" in e),
        "applyTheme_ms": round(sum(e["ms"] for e in hub if "applyTheme" in e), 1),
        "broadcasts": sum(1 for e in hub if "broadcast" in e),
        "move_lag_ms_mean": round(sum(lag) / len(lag), 2),
        "move_lag_ms_max": round(max(lag), 2),
        "release_ms": round(release_ms, 2),
        "drag_ms": round(drag_ms),
        "final_theme_value": final,
        "final_zoom": zoom_now,
    }


async def run(shots: Path | None) -> list[dict]:
    sandbox = Path(tempfile.mkdtemp(prefix="forge-size-drag-"))
    env = {
        "FORGE_CONFIG": str(sandbox / "settings.json"),
        "FORGE_CACHE": str(sandbox / "cache"),
        "FORGE_WALLPAPERS": str(sandbox / "walls"),
        "FORGE_AUTOSTART": str(sandbox / "autostart.desktop"),
    }
    (sandbox / "walls").mkdir()
    results = []
    try:
        with serve(FORGE / "apps/settings", env) as port:
            index = stage(sandbox, port)
            args = (
                "--disable-web-security",
                "--disable-site-isolation-trials",
                "--allow-file-access-from-files",
            )
            async with chrome_page(sandbox, f"{WIDTH},{HEIGHT}", args) as page:
                await page.call("Page.addScriptToEvaluateOnNewDocument", source=STUB)
                for where, key, targets in (
                    ("hub", "ui_scale", (1.35, 1.1)),
                    ("hub", "text_scale", (1.35, 1.1)),
                    ("settings", "ui_scale", (1.35, 1.1)),
                    ("settings", "text_scale", (1.35, 1.1)),
                ):
                    (sandbox / "settings.json").write_text("{}")
                    await page.go(index.as_uri())
                    if not await page.wait(
                        "typeof Sizes === 'object' && typeof openSettings === 'function'",
                        10,
                    ):
                        raise RuntimeError("hub never booted")
                    await page.js(WRAP)
                    # Settings mounted in both cases: a hub drag reaches it too.
                    await page.js("openSettings(); true")
                    await stub_settings_frame(page)
                    if not await page.wait("window.__sizeReady", 15):
                        raise RuntimeError("Settings never mounted")
                    await asyncio.sleep(0.5)
                    if where == "hub":
                        await page.js("Sizes.panel(true); true")
                        await asyncio.sleep(0.2)
                    for n, target in enumerate(targets):
                        r = await drag(page, where, key, target)
                        results.append(r)
                        if shots:
                            shots.mkdir(parents=True, exist_ok=True)
                            await page.screenshot(shots / f"{where}-{key}-{n}.png")
    finally:
        shutil.rmtree(sandbox, ignore_errors=True)
    return results


def verdict(r: dict) -> list[str]:
    name = f"{r['where']} {r['key']} {r['from']}->{r['target']}"
    zoom_key = r["key"] == "ui_scale"
    lines = [
        (
            r["flip_flops"] == 0,
            f"{name}: the slider only moves one way",
            f"{r['flip_flops']} turns in {r['slider_values']}",
        ),
        (
            len(r["saves"]) == 1,
            f"{name}: saved once, on release",
            f"{len(r['saves'])} saves",
        ),
        (
            abs(r["final_theme_value"] - r["target"]) < 0.001,
            f"{name}: ends on the value let go at",
            f"{r['final_theme_value']} vs {r['target']}",
        ),
    ]
    if zoom_key:
        lines.append(
            (
                len(r["zoom_requests"]) == 1,
                f"{name}: the page zooms once",
                f"{len(r['zoom_requests'])} zoom requests",
            )
        )
    else:
        lines.append(
            (not r["zoom_requests"], f"{name}: no zoom at all", str(r["zoom_requests"]))
        )
    return [
        ("PASS" if ok else "FAIL") + f" :: {what} :: {extra}"
        for ok, what, extra in lines
    ]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--shots", type=Path)
    ap.add_argument("--json", type=Path)
    a = ap.parse_args()
    results = asyncio.run(run(a.shots))
    out = []
    for r in results:
        brief = {k: v for k, v in r.items() if k not in ("slider_values", "saves")}
        print(json.dumps(brief))
        out += verdict(r)
    print("\n".join(out))
    if a.json:
        a.json.write_text(json.dumps(results, indent=1))
    return 1 if any(line.startswith("FAIL") for line in out) else 0


if __name__ == "__main__":
    sys.exit(main())
