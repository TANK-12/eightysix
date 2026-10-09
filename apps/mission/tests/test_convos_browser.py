"""The Conversations view (task 109 rebuild) in a real browser: the chat
fills the window (Mission's bars step aside), the Chats panel lists
needs-you first then newest activity, a session the Claude app runs opens
its Claude app chat (a fake one here, through Mission's /api/claude door),
any other opens its transcript, tool calls fold into a steps bar, the model
and effort popover, Ultracode and ultrathink reach the Claude app, text size
and steps settings work, keys (Ctrl+K, Alt+Down, Esc) work, a reply to a
terminal session goes to /say, and leaving and coming back leaves one chat.

Headless Chrome (Flatpak) through ~/Forge/tests/cdp_driver.py; the page's
/api/overview answers are made up, and MISSION_PORT_CLAUDE points Mission at
the fake Claude app, so Emerson's real chats are never touched. Transcript
reads and every POST to /api/sessions are answered inside the page, so no
board note is posted."""

from __future__ import annotations

import asyncio
import json
import random
import shutil
import sys
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP.parents[1] / "tests"))
cdp = pytest.importorskip("cdp_driver")
if not shutil.which("flatpak"):
    pytest.skip("no flatpak Chrome here", allow_module_level=True)

OPTIONS = {
    "models": {"": "Claude Code's default", "opus": "Opus", "haiku": "Haiku"},
    "efforts": {"": "Default", "low": "Low", "high": "High", "max": "Max"},
    "modes": {"dontAsk": "Read files", "acceptEdits": "Also edit files"},
    "agent_limits": {
        "max_helpers": {
            "kind": "int",
            "min": 1,
            "max": 50,
            "default": "20",
            "label": "Helpers at once",
            "help": "h",
        }
    },
    "ultracode": {"unsupported_models": ["haiku"]},
}


class Fake(BaseHTTPRequestHandler):
    posts: list = []
    meta: dict = {}

    def log_message(self, format, *args):  # quiet
        pass

    def _send(self, out):
        raw = json.dumps(out).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        if self.path.startswith("/api/options"):
            return self._send(OPTIONS)
        conv = self.path.split("/")[3]
        if "after=-1" in self.path:
            events = [
                {"type": "forge_user", "text": f"hello {conv}", "seq": 0},
                {
                    "type": "assistant",
                    "seq": 1,
                    "message": {
                        "content": [
                            {"type": "text", "text": f"answer in {conv}"},
                            {
                                "type": "tool_use",
                                "id": "t1",
                                "name": "TodoWrite",
                                "input": {
                                    "todos": [
                                        {"content": "step one", "status": "completed"},
                                        {
                                            "content": "step two",
                                            "status": "in_progress",
                                        },
                                    ]
                                },
                            },
                        ]
                    },
                },
            ]
        else:
            time.sleep(0.5)  # a short long-poll
            events = []
        meta = {"title": f"task {conv}", "model": "opus", "effort": "high"}
        meta.update(Fake.meta.get(conv, {}))
        self._send(
            {
                "events": events,
                "busy": False,
                "meta": meta,
                "boot": "b1",
                "reset": False,
            }
        )

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(n) or b"{}")
        conv, action = self.path.split("/")[3], self.path.split("/")[4]
        Fake.posts.append((conv, action, body))
        if action == "settings":
            Fake.meta.setdefault(conv, {}).update(body)
            meta = {"title": f"task {conv}", "model": "opus", "effort": "high"}
            meta.update(Fake.meta[conv])
            return self._send(meta)
        self._send({"ok": True})


def _sessions(rng: random.Random, n: int) -> list[dict]:
    now = time.time()
    rows = []
    for i in range(n):
        group = rng.choice(["working", "idle", "needs_you", "ended"])
        tab = f"conv{i:02d}" if rng.random() < 0.5 else None
        rows.append(
            {
                "id": f"22222222-aaaa-bbbb-cccc-{i:012d}",
                "name": f"ejb-{i:02x}",
                "label": f"Persona{i}",
                "title": f"title {i}",
                "action": f"doing thing {i}",
                "group": group,
                "status": group,
                "cwd": "/home/ejb/Forge",
                "place": "Forge",
                "model": "claude-opus-5-5",
                "effort": "high",
                "last_active": now - rng.uniform(0, 3 * 86400),
                "helpers": [],
                "crews": [],
                "relay": None,
                "claude_tab": tab,
                "context": 1000,
                "window": 200000,
            }
        )
    return rows


# Answers made up inside the page: the overview, transcripts (a question, an
# answer and one Bash call) and every POST to /api/sessions (caught).
SHIM = """
window.__errs=[];addEventListener('error',e=>__errs.push(String(e.message)));
addEventListener('unhandledrejection',e=>__errs.push('rej '+String(e.reason)));
window.__posts=[];
const f0=window.fetch.bind(window);
const J=(x)=>Promise.resolve(new Response(JSON.stringify(x),{headers:{'content-type':'application/json'}}));
window.fetch=(u,o)=>{
  u=String(u);
  const post=!!(o&&String(o.method||'').toUpperCase()==='POST');
  if(u.includes('/api/overview'))return J(window.__fake);
  const m=/\\/api\\/sessions\\/([^/?]+)\\/events/.exec(u);
  if(m&&!post){
    if(/after=/.test(u))return J({events:[],after:2,size:2,reset:false,more:false});
    const k=m[1].slice(-4);
    return J({events:[{type:'forge_user',text:'hi '+k,seq:0},{type:'assistant',seq:1,message:{content:[
      {type:'text',text:'log answer '+k},{type:'tool_use',id:'b'+k,name:'Bash',input:{command:'ls'}}]}}],
      before:null,more:false,after:2,size:2});
  }
  if(post&&u.includes('/api/sessions/')){window.__posts.push([u,JSON.parse((o&&o.body)||'{}')]);return J({via:'board',id:7});}
  return f0(u,o);
};
localStorage.clear();
"""

LOOK = """JSON.stringify({
  focus: document.body.classList.contains('focus-chat'),
  chrome: ['.mc-top', '.mc-side', '#needs'].map((q) => { const e = document.querySelector(q); return !!(e && e.getClientRects().length); }),
  vh: innerHeight,
  plan: (() => { const b = document.getElementById('fxPlan'); return b.hidden ? '' : b.textContent + '|' + b.title; })(),
  scroll: (() => { const r = document.getElementById('fxScroll').getBoundingClientRect(); return [Math.round(r.width), Math.round(r.height)]; })(),
  sel: window.MissionConvos.selected,
  name: (document.querySelector('.fx-who-name') || {}).textContent || '',
  logs: document.getElementById('fxLog').children.length,
  text: document.getElementById('fxLog').innerText || '',
  steps: [...document.querySelectorAll('#fxLog .fx-steps')].map((g) => g.innerText.replace(/\\s+/g, ' ')),
  stepsShown: [...document.querySelectorAll('#fxLog .fx-steps')].filter((g) => g.getClientRects().length).length,
  chats: !document.getElementById('fxChats').hidden,
  order: [...document.querySelectorAll('#fxList [data-fx-sel]:not([data-fx-sel=whatsapp])')].map((x) => x.dataset.fxSel),
  todos: [...document.querySelectorAll('#fxTodos li')].map((l) => l.className + ':' + l.textContent),
  ultraTag: !!document.querySelector('#fxChip .fx-ultra-tag'),
  font: parseFloat(getComputedStyle(document.querySelector('#fxLog .bubble') || document.body).fontSize),
  errs: window.__errs,
})"""


# Mission's sections (static/logic.js section()): needs-you and working as
# they are, ended or quiet for 30 minutes archived
ARCHIVE_S = 1800
RANK = {"needs_you": 0, "working": 1, "idle": 2, "archived": 3}
OPEN_ARCHIVED = (
    "(document.querySelector('#fxList [data-fx=archived][aria-expanded=false]')"
    " || {click() {}}).click()"
)


def _section(row: dict, now: float) -> str:
    if row["group"] in ("needs_you", "working"):
        return row["group"]
    if row["group"] == "ended" or now - row["last_active"] >= ARCHIVE_S:
        return "archived"
    return row["group"]


def _key(key: str, **mods) -> str:
    flags = ",".join(f"{k}:true" for k in mods)
    return f"window.dispatchEvent(new KeyboardEvent('keydown',{{key:'{key}',bubbles:true,{flags}}}))"


async def _look(p) -> dict:
    return json.loads(await p.js(LOOK))


async def _run(tmp: Path, port: int, rows: list[dict]) -> list[str]:
    fails: list[str] = []
    # the real answer's shape, with made-up sessions in it
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/overview") as r:
        fake = json.load(r)
    fake.update(sessions=rows, sig="fake")
    now = time.time()
    want = [
        r["id"]
        for r in sorted(rows, key=lambda r: (RANK[_section(r, now)], -r["last_active"]))
    ]
    archived = {r["id"] for r in rows if _section(r, now) == "archived"}
    by_id = {r["id"]: r for r in rows}
    async with cdp.chrome_page(tmp, "1600,1000") as p:
        await p.call(
            "Page.addScriptToEvaluateOnNewDocument",
            source=f"window.__fake={json.dumps(fake)};" + SHIM,
        )
        await p.go(f"http://127.0.0.1:{port}/#convos")
        await p.wait("!!(window.MissionConvos && MissionConvos.selected)", 15)
        await asyncio.sleep(0.5)
        got = await _look(p)
        # the chat is the main thing on screen
        if not got["focus"] or any(got["chrome"]):
            fails.append(f"Mission's bars still show: {got['focus']} {got['chrome']}")
        if got["scroll"][0] < 1500 or got["scroll"][1] < 0.65 * got["vh"]:
            fails.append(f"chat area only {got['scroll']} of 1600x{got['vh']}")
        if got["sel"] != want[0]:
            fails.append("the first chat is not needs-you first, then newest")
        # Ctrl+K opens the Chats panel in Mission's sections, newest first in
        # each; Archived stays folded (unless it holds the open chat) until
        # its header is pressed
        await p.js(_key("k", ctrlKey=1))
        await asyncio.sleep(0.3)
        got = await _look(p)
        shown = [i for i in want if i not in archived or want[0] in archived]
        if not got["chats"] or got["order"] != shown:
            fails.append(
                f"Chats panel: open={got['chats']} order ok={got['order'] == shown}"
            )
        if archived and want[0] not in archived:
            await p.js(OPEN_ARCHIVED)
            await asyncio.sleep(0.2)
            if (await _look(p))["order"] != want:
                fails.append("Archived did not unfold in order under the others")
        await p.js(_key("Escape"))
        await asyncio.sleep(0.2)
        if (await _look(p))["chats"]:
            fails.append("Esc did not close the Chats panel")
        # every chat opens from the panel, once, with its own words
        for sid in want:
            row = by_id[sid]
            await p.js("document.querySelector('[data-fx=chats]').click()")
            await p.js(
                f"document.querySelector('#fxList [data-fx-sel=\"{sid}\"]') || ({OPEN_ARCHIVED})"
            )
            await p.js(
                f"document.querySelector('#fxList [data-fx-sel=\"{sid}\"]').click()"
            )
            words = (
                f"answer in {row['claude_tab']}"
                if row["claude_tab"]
                else f"log answer {sid[-4:]}"
            )
            ok = await p.wait(
                f"(document.getElementById('fxLog').innerText||'').includes('{words}')",
                8,
            )
            await asyncio.sleep(0.3)
            got = await _look(p)
            where = f"{row['label']} ({'claude' if row['claude_tab'] else 'log'}, {row['group']})"
            if not ok:
                fails.append(f"{where}: never drew")
            if got["chats"]:
                fails.append(f"{where}: picking did not close the panel")
            if got["logs"] != 1:
                fails.append(f"{where}: {got['logs']} chats drawn at once")
            if not got["name"].startswith(row["title"]):
                fails.append(f"{where}: header name {got['name']!r}")
            if not row["claude_tab"] and not any("1 step" in s for s in got["steps"]):
                fails.append(
                    f"{where}: the Bash call is not folded into a steps bar: {got['steps']}"
                )
            if row["claude_tab"] and got["plan"] != "1 of 2|Plan: now step two":
                fails.append(f"{where}: plan chip: {got['plan']!r}")
        # Alt+Down goes to the next chat in the list's order
        await p.js(f"MissionConvos.select('{want[0]}')")
        await asyncio.sleep(0.3)
        await p.js(_key("ArrowDown", altKey=1))
        await asyncio.sleep(0.3)
        if (await _look(p))["sel"] != want[1 % len(want)]:
            fails.append("Alt+Down did not open the next chat")
        # model, effort, ultrathink and Ultracode reach the Claude app; send
        first = next(r for r in rows if r["claude_tab"])
        conv = first["claude_tab"]
        await p.js(f"MissionConvos.select('{first['id']}')")
        await p.wait(
            f"(document.getElementById('fxLog').innerText||'').includes('answer in {conv}')",
            8,
        )
        await p.js("document.getElementById('fxChip').click()")
        await p.wait("!document.getElementById('fxPop').hidden", 3)
        for sel in (
            '[data-fx-model="haiku"]',
            '[data-fx-model="opus"]',
            '[data-fx-effort="max"]',
            '[data-fx-ultra="next"]',
        ):
            await p.js(f"document.querySelector('#fxPop {sel}').click()")
            await asyncio.sleep(0.4)
        await p.js(_key("Escape"))
        await p.js("document.querySelector('[data-fx=sheet]').click()")
        await p.wait(
            "!!document.querySelector('#fxSheet .run-seg button:nth-child(2)')", 5
        )
        todos = (await _look(p))["todos"]
        if todos != ["completed:step one", "in_progress:step two"]:
            fails.append(f"plan in the Session sheet: {todos}")
        await p.js(
            "document.querySelector('#fxSheet .run-seg button:nth-child(2)').click()"
        )
        await asyncio.sleep(0.4)
        if not (await _look(p))["ultraTag"]:
            fails.append("the chip does not show ultrathink is on")
        await p.js(
            "document.getElementById('fxInput').value='fix the thing'; document.getElementById('fxSend').click()"
        )
        await asyncio.sleep(1.0)
        mine = [x for x in Fake.posts if x[0] == conv]
        sent = [b for c, a, b in mine if a == "send"]
        sets = [b for c, a, b in mine if a == "settings"]
        if sent != [{"text": "ultrathink. fix the thing", "files": []}]:
            fails.append(f"send body: {sent}")
        for want_set in (
            {"model": "haiku"},
            {"model": "opus"},
            {"effort": "max"},
            {"ultracode": True},
        ):
            if want_set not in sets:
                fails.append(f"settings missing {want_set}: {sets}")
        if (await _look(p))["ultraTag"]:
            fails.append("ultrathink stayed on after sending")
        # text size and steps from the Session sheet
        before = (await _look(p))["font"]
        await p.js(
            "const n=document.getElementById('fxSizeN'); n.value='26'; n.dispatchEvent(new Event('change',{bubbles:true}))"
        )
        await asyncio.sleep(0.3)
        after = (await _look(p))["font"]
        if not after > before:
            fails.append(f"text size did not grow: {before} -> {after}")
        await p.js("document.querySelector('[data-fx-steps=\"hidden\"]').click()")
        await asyncio.sleep(0.2)
        log_row = next(r for r in rows if not r["claude_tab"])
        await p.js("document.querySelector('[data-fx=close]').click()")
        await p.js(f"MissionConvos.select('{log_row['id']}')")
        await p.wait(
            f"(document.getElementById('fxLog').innerText||'').includes('log answer {log_row['id'][-4:]}')",
            8,
        )
        await asyncio.sleep(0.3)
        if (await _look(p))["stepsShown"]:
            fails.append("steps still show with Steps: hidden")
        # a reply to a terminal or ended session goes to /say, caught here
        await p.js(
            "document.getElementById('fxInput').value='hello there'; document.getElementById('fxSend').click()"
        )
        await asyncio.sleep(0.8)
        posts = json.loads(await p.js("JSON.stringify(window.__posts)"))
        says = [b for u, b in posts if u.endswith(f"/api/sessions/{log_row['id']}/say")]
        if not says or says[-1].get("text") != "hello there":
            fails.append(f"reply to a terminal session: {posts}")
        # leaving the view and coming back leaves one chat, bars come back meanwhile
        await p.js("MissionApp.setView('sessions')")
        await asyncio.sleep(0.3)
        away = await _look(p)
        if away["focus"] or not any(away["chrome"]):
            fails.append("Mission's bars did not come back on Sessions")
        await p.js("MissionApp.setView('convos')")
        await asyncio.sleep(1.0)
        got = await _look(p)
        if got["logs"] != 1 or not got["focus"]:
            fails.append(
                f"after coming back: {got['logs']} chats, focus {got['focus']}"
            )
        if got["errs"]:
            fails.append(f"page errors: {got['errs']}")
    return fails


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_conversations_view(tmp_path, seed):
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Fake)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    Fake.posts, Fake.meta = [], {}
    rng = random.Random(seed)
    rows = _sessions(rng, rng.randint(4, 9))
    rows[0]["claude_tab"] = rows[0]["claude_tab"] or "conv00"  # at least one each
    rows[1]["claude_tab"] = None
    try:
        with cdp.serve(
            APP, {"MISSION_PORT_CLAUDE": str(srv.server_address[1])}
        ) as port:
            fails = asyncio.run(_run(tmp_path, port, rows))
    finally:
        srv.shutdown()
        srv.server_close()
    assert not fails, "\n".join(fails)


# Reading extras (critic and Emerson-lens fixes): words on the way fold into
# the steps bar, links open through Mission, drafts stay with their chat,
# A-/A+ in the header, Stop on a Relay run asks once, and a backend older
# than the page says so. Everything answered inside the page.
EXTRAS_SHIM = """
window.__errs=[];addEventListener('error',e=>__errs.push(String(e.message)));
addEventListener('unhandledrejection',e=>__errs.push('rej '+String(e.reason)));
window.__posts=[];
const f0=window.fetch.bind(window);
const J=(x,s)=>Promise.resolve(new Response(JSON.stringify(x),{status:s||200,headers:{'content-type':'application/json'}}));
window.fetch=(u,o)=>{
  u=String(u);
  const post=!!(o&&String(o.method||'').toUpperCase()==='POST');
  const body=()=>JSON.parse((o&&o.body)||'{}');
  if(u.includes('/api/overview'))return J(window.__fake);
  if(post&&(u.includes('/api/claude/open-link')||u.includes('/api/relay/tasks/'))){window.__posts.push([u,body()]);return J({ok:true,message:'Stopping it'});}
  if(u.includes('/api/claude/'))return J({detail:'Not Found'},404);
  const m=/\\/api\\/sessions\\/([^/?]+)\\/events/.exec(u);
  if(m&&!post){
    if(/after=/.test(u))return J({events:[],after:4,size:4,reset:false,more:false});
    const k=m[1].slice(-4);
    const said=(seq,text,tool)=>({type:'assistant',seq,message:{content:[{type:'text',text},tool]}});
    return J({events:[{type:'forge_user',text:'please check '+k,seq:0},
      said(1,'Let me look first.',{type:'tool_use',id:'a'+k,name:'Bash',input:{command:'ls'}}),
      said(2,'Found it, reading now.',{type:'tool_use',id:'b'+k,name:'Read',input:{file_path:'/tmp/x'}}),
      {type:'assistant',seq:3,message:{content:[{type:'text',text:'All done '+k+': see [the page](https://example.com/x) for more.'}]}}],
      before:null,more:false,after:4,size:4});
  }
  if(post&&u.includes('/api/sessions/')){window.__posts.push([u,body()]);return J({via:'board',id:7});}
  return f0(u,o);
};
localStorage.clear();
"""

EXTRAS_LOOK = """JSON.stringify({
  sel: window.MissionConvos.selected,
  input: document.getElementById('fxInput').value,
  groups: document.querySelectorAll('#fxLog .fx-steps').length,
  label: (document.querySelector('#fxLog .fx-st-label') || {}).textContent || '',
  said: (document.querySelector('#fxLog .fx-st-names.said') || {}).textContent || '',
  open: [...document.querySelectorAll('#fxLog .msg.claude:not(.fx-aside) > .bubble')].filter((b) => b.getClientRects().length).map((b) => b.textContent.trim()),
  font: parseFloat(getComputedStyle(document.querySelector('#fxLog .bubble') || document.body).fontSize),
  stop: (() => { const b = document.getElementById('fxStop'); return [b.hidden, b.classList.contains('armed'), b.textContent.trim()]; })(),
  empty: document.getElementById('fxEmpty').textContent,
  posts: window.__posts,
  errs: window.__errs,
})"""


async def _extras(port: int, rows: list[dict]) -> list[str]:
    fails: list[str] = []
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/overview") as r:
        fake = json.load(r)
    fake.update(sessions=rows, sig="fake")
    a, b, run, old = (r["id"] for r in rows)

    async def look() -> dict:
        return json.loads(await p.js(EXTRAS_LOOK))

    async def pick(sid: str, words: str = "") -> None:
        await p.js(f"MissionConvos.select('{sid}')")
        if words:
            await p.wait(
                f"(document.getElementById('fxLog').innerText||'').includes('{words}')",
                8,
            )
        await asyncio.sleep(0.4)

    async with cdp.chrome_page(Path("/tmp"), "1600,1000") as p:
        await p.call(
            "Page.addScriptToEvaluateOnNewDocument",
            source=f"window.__fake={json.dumps(fake)};" + EXTRAS_SHIM,
        )
        await p.go(f"http://127.0.0.1:{port}/#convos")
        await p.wait("!!(window.MissionConvos && MissionConvos.selected)", 15)
        await pick(a, f"All done {a[-4:]}")
        got = await look()
        # the two short lines on the way sit in one steps bar with both tools
        if got["groups"] != 1 or not got["label"].startswith("2 steps"):
            fails.append(f"steps bar: {got['groups']} bars, label {got['label']!r}")
        if got["said"] != "Found it, reading now.":
            fails.append(f"the bar does not say the last words: {got['said']!r}")
        if got["open"] != [f"All done {a[-4:]}: see the page for more."]:
            fails.append(f"words left in the open chat: {got['open']}")
        # a link in a reply opens through Mission (Forge's Browser)
        await p.js("document.querySelector('#fxLog .bubble a').click()")
        await asyncio.sleep(0.4)
        if ["/api/claude/open-link", {"url": "https://example.com/x"}] not in (
            await look()
        )["posts"]:
            fails.append(f"the link did not go to open-link: {(await look())['posts']}")
        # A+ / A- in the header
        before = got["font"]
        await p.js("document.querySelector('[data-fx-size=\"2\"]').click()")
        await asyncio.sleep(0.3)
        bigger = (await look())["font"]
        await p.js("document.querySelector('[data-fx-size=\"-2\"]').click()")
        await asyncio.sleep(0.3)
        if not bigger > before or (await look())["font"] != before:
            fails.append(f"A+/A-: {before} -> {bigger} -> {(await look())['font']}")
        # a draft stays with its chat
        await p.js("document.getElementById('fxInput').value='half a thought'")
        await pick(b, f"All done {b[-4:]}")
        if (await look())["input"] != "":
            fails.append("the other chat shows this chat's draft")
        await pick(a, f"All done {a[-4:]}")
        if (await look())["input"] != "half a thought":
            fails.append(f"the draft did not come back: {(await look())['input']!r}")
        # Stop on a Relay run: the first press asks, the second stops it
        await pick(run, f"All done {run[-4:]}")
        await p.js("document.getElementById('fxStop').click()")
        await asyncio.sleep(0.3)
        got = await look()
        if got["stop"] != [False, True, "Stop #77?"] or any(
            "/relay/tasks/" in u for u, _ in got["posts"]
        ):
            fails.append(f"first Stop press: {got['stop']} {got['posts']}")
        await p.js("document.getElementById('fxStop').click()")
        await asyncio.sleep(0.4)
        if not any(u == "/api/relay/tasks/77/stop" for u, _ in (await look())["posts"]):
            fails.append("the second Stop press did not stop task 77")
        # a Claude app chat behind a Mission backend without the routes
        await pick(old)
        await p.wait("document.getElementById('fxEmpty').textContent.length > 0", 8)
        got = await look()
        if "older than this page" not in got["empty"]:
            fails.append(f"old backend message: {got['empty']!r}")
        if got["errs"]:
            fails.append(f"page errors: {got['errs']}")
    return fails


def test_reading_extras():
    now = time.time()
    rows = _sessions(random.Random(7), 4)
    for i, row in enumerate(rows):
        row.update(group="working", status="working", claude_tab=None, relay=None)
        row["last_active"] = now - 10 * (i + 1)
    rows[2]["relay"] = {"task": 77, "title": "Fix the thing"}
    rows[3]["claude_tab"] = "convOLD"
    env = {"MISSION_PORT_CLAUDE": "9", "MISSION_PORT_RELAY": "9"}
    with cdp.serve(APP, env) as port:
        fails = asyncio.run(_extras(port, rows))
    assert not fails, "\n".join(fails)
