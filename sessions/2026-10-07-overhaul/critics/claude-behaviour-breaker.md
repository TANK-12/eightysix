# Claude app: behaviour breaker critic report
date: 2026-10-07 · for: both · reviewer: critic subagent of helper-2 (overhaul wave); scripts in /tmp/critic-act/

Ranked; "reproduced" = seen on a scratch server, "suspected" = read only.

1. Reproduced: a message sent right after a turn ends is silently lost if settings changed or the tab closed mid-turn. Close thread from _read (runner.py:1037) calls stop(quiet); send (runner.py:1085) still sees running() true and writes into the dying process; forge_stopped suppresses forge_exit (1040-1054). Fix: hold self._write inside stop()/close(); in send treat a forge_stopped process as not running and start fresh.
2. Reproduced (classic and Enjoy): after a server restart the page stops showing new events. seq = len(self.events) includes transient stream_events; _load_history (866) renumbers from the jsonl only (109 before restart, 5 after); page keeps polling after=109, reply never drawn, status stuck "working". Fix: boot id or event count in /events, refetch from -1 when the client is past it or boot id changed; better, transient events get no seq.
3. Reproduced: send racing a settings change: BrokenPipeError at runner.py:1126 (and _start ~948) -> 500, but forge_user already recorded and working saved; UI says "Not sent" yet the bubble stays, retry duplicates. Fix: record only after a good write; catch OSError, restart once, retry.
4. Reproduced: streaming = one HTTP round trip per word (120 words -> 241 /events in ~3 s, each with full meta; events_after returns on the first event, runner.py:1170). Fix: after the first event keep collecting ~80-100 ms. Likely most of the #185 page cost.
5. Reproduced: a mid-turn settings change is dropped if any message is sent during that turn: send clears _close_after_turn (1086), _late_send (~1029) never checks it; tab close same path, process lingers. Fix: separate _restart_pending flag not cleared by send; check after _settle too.
6. Reproduced: double-click Send (or Enter auto-repeat) sends twice. No in-flight guard (app.js:811, enjoy.js:584). Fix: sending flag, disable until POST returns, clear input first and restore on failure.
7. Reproduced: settings 500 on bad types: {"model":[1]}, {"effort":{}}, {"mode":["x"]} (web_app.py:345-370 unhashable); limits "1e999"/"Infinity"/raw Infinity OverflowError (runner.py:236-239). Fix: isinstance str checks, catch OverflowError, math.isfinite.
8. Reproduced: {"archived":"false"} archives (bool("false"), web_app.py:389); name ["a"] stored as "['a']". Accept real bools/strings only.
9. Reproduced: /api/send files: 5 -> 500, "abc" iterates characters (web_app.py:559). Require list of str.
10. Reproduced: setInterval(refreshTabs, 4000) (app.js:1036) runs while hidden; the open conversation's long-poll keeps drawing while hidden. Gate on visibility (shared/forge_idle.js exists now).
11. Suspected: infinite CSS pulse animations in classic layout (app.css:20, 212, 255, 267), no no-anim/reduced-motion gating unlike enjoy.css; a .ev.working dot on a cut-off tool call pulses forever; in WebKitGTK that repaints continuously (fits the 87% CPU figure in WIP). Fix: gating + pause while hidden.
12. Suspected: meta mutated and serialised by several threads without a lock (save_meta 858 locks only the write; json.dumps indent=2 is pure-Python; FastAPI encodes conv.meta for /events concurrently). 0 failures in ~3000 hammered requests. Fix: one meta lock, serialise a dict copy under it.
13. Suspected: stop then quick send could lose the message (same as #1; fixed by #1's lock).

Fine: 5100-event conversation (1.2 MB /events in 0.08 s; open 0.36 s classic, 0.43 s Enjoy; switch back 0.01 s); titles cut to 80 chars; after=-5, wait=nan, unknown limit keys handled.
Not tested: two pages on one conversation; closing a tab in the UI mid-turn; toggling Ultracode/Limits through the UI mid-turn.
