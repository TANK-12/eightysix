"""Afterglow in headless Chrome: the shelf, every curio, and screenshots.

    .venv/bin/python tests/check_ui.py                    every curio
    .venv/bin/python tests/check_ui.py --only crucible    one curio (repeatable)
    .venv/bin/python tests/check_ui.py --out DIR          screenshots (default
                                                          /tmp/afterglow-shots)
    .venv/bin/python tests/check_ui.py --voice            also have Forge's voice
                                                          service read a page aloud

Not collected by pytest (it needs the Flatpak Chrome). Runs the app on a free
port with a temp data folder (never ~/ForgeGameData), loads the shelf, writes
a logbook page through the dialog, then opens each curio by its #<id> address
in Simple and in Advanced mode, opens each of its seed keepsakes, and leaves
with Esc. A FAIL is any page error (uncaught, rejected or console.error), a
curio that did not start, a blank stage canvas, a blank shelf preview, or Esc
that never gets back to the shelf. Screenshots are JPEG. Prints PASS/FAIL
lines (INFO for frame timing), exits non-zero on a FAIL.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import os
import shutil
import sys
import tempfile
import urllib.request
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP.parents[1] / "tests"))
from cdp_driver import Page, chrome_page, serve  # noqa: E402

results: list[str] = []

ERRORS = r"""
window.__errs = [];
addEventListener('error', (e) => __errs.push('error: ' + (e.message || (e.target && (e.target.src || e.target.href)) || e)), true);
addEventListener('unhandledrejection', (e) => __errs.push('rejection: ' + ((e.reason && e.reason.stack) || e.reason)));
{ const ce = console.error.bind(console);
  console.error = (...a) => { __errs.push('console: ' + a.map((x) => (x && x.stack) || String(x)).join(' ')); ce(...a); }; }
"""

# The spread of brightness over a canvas, sampled small: 0 means one flat colour.
SPREAD = r"""
window.__spread = (c) => {
  try {
    const s = document.createElement('canvas'); s.width = 64; s.height = 36;
    const g = s.getContext('2d'); g.drawImage(c, 0, 0, 64, 36);
    const d = g.getImageData(0, 0, 64, 36).data;
    let lo = 765, hi = 0;
    for (let i = 0; i < d.length; i += 4) { const v = d[i] + d[i + 1] + d[i + 2]; lo = Math.min(lo, v); hi = Math.max(hi, v); }
    return hi - lo;
  } catch (e) { return -1; }
};
window.__biggest = (root) => [...root.querySelectorAll('canvas')]
  .sort((a, b) => b.clientWidth * b.clientHeight - a.clientWidth * a.clientHeight)[0] || null;
"""

FRAMES = r"""
new Promise((done) => {
  const ts = [];
  const f = (t) => { ts.push(t); if (ts.length < 41) requestAnimationFrame(f); else done((ts[40] - ts[0]) / 40); };
  requestAnimationFrame(f);
})
"""


def check(name: str, ok: bool, extra: object = "") -> bool:
    note = f" :: {extra}" if extra != "" and not ok else ""
    results.append(f"{'PASS' if ok else 'FAIL'} :: {name}{note}")
    return ok


def info(text: str) -> None:
    results.append(f"INFO :: {text}")


async def shot(page: Page, path: Path) -> None:
    r = await page.call("Page.captureScreenshot", format="jpeg", quality=82)
    path.write_bytes(base64.b64decode(r["data"]))


async def errors(page: Page) -> list[str]:
    errs = await page.js("JSON.stringify(window.__errs.splice(0))")
    return json.loads(errs or "[]")


async def shelf(
    page: Page, base: str, out: Path, curios: list[dict], only: list[str], voice: bool
) -> None:
    await page.go(base + "/")
    want = len(curios) + 1  # every curio and the empty slot
    ok = await page.wait(
        f"document.querySelectorAll('#shelf .card').length === {want}", 8
    )
    check("shelf shows every curio and the empty slot", ok)
    await page.wait("document.querySelector('#pages .page, #pages .empty')", 5)
    await asyncio.sleep(1.2)  # previews draw a frame after layout
    spreads = await page.js(
        "[...document.querySelectorAll('#shelf .card[data-curio] canvas')].map(__spread)"
    )
    blank = [
        c["id"]
        for c, s in zip(curios, spreads or [])
        if s is not None and s < 12 and (not only or c["id"] in only)
    ]
    check("every shelf preview draws something", not blank, blank)
    await asyncio.sleep(1.0)  # keepsake pictures draw after their fetches
    await shot(page, out / "shelf.jpg")
    e = await errors(page)
    if only:  # other curios on the shelf may be half-built by another session
        if e:
            info(f"shelf page errors (not failed with --only): {e}")
    else:
        check("shelf has no page errors", not e, e)

    # a logbook page through the dialog: a write with X-Forge from the real page
    await page.js("document.getElementById('write-page').click()")
    await page.js(
        "document.getElementById('page-title').value = 'A test page';"
        "document.getElementById('page-body').value = 'First line.\\n\\nSecond paragraph.'"
    )
    await page.js("document.getElementById('page-save').click()")
    ok = await page.wait(
        "[...document.querySelectorAll('#pages .page h4')].some((h) => h.textContent === 'A test page')",
        5,
    )
    check("a logbook page written from the dialog shows up", ok)
    test_page = "[...document.querySelectorAll('#pages .page')].find((n) => n.querySelector('h4').textContent === 'A test page')"
    has_read = await page.js(f"!!({test_page} || document).querySelector('.read')")
    check("logbook pages offer Read aloud", has_read)
    if voice and has_read:
        await page.js(f"{test_page}.querySelector('.read').click()")
        said = await page.wait(
            "performance.getEntriesByType('resource').some((r) => r.name.includes(':8467/api/tts') && r.responseStatus === 200)",
            90,
        )
        check("Read aloud gets speech from Forge's voice service", said)
        back = await page.wait(
            f"{test_page}.querySelector('.read').textContent === 'Read aloud'", 30
        )
        check("the Read aloud button comes back when the line ends", back)
    await page.js("location.hash = '#no-such-curio'")
    ok = await page.wait(
        "location.hash === '' && !document.getElementById('shelf-view').hidden", 4
    )
    check("an unknown curio address goes back to the shelf", ok)
    check(
        "logbook and bad address raise no page errors", not (e := await errors(page)), e
    )


# [how many .adv elements the curio has, how many of them are on screen]
ADV = (
    "(() => { const r = document.querySelector('.curio-root'); if (!r) return [0, 0];"
    " const all = [...r.querySelectorAll('.adv')];"
    " return [all.length, all.filter((e) => e.getClientRects().length > 0).length]; })()"
)


async def curio(page: Page, base: str, out: Path, meta: dict) -> None:
    cid = meta["id"]
    root = f"document.querySelector('.curio-root[data-curio=\"{cid}\"]')"
    await page.js(
        f"document.querySelector('#mode-seg [data-mode=simple]').click(); location.hash = '#{cid}'"
    )
    started = await page.wait(f"{root} && {root}.children.length > 0", 8)
    failed = await page.js("!!document.querySelector('.stage-error')")
    check(
        f"{cid}: starts",
        started and not failed,
        await page.js("document.getElementById('stage').innerText.slice(0, 300)"),
    )
    stale = await page.js(
        "(() => { const t = document.getElementById('toast'); return !t.classList.contains('hidden') && t.textContent.includes('no curio called'); })()"
    )
    check(f"{cid}: no message left over from the shelf", not stale)
    await asyncio.sleep(1.8)
    spread = await page.js(
        f"(() => {{ const c = __biggest({root} || document); return c ? __spread(c) : null; }})()"
    )
    if spread is not None:
        check(f"{cid}: its biggest canvas is not blank", spread >= 12, spread)
    frame = await page.js(FRAMES)
    info(f"{cid}: {frame:.1f} ms per animation frame (headless, no GPU)")
    await shot(page, out / f"{cid}.jpg")
    check(f"{cid}: no page errors in Simple", not (e := await errors(page)), e)
    adv = await page.js(ADV)
    check(f"{cid}: Simple hides its advanced controls", adv[1] == 0, adv)

    await page.js("document.querySelector('#mode-seg [data-mode=advanced]').click()")
    await asyncio.sleep(0.8)
    await shot(page, out / f"{cid}-advanced.jpg")
    adv = await page.js(ADV)
    if adv[0]:
        check(f"{cid}: Advanced shows its advanced controls", adv[1] > 0, adv)
    check(f"{cid}: no page errors in Advanced", not (e := await errors(page)), e)
    await page.js("document.querySelector('#mode-seg [data-mode=simple]').click()")

    seeds = json.load(urllib.request.urlopen(f"{base}/api/keepsakes?curio={cid}"))
    seeds = [r for r in seeds["keepsakes"] if r["seed"]]
    for row in seeds:
        await page.js(f"location.hash = '#{cid}/{row['slug']}'")
        await asyncio.sleep(1.0)
        bad = await page.js(
            "(() => { const t = document.getElementById('toast'); return !t.classList.contains('hidden') && t.classList.contains('err') ? t.textContent : ''; })()"
        )
        e = await errors(page)
        check(f"{cid}: opens seed {row['slug']}", not bad and not e, bad or e)
    if seeds:
        await shot(page, out / f"{cid}-seed.jpg")
        await page.js("document.getElementById('drawer-btn').click()")
        ok = await page.wait(
            "document.querySelectorAll('#drawer-list .d-item').length > 0", 4
        )
        check(f"{cid}: the keepsake drawer lists its seeds", ok)
        squeezed = await page.js(
            "[...document.querySelectorAll('#drawer-list .d-item')].filter((d) => d.scrollHeight > d.clientHeight + 1).length"
        )
        check(f"{cid}: no drawer card is squeezed (names show)", squeezed == 0, squeezed)
        await shot(page, out / f"{cid}-drawer.jpg")

    for _ in range(4):
        await page.key("Escape", "Escape", 0, 27)
        if await page.wait("!document.getElementById('shelf-view').hidden", 1.2):
            break
    check(
        f"{cid}: Esc gets back to the shelf",
        await page.js("!document.getElementById('shelf-view').hidden"),
    )
    check(f"{cid}: no page errors on the way out", not (e := await errors(page)), e)


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", action="append", default=[])
    parser.add_argument("--out", default="/tmp/afterglow-shots")
    parser.add_argument("--size", default="1400,900")
    parser.add_argument("--voice", action="store_true")
    opts = parser.parse_args()
    out = Path(opts.out)
    out.mkdir(parents=True, exist_ok=True)
    sandbox = Path(tempfile.mkdtemp(prefix="afterglow-ui-"))
    env = {
        "AFTERGLOW_DATA": str(sandbox / "data"),
        "FORGE_SHARED_DIR": str(APP.parents[1] / "shared"),
    }
    try:
        with serve(APP, env) as port:
            base = f"http://127.0.0.1:{port}"
            listing = json.load(urllib.request.urlopen(f"{base}/api/curios"))
            problems = [
                p
                for p in listing["problems"]
                if not opts.only or p.split(":")[0] in opts.only
            ]
            check("no curio reports a problem", not problems, problems)
            curios = listing["curios"]
            missing = [c for c in opts.only if c not in {m["id"] for m in curios}]
            check("every --only curio is on the shelf", not missing, missing)
            async with chrome_page(
                sandbox,
                size=opts.size,
                extra_args=("--autoplay-policy=no-user-gesture-required",),
            ) as page:
                await page.call(
                    "Page.addScriptToEvaluateOnNewDocument", source=ERRORS + SPREAD
                )
                await shelf(page, base, out, curios, opts.only, opts.voice)
                for meta in curios:
                    if not opts.only or meta["id"] in opts.only:
                        await curio(page, base, out, meta)
    finally:
        shutil.rmtree(sandbox, ignore_errors=True)
    print("\n".join(results))
    print(f"screenshots: {out}")
    return 1 if any(r.startswith("FAIL") for r in results) else 0


if __name__ == "__main__":
    os.environ.setdefault("PYTHONUNBUFFERED", "1")
    sys.exit(asyncio.run(main()))
