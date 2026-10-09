"""Drive the AI Studio page in headless Chrome against the stand-in backend.

    .venv/bin/python tests/check_ui.py [shots-folder]

Not collected by pytest (it needs the Flatpak Chrome). It starts
tests/check_ui_stub.py on a free port in 9021-9030 (never Emerson's live
AI Studio on 8430), then checks the page at 1100, 760 and 1920 px wide:
plain model cards, the download dialog with sizes and free space, the kind
refusal, live progress and Cancel, one request per click, the world player,
calm offline retries, resting while hidden, readable text (contrast, no
text under 14 px, no all-caps words). Screenshots go to the shots folder
(default /tmp/ai-studio-ui/shots). Prints PASS/FAIL lines, exits 1 on a FAIL.
"""

from __future__ import annotations

import asyncio
import json
import re
import shutil
import socket
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP.parents[1] / "tests"))

from cdp_driver import (
    Page,
    chrome_page,
    wait_http,
)  # noqa: E402  # pyright: ignore[reportMissingImports]

BOX = Path("/tmp/ai-studio-ui")
SHOTS = Path(sys.argv[1]) if len(sys.argv) > 1 else BOX / "shots"
TECHNICAL = re.compile(
    r"\d+(\.\d+)?\s*(px|gb|mb|kb)\b|\b(sd1\.5|sdxl|vae|lora|cfg|unet|gguf|safetensors|vram|fp16|q4|q8)\b",
    re.I,
)
results: list[str] = []


def check(name: str, ok: bool, extra: object = "") -> None:
    results.append(
        f"{'PASS' if ok else 'FAIL'} :: {name}{' :: ' + str(extra) if extra and not ok else ''}"
    )


def free_port() -> int:
    for port in range(9021, 9031):
        with socket.socket() as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise RuntimeError("no free scratch port in 9021-9030")


# Readability audit of what is on screen: text under 14 px, contrast under
# 4.5:1 (3:1 for bold 18 px+), and all-caps words.
AUDIT = r"""(() => {
  const out = { small: [], contrast: [], caps: [] };
  const rgba = (s) => { const m = s.match(/[\d.]+/g) || [0,0,0,0]; return m.map(Number).concat([1]).slice(0, 4); };
  const lin = (c) => { c /= 255; return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4); };
  const lum = ([r, g, b]) => 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b);
  function under(el) {
    let layers = [];
    for (let n = el; n; n = n.parentElement) {
      const c = rgba(getComputedStyle(n).backgroundColor);
      if (c[3] > 0) { layers.push(c); if (c[3] >= 0.99) break; }
    }
    let base = [15, 17, 21];
    for (const c of layers.reverse()) base = base.map((v, i) => v * (1 - c[3]) + c[i] * c[3]);
    return base;
  }
  const ALLOW = new Set(["JPEG", "PNG", "AI", "NVIDIA", "AMD"]);
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  const seen = new Set();
  while (walker.nextNode()) {
    const t = walker.currentNode, el = t.parentElement;
    const text = t.textContent.trim();
    if (!text || !el || seen.has(el)) continue;
    if (el.closest(".forge-chrome-btn, .forge-close-btn, script, style, svg")) continue;
    const r = el.getBoundingClientRect();
    if (!r.width || !r.height || el.closest("[hidden]") || getComputedStyle(el).visibility === "hidden") continue;
    if (!el.getClientRects().length) continue;
    seen.add(el);
    const cs = getComputedStyle(el);
    const fs = parseFloat(cs.fontSize);
    if (fs < 14) out.small.push(`${fs}px: ${text.slice(0, 40)}`);
    if (el.closest("button:disabled")) continue;
    const fg = rgba(cs.color), bg = under(el);
    const mix = fg.slice(0, 3).map((v, i) => v * fg[3] + bg[i] * (1 - fg[3]));
    const a = lum(mix), b = lum(bg);
    const ratio = (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
    const big = fs >= 18.6 || (fs >= 14 && Number(cs.fontWeight) >= 700);
    if (ratio < (big ? 3 : 4.5)) out.contrast.push(`${ratio.toFixed(2)}: ${text.slice(0, 40)}`);
    for (const w of text.match(/\b[A-Z]{3,}\b/g) || []) if (!ALLOW.has(w)) out.caps.push(w);
  }
  return out;
})()"""


class Run:
    def __init__(self, p: Page, port: int) -> None:
        self.p, self.port = p, port
        self.base = f"http://127.0.0.1:{port}"

    def stub(self, path: str, method: str = "POST") -> dict:
        req = urllib.request.Request(self.base + path, method=method)
        return json.load(urllib.request.urlopen(req))

    def counts(self) -> dict:
        return self.stub("/__stats", "GET")

    async def size(self, w: int, h: int = 900) -> None:
        await self.p.call(
            "Emulation.setDeviceMetricsOverride",
            width=w,
            height=h,
            deviceScaleFactor=1,
            mobile=False,
        )

    async def open(self, section: str) -> None:
        # a fresh load every time (a hash-only change would keep the old page)
        self.loads = getattr(self, "loads", 0) + 1
        await self.p.go(f"{self.base}/?load={self.loads}#{section}")
        await self.wait("window.AS && AS.models && AS.models.loaded", 8)
        await asyncio.sleep(0.3)

    async def wait(self, expr: str, timeout: float = 5.0) -> bool:
        # !! so a found element counts (an element comes back as {} by value)
        return await self.p.wait(f"!!({expr})", timeout)

    async def click(self, sel: str) -> None:
        await self.p.js(f"document.querySelector({json.dumps(sel)}).click()")

    async def shot(self, name: str) -> None:
        await asyncio.sleep(0.35)  # let fades and images settle
        await self.p.screenshot(SHOTS / f"{name}.png")

    async def audit(self, where: str) -> None:
        a = await self.p.js(AUDIT)
        check(f"{where}: no text under 14 px", not a["small"], a["small"][:5])
        check(
            f"{where}: text contrast at least 4.5:1",
            not a["contrast"],
            a["contrast"][:5],
        )
        check(f"{where}: no all-caps words", not a["caps"], a["caps"][:5])

    async def dialog_text(self) -> str:
        await self.wait("document.querySelector('.forge-dialog')", 5)
        return await self.p.js("document.querySelector('.forge-dialog p').textContent")

    async def card(self, mid: str, expr: str):
        return await self.p.js(
            f"(() => {{ const c = document.querySelector('.model-card[data-id={json.dumps(mid)}]'); return c && ({expr}); }})()"
        )

    # ---------------- per width ----------------
    async def width_pass(self, w: int) -> None:
        tag = f"{w}px"
        self.stub("/__reset")
        await self.size(w)
        await self.open("image")
        check(
            f"{tag}: image section shows the model in use",
            "Anime -- General"
            in (
                await self.p.js(
                    "document.querySelector('#sec-image .model-line').textContent"
                )
            ),
        )
        overflow = await self.p.js("document.documentElement.scrollWidth - innerWidth")
        check(f"{tag}: nothing wider than the window", overflow <= 0, overflow)
        await self.audit(f"{tag} main")
        await self.shot(f"{w}-main")

        await self.click("#modelsBtn")
        await self.wait("document.querySelectorAll('.model-card').length > 0")
        for kind, name in (
            ("image", "images"),
            ("video", "video"),
            ("world", "worlds"),
        ):
            await self.click(f'#modelTabs button[data-value="{kind}"]')
            await self.wait(
                f"document.querySelector('#modelTabs').dataset.value === '{kind}' && document.querySelectorAll('.model-card').length > 0"
            )
            await asyncio.sleep(0.2)
            text = await self.p.js(
                "[...document.querySelectorAll('.model-card .name, .model-card .blurb, .model-card .note, .model-card .progress-text')].map(e => e.textContent).join(' | ')"
            )
            bad = TECHNICAL.findall(text)
            check(f"{tag} models/{kind}: cards carry no sizes or jargon", not bad, bad)
            await self.audit(f"{tag} models/{kind}")
            await self.shot(f"{w}-models-{name}")

        await self.click('#modelTabs button[data-value="image"]')
        await self.wait(
            "document.querySelector('.model-card[data-id=\"z-image-turbo\"]')"
        )
        before = self.counts()
        # two quick presses: one quote, one dialog
        await self.p.js(
            "(() => { const b = document.querySelector('.model-card[data-id=\"z-image-turbo\"] button[data-act=download]'); b.click(); b.click(); })()"
        )
        text = await self.dialog_text()
        await self.audit(f"{tag} download dialog")
        await self.shot(f"{w}-download-confirm")
        if w == 1100:
            after = self.counts()
            q = "GET /api/models/z-image-turbo/quote"
            check(
                "double press asks for one quote",
                after.get(q, 0) - before.get(q, 0) == 1,
                after.get(q),
            )
            check("confirm states the download size", "9.4 GB" in text, text)
            check("confirm states the free space", "81 GB free" in text, text)
            check(
                "confirm has no all-caps", not re.search(r"\b[A-Z]{3,}\b", text), text
            )
        await self.click(".forge-dialog .ok")
        ok = await self.wait(
            "document.querySelector('.model-card[data-id=\"z-image-turbo\"] .progress-bar')",
            6,
        )
        check(f"{tag}: progress bar appears after Download", ok)
        await self.shot(f"{w}-progress")
        if w == 1100:
            check(
                "one download request",
                self.counts().get("POST /api/models/z-image-turbo/download") == 1,
                self.counts(),
            )
            p1 = await self.card(
                "z-image-turbo", "c.querySelector('.progress-text').textContent"
            )
            await asyncio.sleep(2.6)
            p2 = await self.card(
                "z-image-turbo",
                "c.querySelector('.progress-text') && c.querySelector('.progress-text').textContent",
            )
            check("progress moves by itself", p1 != p2, f"{p1} -> {p2}")
            check(
                "progress shows a percentage, no sizes",
                bool(p1 and re.fullmatch(r"Downloading\.\.\. \d+%", p1)),
                p1,
            )
            await self.p.js(
                "document.querySelector('.model-card[data-id=\"z-image-turbo\"] button[data-act=cancel]').click()"
            )
            text = await self.dialog_text()
            check("cancel asks first", "Stop downloading" in text, text)
            await self.click(".forge-dialog .ok")
            ok = await self.wait(
                "(() => { const c = document.querySelector('.model-card[data-id=\"z-image-turbo\"]'); return c && /cancelled/.test(c.textContent) && c.querySelector('button[data-act=download]'); })()",
                6,
            )
            check("cancel stops it and offers Download again", ok)

            # the kind refusal
            await self.p.js(
                "document.querySelector('.model-card[data-id=\"flux-huge\"] button[data-act=download]').click()"
            )
            text = await self.dialog_text()
            buttons = await self.p.js(
                "document.querySelectorAll('.forge-dialog button').length"
            )
            check(
                "too big: refuses kindly", "won't fit" in text and "free" in text, text
            )
            check("too big: only an OK, no download offered", buttons == 1, buttons)
            await self.shot(f"{w}-download-refused")
            await self.click(".forge-dialog .ok")
            await asyncio.sleep(0.3)
            check(
                "too big: nothing was downloaded",
                "POST /api/models/flux-huge/download" not in self.counts(),
            )

            heavy = await self.p.js(
                "[...document.querySelectorAll('.model-card')].filter(c => c.textContent.includes('Large, probably too heavy for this laptop')).map(c => c.dataset.id).sort().join(',')"
            )
            check(
                "big models say they are probably too heavy",
                heavy == "flux-huge,qwen-image",
                heavy,
            )
            check(
                "can't-run model shows its note",
                bool(
                    await self.card(
                        "qwen-image",
                        "c.textContent.includes('Needs an engine update.')",
                    )
                ),
            )
            check(
                "can't-run model offers no Use this",
                not await self.card(
                    "qwen-image", "!!c.querySelector('button[data-act=activate]')"
                ),
            )

            # Use this, Delete
            await self.p.js(
                "document.querySelector('.model-card[data-id=\"realistic\"] button[data-act=activate]').click()"
            )
            ok = await self.wait(
                "(() => { const c = document.querySelector('.model-card[data-id=\"realistic\"]'); return c && c.textContent.includes('In use'); })()",
                5,
            )
            check("Use this switches the model", ok)
            line = await self.p.js(
                "document.querySelector('#sec-image .model-line').textContent"
            )
            check("the section line follows the switch", "Realistic" in line, line)
            await self.p.js(
                "document.querySelector('.model-card[data-id=\"meina\"] button[data-act=delete]').click()"
            )
            text = await self.dialog_text()
            check("delete asks first", "Delete Anime -- General" in text, text)
            await self.click(".forge-dialog .ok")
            ok = await self.wait(
                "(() => { const c = document.querySelector('.model-card[data-id=\"meina\"]'); return c && c.querySelector('button[data-act=download]'); })()",
                5,
            )
            check("delete removes it", ok)

            # a world model: Play, not Use this; Play opens the 3D worlds section
            await self.click('#modelTabs button[data-value="world"]')
            await self.wait(
                "document.querySelector('.model-card[data-id=\"world-walk\"] button[data-act=play]')"
            )
            check(
                "world card has no Use this",
                not await self.card(
                    "world-walk", "!!c.querySelector('button[data-act=activate]')"
                ),
            )
            check(
                "world that can't run has no Play",
                not await self.card(
                    "world-big", "!!c.querySelector('button[data-act=play]')"
                ),
            )
            await self.p.js(
                "document.querySelector('.model-card[data-id=\"world-walk\"] button[data-act=play]').click()"
            )
            ok = await self.wait(
                "!document.getElementById('sec-worlds').hidden && document.getElementById('modelsModal').hidden"
            )
            check("Play opens the 3D worlds section", ok)
            await self.click("#modelsBtn")

        await self.click("#closeModelsBtn")
        await self.open("edit")
        await self.audit(f"{tag} edit")
        await self.shot(f"{w}-edit")
        await self.open("video")
        await self.audit(f"{tag} video")
        await self.shot(f"{w}-video")
        await self.click('#videoWay button[data-value="warp"]')
        await asyncio.sleep(0.2)
        await self.audit(f"{tag} video warp")
        await self.shot(f"{w}-video-warp")
        await self.open("library")
        await self.wait("document.querySelectorAll('#gallery .thumb').length > 0")
        gone = await self.p.js(
            "[...document.querySelectorAll('#gallery .thumb')].filter(t => t.textContent.includes('The file is gone')).length"
        )
        check(f"{tag}: a library entry whose file is gone says so", gone == 1, gone)
        vids = await self.p.js("document.querySelectorAll('#gallery video').length")
        check(
            f"{tag}: library tiles use small thumbnails, not whole videos",
            vids == 0,
            vids,
        )
        await self.audit(f"{tag} library")
        await self.shot(f"{w}-library")

        await self.open("worlds")
        line = await self.p.js(
            "document.querySelector('#sec-worlds .model-line').textContent"
        )
        check(
            f"{tag}: worlds section picks the downloaded world model",
            "Walk-Through Worlds" in line,
            line,
        )
        await self.p.js(
            "document.getElementById('worldPrompt').value = 'a misty forest path'"
        )
        await self.click("#worldStart")
        ok = await self.wait(
            "!document.getElementById('worldFrame').hidden && AS.worlds.session && AS.worlds.session.shown > 0",
            8,
        )
        check(f"{tag}: world starts and shows pictures", ok)
        labels = await self.p.js(
            "[...document.querySelectorAll('#worldPad button')].map(b => b.textContent).join(',')"
        )
        check(
            f"{tag}: move buttons use the server's words",
            "Walk forward" in labels and "Turn left" in labels,
            labels,
        )
        await self.p.js("document.getElementById('worldView').focus()")
        before = self.counts()
        shown0 = await self.p.js("AS.worlds.session.shown")
        await self.p.call(
            "Input.dispatchKeyEvent",
            type="keyDown",
            key="w",
            code="KeyW",
            windowsVirtualKeyCode=87,
        )
        await self.p.call(
            "Input.dispatchKeyEvent",
            type="keyDown",
            key="ArrowRight",
            code="ArrowRight",
            windowsVirtualKeyCode=39,
        )
        await asyncio.sleep(2.0)
        await self.audit(f"{tag} worlds")
        await self.shot(f"{w}-worlds")
        for key, code, vk in (("w", "KeyW", 87), ("ArrowRight", "ArrowRight", 39)):
            await self.p.call(
                "Input.dispatchKeyEvent",
                type="keyUp",
                key=key,
                code=code,
                windowsVirtualKeyCode=vk,
            )
        steps = sum(v for k, v in self.counts().items() if k.endswith("/step")) - sum(
            v for k, v in before.items() if k.endswith("/step")
        )
        check(f"{tag}: held keys send a few moves, not a flood", 1 <= steps <= 6, steps)
        await asyncio.sleep(1.5)
        shown1 = await self.p.js("AS.worlds.session.shown")
        check(f"{tag}: new pictures play", shown1 > shown0, f"{shown0} -> {shown1}")
        quiet = self.counts()
        await asyncio.sleep(1.5)
        idle = sum(v for k, v in self.counts().items() if k.endswith("/step")) - sum(
            v for k, v in quiet.items() if k.endswith("/step")
        )
        check(f"{tag}: no keys held, no moves sent", idle == 0, idle)
        await self.click("#worldStop")
        ok = await self.wait("!document.getElementById('worldStart').hidden", 5)
        check(f"{tag}: Stop ends the world", ok)

    # ---------------- once ----------------
    async def behaviour(self) -> None:
        self.stub("/__reset")
        self.stub("/__delay?s=1.0")
        await self.size(1100)
        await self.open("image")
        await self.p.js(
            "document.getElementById('imgPrompt').value = 'a fox under a lantern'"
        )
        await self.p.js(
            "(() => { const b = document.getElementById('imgGo'); b.click(); b.click(); })()"
        )
        await asyncio.sleep(0.4)
        await self.shot("1100-image-working")
        ok = await self.wait("document.querySelector('#imgResult .stage img')", 6)
        check("image appears in the result area", ok)
        check(
            "double press sends one request",
            self.counts().get("POST /api/generate/image") == 1,
            self.counts(),
        )
        await self.shot("1100-image-result")
        self.stub("/__delay?s=0.2")

        # edit: picks a picture from the library through "Edit this picture"
        await self.p.js(
            "[...document.querySelectorAll('#imgResult .result-actions button')].find(b => b.textContent === 'Edit this picture').click()"
        )
        ok = await self.wait(
            "!document.getElementById('sec-edit').hidden && document.querySelector('#editPicker .pick-thumb')"
        )
        check("Edit this picture opens Edit with it chosen", ok)
        await self.p.js("document.getElementById('editPrompt').value = 'at night'")
        await self.click("#editGo")
        ok = await self.wait("document.querySelector('#editResult .stage img')", 6)
        check("edit result appears", ok)
        await self.shot("1100-edit-result")

        # video from a model with no video model in use: says so, sends nothing
        await self.open("video")
        await self.p.js(
            "document.getElementById('mvPrompt').value = 'a paper boat in the rain'"
        )
        await self.click("#videoGo")
        err = await self.p.js("document.querySelector('#videoForm .error').textContent")
        check("no video model: says so in words", "no video model" in err, err)
        check(
            "no video model: nothing sent",
            "POST /api/generate/model-video" not in self.counts(),
        )
        await self.click("#sec-video .model-line[data-kind=video] button")
        await self.wait(
            "document.querySelector('#modelTabs').dataset.value === 'video' && document.querySelector('.model-card[data-id=\"wan-small\"]')"
        )
        await self.p.js(
            "document.querySelector('.model-card[data-id=\"wan-small\"] button[data-act=activate]').click()"
        )
        await self.wait("AS.models.active('video')")
        await self.click("#closeModelsBtn")
        await self.click("#videoGo")
        ok = await self.wait(
            "/Step \\d+ of 8/.test(document.querySelector('#videoResult .stage').textContent)",
            6,
        )
        check("video model: shows its progress", ok)
        await self.shot("1100-video-working")
        ok = await self.wait("document.querySelector('#videoResult .stage video')", 15)
        check("video model: the video appears", ok)
        await self.shot("1100-video-result")

        # camera moves over pictures: a job with phases, then the video
        await self.click('#videoWay button[data-value="warp"]')
        await self.p.js(
            "document.getElementById('wpPrompt').value = 'a harbour at sunset'"
        )
        await self.click("#videoGo")
        ok = await self.wait(
            "/Making the pictures: \\d of 6 done/.test(document.querySelector('#videoResult .stage').textContent)",
            6,
        )
        check("camera-move video: shows its progress in words", ok)
        await self.shot("1100-video-warp-working")
        ok = await self.wait("document.querySelector('#videoResult .stage video')", 15)
        check("camera-move video: the video appears", ok)
        stats = await self.p.js(
            "document.querySelector('#videoResult .stats').textContent"
        )
        check(
            "camera-move video: says how long it took",
            stats.startswith("Done in 6 seconds"),
            stats,
        )

        # one heavy job at a time: while a model video runs, the other
        # sections and Use this wait, with a line saying why
        await self.click('#videoWay button[data-value="model"]')
        self.stub("/__delay?s=0.2")
        await self.click("#videoGo")
        await self.wait(
            "/Step \\d+ of 8/.test(document.querySelector('#videoResult .stage').textContent)",
            6,
        )
        why = await self.p.js(
            "document.querySelector('#imageForm .busy-line').textContent"
        )
        check(
            "video running: image section says why it waits",
            why == "A video is being made. Wait for it or cancel it first.",
            why,
        )
        dis = await self.p.js(
            "[...document.querySelectorAll('#imageForm .go, #editForm .go, #worldForm .go')].map(b => b.disabled).join(',')"
        )
        check("video running: other Go buttons wait", dis == "true,true,true", dis)
        own = await self.p.js(
            "document.querySelector('#videoForm .busy-line').textContent"
        )
        check("video running: its own section has no wait line", own == "", own)
        await self.click("#modelsBtn")
        await self.wait(
            "document.querySelector('.model-card button[data-act=activate]')"
        )
        dis = await self.p.js(
            "[...document.querySelectorAll('#modelsList button[data-act=activate]')].every(b => b.disabled)"
        )
        line = await self.p.js("document.getElementById('modelsBusyLine').textContent")
        check(
            "video running: Use this waits, and the panel says why",
            dis and "A video is being made" in line,
            line,
        )
        await self.shot("1100-busy-models")
        await self.click("#closeModelsBtn")
        await self.p.js("AS.show('image')")
        await asyncio.sleep(0.3)
        await self.shot("1100-busy-image")
        await self.p.js("AS.show('video')")
        await self.p.js(
            "[...document.querySelectorAll('#videoResult .stage button')].find(b => b.textContent === 'Cancel').click()"
        )
        ok = await self.wait(
            "!document.querySelector('#imageForm .go').disabled && document.querySelector('#imageForm .busy-line').textContent === ''",
            8,
        )
        check("video cancelled: the other sections are free again", ok)

        # the server's 409 words reach the person (another window is busy)
        text = (
            "A video is being made in another window. Wait for it or cancel it first."
        )
        self.stub("/__busy?text=" + urllib.parse.quote(text))
        await self.open("image")
        ok = await self.wait(
            f"document.querySelector('#imageForm .busy-line').textContent === {json.dumps(text)}",
            8,
        )
        check("a heavy job in another window: the page says so and waits", ok)
        check(
            "a heavy job in another window: Go waits",
            await self.p.js("document.getElementById('imgGo').disabled"),
        )
        await self.shot("1100-busy-elsewhere")
        # the server's guard still answers if a press gets through (a job
        # another window began a moment ago, not yet in /api/busy)
        self.stub("/__busy?report=0&text=" + urllib.parse.quote(text))
        await self.wait(
            "document.querySelector('#imageForm .busy-line').textContent === ''", 12
        )
        await self.p.js("document.getElementById('imgPrompt').value = 'a fox'")
        await self.click("#imgGo")
        ok = await self.wait(
            "document.querySelector('#imageForm .error').textContent.length > 0", 6
        )
        err = await self.p.js("document.querySelector('#imageForm .error').textContent")
        check("a 409 from Go shows the server's words", err == text, err)
        stage = await self.p.js(
            "document.querySelector('#imgResult .stage').textContent"
        )
        check(
            "a 409 from Go says calmly that nothing started",
            "Nothing was started" in stage,
            stage,
        )
        await self.click("#modelsBtn")
        await self.wait(
            "document.querySelector('.model-card button[data-act=activate]:not(:disabled)')"
        )
        await self.p.js(
            "document.querySelector('.model-card button[data-act=activate]').click()"
        )
        dtext = await self.dialog_text()
        check("a 409 from Use this shows the server's words", dtext == text, dtext)
        await self.click(".forge-dialog .ok")
        await self.click("#closeModelsBtn")
        self.stub("/__busy?text=")

        # hidden: the open Models panel and the world rest completely
        await self.click("#modelsBtn")
        await asyncio.sleep(1.5)
        await self.p.js(
            "ForgeVisible.on = false; document.dispatchEvent(new CustomEvent('forge-visible', {detail: {visible: false}}))"
        )
        await asyncio.sleep(0.5)
        before = sum(self.counts().values())
        await asyncio.sleep(5)
        made = sum(self.counts().values()) - before
        check("hidden page makes no requests", made == 0, made)
        await self.p.js(
            "ForgeVisible.on = true; document.dispatchEvent(new CustomEvent('forge-visible', {detail: {visible: true}}))"
        )
        await self.click("#closeModelsBtn")

        # server down: calm words, few requests, recovers by itself
        self.stub("/__offline?on=1")
        await self.p.go(f"{self.base}/#library")
        ok = await self.wait(
            "/Can't reach the AI Studio server right now/.test(document.querySelector('#sec-library').textContent)",
            8,
        )
        check("offline: library says so calmly", ok)
        line = await self.p.js(
            "document.querySelector('#sec-image .model-line').textContent"
        )
        check("offline: model line says so calmly", "Can't reach" in line, line)
        await self.shot("1100-offline")
        c0 = sum(self.counts().values())
        await asyncio.sleep(10)
        n = sum(self.counts().values()) - c0
        check("offline: at most 8 requests in 10 s", n <= 8, n)
        self.stub("/__offline?on=0")
        ok = await self.wait(
            "document.querySelectorAll('#gallery .thumb').length > 0 && AS.models.loaded",
            40,
        )
        check("offline: recovers by itself", ok)


async def main() -> int:
    if BOX.exists():
        shutil.rmtree(BOX)  # scratch folder of this check only
    SHOTS.mkdir(parents=True, exist_ok=True)
    port = free_port()
    stub = subprocess.Popen(
        [sys.executable, str(APP / "tests/check_ui_stub.py"), str(port)]
    )
    try:
        wait_http(f"http://127.0.0.1:{port}/api/models")
        async with chrome_page(BOX, size="1100,900") as p:
            # uncaught errors and rejections are kept across page loads
            await p.call(
                "Page.addScriptToEvaluateOnNewDocument",
                source="const keep = (m) => { const a = JSON.parse(sessionStorage.__errors || '[]'); a.push(String(m)); sessionStorage.__errors = JSON.stringify(a); };"
                "addEventListener('error', (e) => keep(e.message));"
                "addEventListener('unhandledrejection', (e) => keep(e.reason && e.reason.message || e.reason));",
            )
            errors: list[str] = []
            run = Run(p, port)
            for w in (1100, 760, 1920):
                await run.width_pass(w)
            await run.behaviour()
            logs = await p.js("sessionStorage.__errors || ''")
            if logs and logs != "[]":
                errors.append(logs)
            check("no script errors", not errors, errors)
    finally:
        stub.terminate()
        stub.wait(5)
    for line in results:
        print(line)
    fails = sum(r.startswith("FAIL") for r in results)
    print(f"\n{len(results) - fails} passed, {fails} failed; screenshots in {SHOTS}")
    return 1 if fails else 0


if __name__ == "__main__":
    t0 = time.monotonic()
    code = asyncio.run(main())
    print(f"took {time.monotonic() - t0:.0f} s")
    sys.exit(code)
