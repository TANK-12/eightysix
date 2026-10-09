"""Screenshots of the Conversations view on real data, for before and after
pictures. Not a test (pytest does not collect it).

Runs this app on a free port, opens it in headless Chrome with every POST
blocked inside the page, so nothing is sent, stopped, renamed or marked seen
in Emerson's real chats (reads still go to the real Claude app through
Mission's /api/claude door), picks a session and saves PNGs.

    .venv/bin/python tests/shoot_convos.py OUT_DIR [--kind claude|log|any]
        [--session ID] [--size 1600,1000] [--name shot] [--wait 7]
        [--js "extra page script run before the picture"]

--session whatsapp shows the WhatsApp chat with Relay. --kind claude picks the newest session that runs in a Claude app tab, log the
newest that does not, any the newest of all. Prints the session it used.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import urllib.request
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP.parents[1] / "tests"))
import cdp_driver as cdp  # noqa: E402  # pyright: ignore[reportMissingImports]

BLOCK_POSTS = (
    "window.__errs=[];addEventListener('error',e=>__errs.push(String(e.message)));"
    "const f0=window.fetch.bind(window);"
    "window.fetch=(u,o)=>(o&&String(o.method||'').toUpperCase()==='POST')"
    "?Promise.reject(new Error('blocked in the screenshot run')):f0(u,o);"
)


def pick(sessions: list[dict], kind: str) -> dict | None:
    rows = sorted(sessions, key=lambda s: -(s.get("last_active") or 0))
    if kind == "claude":
        rows = [s for s in rows if s.get("claude_tab")]
    elif kind == "log":
        rows = [s for s in rows if not s.get("claude_tab")]
    return rows[0] if rows else None


async def shoot(port: int, args: argparse.Namespace, out: Path) -> None:
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/overview") as r:
        data = json.load(r)
    s = (
        {"id": "whatsapp", "label": "the WhatsApp chat"}
        if args.session == "whatsapp"
        else (
            next((x for x in data["sessions"] if x["id"] == args.session), None)
            if args.session
            else pick(data["sessions"], args.kind)
        )
    )
    if not s:
        raise SystemExit(f"no {args.kind} session to show")
    print(
        f"session {s['id']} {s.get('label') or s.get('name')} tab={s.get('claude_tab')}"
    )
    seed = (
        BLOCK_POSTS
        + f"localStorage.setItem('mission.convos.sel',{json.dumps(json.dumps(s['id']))});"
        + "localStorage.setItem('mission.view',JSON.stringify('convos'));"
    )
    async with cdp.chrome_page(out, args.size) as p:
        await p.call("Page.addScriptToEvaluateOnNewDocument", source=seed)
        await p.go(f"http://127.0.0.1:{port}/#convos")
        await asyncio.sleep(args.wait)
        if args.js:
            await p.js(args.js)
            await asyncio.sleep(1.2)
        await p.screenshot(out / f"{args.name}.png")
        errs = await p.js("JSON.stringify(window.__errs||[])")
        print("page errors:", errs)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--kind", default="claude", choices=("claude", "log", "any"))
    ap.add_argument("--session", default="")
    ap.add_argument("--size", default="1600,1000")
    ap.add_argument("--name", default="shot")
    ap.add_argument("--wait", type=float, default=7.0)
    ap.add_argument("--js", default="")
    args = ap.parse_args()
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    with cdp.serve(APP, {"FORGE_SHARED_DIR": str(APP.parents[1] / "shared")}) as port:
        asyncio.run(shoot(port, args, out))


if __name__ == "__main__":
    main()
