"""The WhatsApp chat with Relay inside the Conversations view (Emerson's
note 1295, task 109) in a real browser: the header button and the pinned
Chats row open it, Relay's lines sit left under portraits (one per run of a
speaker) and his on the right with a read mark, WhatsApp's marks render and
nothing in a line can add markup, a day chip starts each day, a line he
sends goes to /api/relay-chat/say (to Relay or to the boss) and its ghost
gives way to the real line, the typing dots follow `answering`, new lines
are added without redrawing the old ones, Alt+Up and the header button move
between it and the sessions, and Mission's nav entry opens it.

Headless Chrome (Flatpak) through ~/Forge/tests/cdp_driver.py. Every answer
the page gets about sessions and the chat is made up inside the page (the
shim from test_convos_browser.py plus one for /api/relay-chat), so nothing
reaches Relay, WhatsApp or the Claude app."""

from __future__ import annotations

import asyncio
import datetime
import json
import random
import sys
import urllib.request
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_convos_browser import SHIM, _key, _sessions, cdp  # noqa: E402

DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

# /api/relay-chat answered from window.__wa; a line said there is added to it
# as Emerson's, marked new, as Relay's own log would show it.
WA_SHIM = """
window.__waPosts=[];window.__waGets=0;
const f1=window.fetch;
window.fetch=(u,o)=>{
  u=String(u);
  const post=!!(o&&String(o.method||'').toUpperCase()==='POST');
  const w=window.__wa;
  if(post&&u.includes('/api/relay-chat/say')){
    const b=JSON.parse(o.body);__waPosts.push(b);
    w.messages=w.messages.concat([{key:'p'+__waPosts.length,at:w.today+' 10:1'+__waPosts.length,who:'Emerson',me:true,text:(b.boss?'boss: ':'')+b.text,new:true}]);
    w.version=(parseInt(w.version,16)+1).toString(16);
    return J({ok:true,reply:'Sent: the answer comes in the chat.'});
  }
  if(!post&&u.includes('/api/relay-chat')){
    __waGets++;
    const seen=new URL(u,location.href).searchParams.get('seen')||'';
    const head={task:w.task,status:w.status,answering:w.answering,version:w.version};
    return J(seen&&seen===w.version?Object.assign(head,{same:true}):Object.assign(head,{messages:w.messages}));
  }
  return f1(u,o);
};
"""

LOOK = """JSON.stringify({
  sel: window.MissionConvos.selected,
  focus: document.body.classList.contains('focus-chat'),
  name: (document.querySelector('.fx-who-name') || {}).textContent || '',
  pill: (document.querySelector('.fx-who .fx-pill') || {}).textContent || '',
  pressed: document.getElementById('fxWaBtn').getAttribute('aria-pressed'),
  chip: document.getElementById('fxChip').innerText.replace(/\\s+/g, ' ').trim(),
  ph: document.getElementById('fxInput').placeholder,
  input: document.getElementById('fxInput').value,
  rows: [...document.querySelectorAll('#fxLog .fx-wa:not(.fx-typing)')].map((n) => [n.dataset.who, n.classList.contains('user') ? 'R' : 'L', !!n.querySelector(':scope > .fx-face'), (n.querySelector('.bubble') || {}).innerText || '', (n.querySelector('.joined') || {}).textContent || '']),
  days: [...document.querySelectorAll('#fxLog .fx-wa-day')].map((d) => d.textContent),
  ghosts: document.querySelectorAll('#fxLog .ghost').length,
  typing: !!document.querySelector('#fxLog .fx-typing'),
  bold: [...document.querySelectorAll('#fxLog .fx-wa .bubble b, #fxLog .fx-wa .bubble i')].map((b) => b.tagName + ':' + b.textContent),
  links: [...document.querySelectorAll('#fxLog .fx-wa .bubble a')].map((a) => a.getAttribute('href')),
  imgs: document.querySelectorAll('#fxLog img').length,
  probe: !!(document.querySelector('#fxLog .fx-wa[data-key="m2"]') || {})._probe,
  list: [...document.querySelectorAll('#fxList [data-fx-sel]')].map((x) => x.dataset.fxSel + (x.classList.contains('on') ? '*' : '')),
  chats: !document.getElementById('fxChats').hidden,
  facts: (document.getElementById('fxFacts') || {}).innerText || '',
  font: parseFloat(getComputedStyle(document.querySelector('#fxLog .fx-wa .bubble') || document.body).fontSize),
  errs: window.__errs,
})"""


def _thread(today: str, yesterday: str) -> dict:
    def line(i, at, who, text):
        me = who == "Emerson"
        return {
            "key": f"m{i}",
            "at": at,
            "who": who,
            "me": me,
            "text": text,
            "new": False,
        }

    return {
        "task": "47",
        "status": "idle",
        "answering": False,
        "version": "a1",
        "today": today,
        "messages": [
            line(
                1,
                f"{yesterday} 23:50",
                "Relay",
                "*Big* news and _soft_ https://example.com/a?b=1&c=2",
            ),
            line(2, f"{yesterday} 23:51", "Relay", "second in the run"),
            line(
                3, f"{today} 09:00", "Emerson", "<img src=x onerror=__errs.push('xss')>"
            ),
            line(4, f"{today} 09:01", "Relay", "line one\nline two"),
            line(5, f"{today} 09:02", "Boss", "the boss says hi"),
            line(6, f"{today} 09:03", "Jan", "and Jan"),
        ],
    }


async def _do(p, code: str) -> None:
    """Run statements in their own scope (a top-level const would stay)."""
    await p.js("(() => {" + code + "})()")


async def _look(p) -> dict:
    return json.loads(await p.js(LOOK))


async def _until(p, check, what: str, fails: list[str], secs: float = 6.0) -> dict:
    got = await _look(p)
    end = asyncio.get_event_loop().time() + secs
    while not check(got) and asyncio.get_event_loop().time() < end:
        await asyncio.sleep(0.25)
        got = await _look(p)
    if not check(got):
        fails.append(
            f"{what}: {json.dumps({k: got[k] for k in ('sel', 'rows', 'ghosts', 'typing', 'chip', 'pill')})[:600]}"
        )
    return got


async def _run(tmp: Path, port: int, rows: list[dict]) -> list[str]:
    fails: list[str] = []
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/overview") as r:
        fake = json.load(r)
    fake.update(sessions=rows, sig="fake")
    want = [
        r["id"]
        for r in sorted(
            rows, key=lambda r: (r["group"] != "needs_you", -r["last_active"])
        )
    ]
    i = datetime.date.today().weekday()
    today, yesterday = DAYS[i], DAYS[(i - 1) % 7]
    seed = f"window.__fake={json.dumps(fake)};window.__wa={json.dumps(_thread(today, yesterday))};"
    async with cdp.chrome_page(tmp, "1600,1000") as p:
        await p.call(
            "Page.addScriptToEvaluateOnNewDocument", source=seed + SHIM + WA_SHIM
        )
        await p.go(f"http://127.0.0.1:{port}/#convos")
        await p.wait("!!(window.MissionConvos && MissionConvos.selected)", 15)
        await asyncio.sleep(0.4)
        # the header button opens the WhatsApp chat
        await p.js("document.querySelector('[data-fx=wa]').click()")
        got = await _until(
            p, lambda g: len(g["rows"]) == 6, "the six lines did not show", fails
        )
        if (
            got["sel"] != "whatsapp"
            or "WhatsApp" not in got["name"]
            or got["pressed"] != "true"
        ):
            fails.append(
                f"header: {got['sel']} {got['name']!r} pressed={got['pressed']}"
            )
        if got["chip"] != "To Relay ▾" or got["ph"] != "Message Relay…":
            fails.append(f"composer: {got['chip']!r} {got['ph']!r}")
        # left / right, one face per run, the read mark on his last line
        shape = [(r[0], r[1], r[2], r[4]) for r in got["rows"]]
        if shape != [
            ("relay", "L", True, ""),
            ("relay", "L", False, ""),
            ("me", "R", False, "✓✓ read"),
            ("relay", "L", True, ""),
            ("boss", "L", True, ""),
            ("jan", "L", True, ""),
        ]:
            fails.append(f"layout: {shape}")
        if got["days"] != ["Yesterday", "Today"]:
            fails.append(f"day chips: {got['days']}")
        if got["bold"] != ["B:Big", "I:soft"] or got["links"] != [
            "https://example.com/a?b=1&c=2"
        ]:
            fails.append(f"marks: {got['bold']} {got['links']}")
        if (
            got["imgs"]
            or "<img src=x" not in got["rows"][2][3]
            or "line one\nline two" not in got["rows"][3][3]
        ):
            fails.append(
                f"escaping or line breaks: imgs={got['imgs']} {got['rows'][2][3]!r} {got['rows'][3][3]!r}"
            )
        if abs(got["font"] - 19) > 0.6:
            fails.append(f"text is {got['font']} px, not 19")
        # pinned on top of the Chats, found by "relay", not by nonsense
        await p.js(_key("k", ctrlKey=1))
        await asyncio.sleep(0.3)
        # Archived folds: open it to count every chat
        await p.js(
            "(document.querySelector('#fxList [data-fx=archived][aria-expanded=false]')"
            " || {click() {}}).click()"
        )
        await asyncio.sleep(0.2)
        got = await _look(p)
        if (
            not got["chats"]
            or got["list"][:1] != ["whatsapp*"]
            or len(got["list"]) != len(want) + 1
        ):
            fails.append(f"Chats panel: {got['list']}")
        for q, shown in (("zzqx", False), ("relay", True), ("whats", True)):
            await _do(
                p,
                f"const f=document.getElementById('fxFind');f.value='{q}';f.dispatchEvent(new Event('input',{{bubbles:true}}))",
            )
            await asyncio.sleep(0.1)
            if ("whatsapp*" in (await _look(p))["list"]) != shown:
                fails.append(f"find {q!r}: WhatsApp row shown should be {shown}")
        await _do(
            p,
            "const f=document.getElementById('fxFind');f.value='';f.dispatchEvent(new Event('input',{bubbles:true}))",
        )
        await p.js(_key("Escape"))
        # a line to Relay: the say call, a ghost, then the real line
        await _do(
            p,
            "const t=document.getElementById('fxInput');t.value='status';document.getElementById('fxSend').click()",
        )
        got = await _until(
            p,
            lambda g: len(g["rows"]) == 7 and not g["ghosts"],
            "the sent line did not replace its ghost",
            fails,
        )
        posts = json.loads(await p.js("JSON.stringify(window.__waPosts)"))
        if posts[:1] != [{"text": "status", "boss": False}]:
            fails.append(f"say: {posts}")
        last = got["rows"][-1]
        if (
            last[1] != "R"
            or not last[3].startswith("status")
            or "10:11" not in last[3]
            or last[4] != "✓ sent"
            or got["input"]
        ):
            fails.append(f"after sending: {got['rows'][-1]} input={got['input']!r}")
        # to the boss, through the chip's popover
        await p.js("document.getElementById('fxChip').click()")
        await asyncio.sleep(0.2)
        await p.js("document.querySelector('#fxPop [data-fx-wa=boss]').click()")
        await asyncio.sleep(0.2)
        got = await _look(p)
        if got["chip"] != "To the boss ▾" or got["ph"] != "Ask Relay's boss…":
            fails.append(f"boss pick: {got['chip']!r} {got['ph']!r}")
        await p.js(_key("Escape"))
        await _do(
            p,
            "const t=document.getElementById('fxInput');t.value='how full are we';document.getElementById('fxSend').click()",
        )
        got = await _until(
            p,
            lambda g: len(g["rows"]) == 8 and not g["ghosts"],
            "the boss line did not show",
            fails,
        )
        posts = json.loads(await p.js("JSON.stringify(window.__waPosts)"))
        if posts[1:2] != [{"text": "how full are we", "boss": True}]:
            fails.append(f"boss say: {posts}")
        if (
            json.loads(await p.js("localStorage.getItem('mission.convos.waBoss')"))
            is not True
        ):
            fails.append("the boss pick is not kept")
        await p.js("document.getElementById('fxChip').click()")
        await asyncio.sleep(0.2)
        await p.js("document.querySelector('#fxPop [data-fx-wa=relay]').click()")
        await p.js(_key("Escape"))
        # typing dots while Relay's chat answers
        await p.js("window.__wa.answering=true")
        got = await _until(
            p,
            lambda g: g["typing"] and g["pill"] == "answering",
            "no typing dots",
            fails,
        )
        await p.js("window.__wa.answering=false")
        await _until(
            p,
            lambda g: not g["typing"] and g["pill"] == "live",
            "the typing dots stayed",
            fails,
        )
        # a new line is added and the old ones stay as they are; the oldest
        # one leaving (Relay keeps 40) takes only itself away
        await _do(
            p,
            "document.querySelector('#fxLog .fx-wa[data-key=\"m2\"]')._probe=1;"
            "const w=window.__wa;w.messages=w.messages.slice(1).concat([{key:'m9',at:w.today+' 11:00',who:'Relay',me:false,text:'fresh',new:false}]);"
            "w.version=(parseInt(w.version,16)+1).toString(16)",
        )
        got = await _until(
            p,
            lambda g: g["rows"] and g["rows"][-1][3].startswith("fresh"),
            "the new line did not show",
            fails,
        )
        if (
            not got["probe"]
            or len(got["rows"]) != 8
            or got["rows"][0][:3] != ["relay", "L", True]
        ):
            fails.append(
                f"incremental: probe={got['probe']} n={len(got['rows'])} first={got['rows'][:1]}"
            )
        if got["days"] != ["Yesterday", "Today"]:
            fails.append(f"day chips after the window moved: {got['days']}")
        # the sheet: text size and the facts, no session knobs
        await p.js("document.querySelector('[data-fx=sheet]').click()")
        await asyncio.sleep(0.3)
        got = await _look(p)
        if "#47" not in got["facts"] or await p.js(
            "!!document.querySelector('#fxSheet input[name=fxMode]')"
        ):
            fails.append(f"sheet: {got['facts']!r}")
        await p.js(_key("Escape"))
        # Alt+Up wraps to the last session; the header button goes there and back
        await p.js(_key("ArrowUp", altKey=1))
        await asyncio.sleep(0.4)
        got = await _look(p)
        if got["sel"] != want[-1] or got["pressed"] != "false":
            fails.append(f"Alt+Up from WhatsApp: {got['sel']} (want {want[-1]})")
        await p.js("document.querySelector('[data-fx=wa]').click()")
        await asyncio.sleep(0.4)
        await p.js("document.querySelector('[data-fx=wa]').click()")
        await asyncio.sleep(0.4)
        if (await _look(p))["sel"] != want[-1]:
            fails.append("the WhatsApp button did not go back to the chat before it")
        # Mission's nav entry opens it from another view
        await p.js("document.querySelector('[data-fx=back]').click()")
        await asyncio.sleep(0.3)
        if (await _look(p))["focus"]:
            fails.append("Mission button did not leave the chat")
        await p.js("document.querySelector('.views [data-chat=whatsapp]').click()")
        got = await _until(
            p,
            lambda g: g["focus"] and g["sel"] == "whatsapp" and len(g["rows"]) == 8,
            "the nav entry did not open WhatsApp",
            fails,
        )
        await p.screenshot(tmp / "wa.png")
        if got["errs"]:
            fails.append(f"page errors: {got['errs']}")
    return fails


@pytest.mark.parametrize("seed", [1, 2])
def test_whatsapp_chat(tmp_path, seed):
    rng = random.Random(seed)
    rows = _sessions(rng, rng.randint(3, 7))
    for r in rows:
        r["claude_tab"] = None  # transcripts only: the Claude app is never asked
    with cdp.serve(APP, {"MISSION_PORT_CLAUDE": "9"}) as port:
        fails = asyncio.run(_run(tmp_path, port, rows))
    assert not fails, "\n".join(fails)
