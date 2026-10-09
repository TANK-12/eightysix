"""Prompt evaluation against the real Jan models (not a pytest test: it needs
Jan and takes minutes).

Every tool is replaced by a stub that records the call and returns a canned
result, so nothing on the desktop changes. Each case names the tool(s) a
good first call would use. Scores are printed per tier and saved to
~/.cache/acchan/eval-<tier>.json so prompt changes can be compared.

    .venv/bin/python tests/eval_prompts.py small medium
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from acchan import registry  # noqa: E402
from acchan.agent import Agent  # noqa: E402
from acchan.conversation import Conversation  # noqa: E402

CANNED = {
    "list_dir": "/home/ejb/Downloads:\nlecture5.pdf  (2.1 MB)\nsetup.exe  (40 MB)\nphoto.jpg  (3 MB)",
    "find_files": "/home/ejb/Documents/uni/MATH1014/lecture5.pdf\n/home/ejb/Documents/uni/MATH1014/lecture4.pdf",
    "read_file": "    1  def add(a, b):\n    2      return a - b\n",
    "edit_file": "Edited app.py: replaced 1 block.",
    "write_file": "Created /home/ejb/notes/todo.md (3 lines).",
    "search_text": "/home/ejb/project/app.py:12: def main():",
    "run_command": "exit code 0\nOn branch main\nnothing to commit, working tree clean",
    "ask_document": "From lecture5.pdf, the most relevant passages:\n\n[page 7]\nThe derivative of ln x is 1/x for x > 0.",
    "read_document": "# lecture5.pdf\n[page 1]\nMATH1014 Lecture 5: Logarithms and their derivatives...",
    "whats_on_screen": "Focused window: org.gnome.Papers — lecture5.pdf\nDocument file: /home/ejb/Documents/uni/MATH1014/lecture5.pdf (showing page 3)\nTo read all of it: read_document or ask_document with that path.",
    "browser_tabs": "* w1 #1  Qobuz Player  <https://play.qobuz.com/>\n  w1 #2  YouTube  <https://youtube.com>",
    "web_search": "- Bali flights from Perth\n  https://example.com/flights\n  Cheap flights from $199",
    "read_web_page": "# Article\nThe battery lasts 12 hours...",
    "video_transcript": "Relevant parts:\n[00:03:10] batteries degrade faster in heat",
    "calculate": "result",
    "ask_course": "From the MATH1014 notes:\n\n[topic t5_limits]\nAs x grows without bound, 1/x approaches 0; divide top and bottom by the highest power of x.",
    "recall": "- Emerson's calculus exam is on 3 November",
    "weather": "Perth: Sunny, +17°C, wind 15km/h, rain 0.0mm",
    "what_time": "It is 18:30 on Wednesday 23 September 2026.",
    "wifi": "Connected to meloncherry (signal 77%).",
    "now_playing": "firefox: Playing | Nujabes - Aruarian Dance | 1:02/4:20 | vol 0.8",
}

CASES = [
    ("what's in my downloads folder?", {"list_dir"}),
    ("find my MATH1014 lecture 5 notes", {"find_files"}),
    (
        "in ~/Documents/uni/MATH1014/lecture5.pdf what is the derivative of ln x?",
        {"ask_document", "read_document"},
    ),
    ("explain what's on page 3 of the pdf I have open", {"whats_on_screen"}),
    ("what tabs have I got open in firefox?", {"browser_tabs"}),
    ("search the web for cheap flights from Perth to Bali", {"web_search", "open_web"}),
    ("what is 348 times 29?", {"calculate"}),
    (
        "the add function in ~/project/app.py is broken, fix it",
        {"read_file", "search_text"},
    ),
    ("run git status in ~/project", {"run_command"}),
    (
        "make a todo list file at ~/notes/todo.md with milk, eggs and bread",
        {"write_file"},
    ),
    ("what's playing right now?", {"now_playing"}),
    ("skip this song on qobuz", {"media_control"}),
    (
        "summarise what this video says about batteries: https://youtu.be/abc123",
        {"video_transcript"},
    ),
    ("remind me in 20 minutes to check the oven", {"remind_me"}),
    ("copy 'hello world' to my clipboard", {"set_clipboard"}),
    ("close the dolphin window", {"close_window"}),
    # pressing play through MPRIS is as good as clicking the button
    (
        "click the play button in qbz",
        {"press_control", "app_controls", "media_control"},
    ),
    ("open a terminal in my Forge folder", {"open_terminal"}),
    ("what windows do I have open?", {"list_windows"}),
    ("read me the first page of the pdf on my screen", {"whats_on_screen"}),
    ("in my calculus class, how do limits at infinity work?", {"ask_course"}),
    (
        "open a terminal in my Forge folder and list the files",
        # launch_app(terminal, folder) hands over to open_terminal
        {"open_terminal", "list_dir", "launch_app"},
    ),
    # 2026-09-23: Emerson's own messages, typos included (None = no tool is right)
    ("what model is this?", {None}),
    ("open a new firfox window", {"open_web", "launch_app"}),
    ("open a firefox indow and tb", {"open_web", "launch_app"}),
    ("wriet a story", {None}),
    ("remember that my calculus exam is on the 3rd of November", {"remember"}),
    ("what's the weather like in Perth?", {"weather"}),
    ("what time is it?", {"what_time", "system_status"}),
    ("make the screen a bit brighter", {"set_brightness"}),
    ("is my wifi connected?", {"wifi"}),
    ("create a python script ~/project/hello.py that prints hello", {"write_file"}),
    # 2026-09-23 evening: the second log, and requests only a model can place
    ("open wikipeida tab", {"open_web"}),
    ("list th etabs i have open", {"browser_tabs"}),
    ("what is 1234 * 5678", {"calculate"}),
    ("opena new text doc", {"launch_app"}),
    ("open youtube in a new tab", {"open_web"}),
    ("can you pull up github in firefox so I can check my repos", {"open_web"}),
    ("anything interesting in my open tabs?", {"browser_tabs"}),
    ("switch to the tab with my uni portal", {"switch_tab", "browser_tabs"}),
    ("scroll down a bit in firefox", {"scroll"}),
    ("go back a page in firefox", {"navigate"}),
    ("tell me a fun fact about octopuses", {None}),
]


def stub_all() -> list[tuple[str, dict]]:
    calls: list[tuple[str, dict]] = []
    for name, entry in registry.TOOLS.items():

        def fake(*_a, _name=name, **kw):
            calls.append((_name, kw))
            if _name == "calculate":
                expr = kw.get("expression", "")
                try:
                    return f"{expr} = {eval(expr.replace('^', '**'), {'__builtins__': {}})}"
                except Exception:
                    return "bad expression"
            return CANNED.get(_name, "done")

        entry.func = fake
    return calls


def main(tiers: list[str]) -> None:
    import tempfile

    import acchan.conversation as conversation

    # Eval chats go to a throwaway folder, never the user's chat list.
    conversation.DATA = Path(tempfile.mkdtemp(prefix="acchan-eval-"))
    registry.load_all()
    calls = stub_all()
    for tier in tiers:
        rows, good, started = [], 0, time.monotonic()
        for text, want in CASES:
            calls.clear()
            conv = Conversation(source="eval")
            agent = Agent(conv, forced_tier=tier)
            final, escalations, t0 = "", [], time.monotonic()
            try:
                for event in agent.run(text):
                    if event["type"] == "done":
                        final = event["text"]
                    elif event["type"] == "escalate":
                        escalations.append(event["to"])
                    elif event["type"] == "error":
                        final = "ERROR " + event["message"]
            except Exception as exc:  # the harness keeps going
                final = f"CRASH {type(exc).__name__}: {exc}"
            first = calls[0][0] if calls else None
            ok = first in want
            good += ok
            rows.append(
                {
                    "text": text,
                    "want": sorted(want),
                    "first": first,
                    "calls": calls[:6],
                    "ok": ok,
                    "final": final[:200],
                    "escalated": escalations,
                    "seconds": round(time.monotonic() - t0, 1),
                }
            )
            mark = "PASS" if ok else "FAIL"
            print(
                f"[{tier}] {mark} {rows[-1]['seconds']:>5}s  {text[:55]!r:58} first={first} calls={[c[0] for c in calls[:4]]} esc={escalations}",
                flush=True,
            )
            print(f"        reply: {final[:140]!r}", flush=True)
        total = round(time.monotonic() - started)
        print(
            f"== {tier}: {good}/{len(CASES)} first-call correct, {total}s", flush=True
        )
        out = Path.home() / ".cache/acchan" / f"eval-{tier}.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps(
                {"score": good, "of": len(CASES), "seconds": total, "rows": rows},
                indent=1,
                default=str,
            )
        )


if __name__ == "__main__":
    main(sys.argv[1:] or ["small"])
