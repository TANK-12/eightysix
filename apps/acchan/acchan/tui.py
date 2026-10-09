"""Acchan in the terminal: a full-screen Textual app, or one-shot.

    acchan                      full-screen chat (working folder = where you ran it)
    acchan "fix the failing test"    one message, printed plainly, then exit
    acchan -c                   continue the most recent terminal conversation
    acchan -m medium ...        force a model size (tiny/small/medium/large)

Keys in the app: Enter send · Ctrl+N new chat · Ctrl+T cycle model size ·
Escape stop · Ctrl+O open a past chat · Ctrl+Q quit.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from acchan import client  # noqa: E402
from acchan.conversation import Conversation  # noqa: E402

TIERS = [None, "switch", "tiny", "small", "medium", "large"]
TIER_LABEL = {
    None: "auto (one model)",
    "switch": "switch per message",
    "tiny": "0.8B",
    "small": "2B",
    "medium": "4B",
    "large": "9B",
}


def one_shot(text: str, conversation: str | None, tier: str | None) -> int:
    dim, pink, red, reset = "\033[2m", "\033[38;5;211m", "\033[31m", "\033[0m"
    if not sys.stdout.isatty():
        dim = pink = red = reset = ""
    code = 0
    for event in client.send(text, conversation, tier, os.getcwd(), source="cli"):
        kind = event["type"]
        if kind == "tool":
            args = " ".join(
                f"{k}={json.dumps(v, ensure_ascii=False)}"
                for k, v in event["args"].items()
            )
            print(f"{dim}→ {event['name']} {args[:160]}{reset}", flush=True)
        elif kind == "result" and not event["ok"]:
            print(f"{red}  {event['result'][:300]}{reset}", flush=True)
        elif kind == "escalate":
            print(f"{dim}  (switching to the {event['to']} model){reset}", flush=True)
        elif kind == "text":
            print(f"{pink}{event['delta']}{reset}", flush=True)
        elif kind == "error":
            print(f"{red}{event['message']}{reset}", flush=True)
            code = 1
    return code


def run_app(conversation: str | None, tier: str | None) -> None:
    build_app(conversation, tier).run()


def build_app(conversation: str | None, tier: str | None):
    """The Textual app, unstarted (tests drive it with run_test)."""
    from textual import on, work
    from textual.app import App, ComposeResult
    from textual.binding import Binding
    from textual.containers import VerticalScroll
    from textual.widgets import (
        Collapsible,
        Footer,
        Header,
        Input,
        Markdown,
        OptionList,
        Static,
    )
    from textual.widgets.option_list import Option

    class ChatApp(App):
        TITLE = "Acchan"
        CSS = """
        Screen { background: $surface; }
        #log { padding: 0 1; }
        .user { margin: 1 0 0 12; padding: 0 1; background: $panel; color: $text; }
        .assistant { margin: 1 8 0 0; }
        .note { color: $text-muted; margin: 0 0 0 1; }
        .error { color: $error; margin: 0 0 0 1; }
        Collapsible { margin: 0 8 0 0; padding: 0; border: none; background: $surface; }
        .tool-result { color: $text-muted; }
        #input { dock: bottom; margin: 0 1 1 1; }
        #picker { dock: right; width: 50; display: none; border-left: tall $panel; }
        #picker.shown { display: block; }
        """
        BINDINGS = [
            Binding("ctrl+n", "new_chat", "New chat"),
            Binding("ctrl+t", "cycle_tier", "Model size"),
            Binding("ctrl+o", "pick_chat", "Past chats"),
            Binding("escape", "stop", "Stop"),
            Binding("ctrl+q", "quit", "Quit"),
        ]

        def __init__(self) -> None:
            super().__init__()
            self.conversation = conversation
            self.tier = tier
            self.busy = False
            self.cards: dict[str, tuple[Collapsible, Static]] = {}

        def compose(self) -> ComposeResult:
            yield Header(show_clock=True)
            yield VerticalScroll(id="log")
            yield OptionList(id="picker")
            yield Input(
                placeholder="Ask Acchan…  (Ctrl+T model size · Ctrl+O past chats)",
                id="input",
            )
            yield Footer()

        def on_mount(self) -> None:
            self.update_title()
            log = self.query_one("#log", VerticalScroll)
            if self.conversation:
                self.replay(self.conversation)
            else:
                log.mount(
                    Static(
                        "🐱 Hi! I'm Acchan. Ask me to code, open things, manage windows and tabs, play music, or read documents and videos.",
                        classes="note",
                    )
                )
            self.query_one("#input", Input).focus()

        def update_title(self) -> None:
            where = "backend" if client.backend_up() else "local"
            self.sub_title = f"{os.getcwd()} · model {TIER_LABEL[self.tier]} · {where}"

        def add(self, widget) -> None:
            log = self.query_one("#log", VerticalScroll)
            log.mount(widget)
            log.scroll_end(animate=False)

        def replay(self, cid: str) -> None:
            try:
                conv = Conversation.load(cid)
            except (OSError, ValueError):
                return
            log = self.query_one("#log", VerticalScroll)
            log.remove_children()
            for m in conv.messages:
                if m["role"] == "user" and not m["content"].startswith(
                    ("(Note:", "You do have tools", "Stop using tools")
                ):
                    shown = re.sub(r"^\(Working folder: [^)]*\)\n", "", m["content"])
                    self.add(Static(shown, classes="user"))
                elif m["role"] == "assistant":
                    for call in m.get("tool_calls") or []:
                        fn = call["function"]
                        self.add(
                            Collapsible(
                                Static(fn["arguments"][:600]),
                                title=f"→ {fn['name']}",
                                collapsed=True,
                            )
                        )
                    if m.get("content"):
                        self.add(Markdown(m["content"], classes="assistant"))

        @on(Input.Submitted, "#input")
        def submitted(self, event: Input.Submitted) -> None:
            text = event.value.strip()
            if not text or self.busy:
                return
            event.input.value = ""
            self.add(Static(text, classes="user"))
            self.busy = True
            self.run_message(text)

        @work(thread=True, exclusive=True)
        def run_message(self, text: str) -> None:
            reply = ""
            try:
                for event in client.send(
                    text, self.conversation, self.tier, os.getcwd(), source="tui"
                ):
                    self.call_from_thread(self.handle, event)
                    if event["type"] == "text":
                        reply += event["delta"]
            except Exception as exc:
                self.call_from_thread(
                    self.add, Static(f"{type(exc).__name__}: {exc}", classes="error")
                )
            finally:
                self.busy = False

        def handle(self, event: dict) -> None:
            kind = event["type"]
            if kind == "start":
                self.conversation = event["conversation"]
            elif kind == "tool":
                args = " ".join(
                    f"{k}={json.dumps(v, ensure_ascii=False)}"
                    for k, v in event["args"].items()
                )
                body = Static("…", classes="tool-result")
                card = Collapsible(
                    body, title=f"→ {event['name']} {args[:90]}", collapsed=True
                )
                # Keep the body itself: query_one(Static) would find the
                # card's title first (it is a Static too) and overwrite it.
                self.cards[event["id"]] = (card, body)
                self.add(card)
            elif kind == "result":
                found = self.cards.get(event["id"])
                if found is not None:
                    card, body = found
                    mark = "✓ " if event["ok"] else "✗ "
                    card.title = mark + card.title.removeprefix("→ ")
                    body.update(event["result"][:3000])
            elif kind == "escalate":
                self.add(
                    Static(
                        f"switching up to the {event['to']} model ({event['why']})",
                        classes="note",
                    )
                )
            elif kind == "text":
                self.add(Markdown(event["delta"], classes="assistant"))
            elif kind == "error":
                self.add(Static(event["message"], classes="error"))
            elif kind == "done":
                stats = event.get("stats") or {}
                if stats.get("seconds") is not None:
                    self.add(
                        Static(
                            f"{stats.get('tier', 'instant')} · {stats['seconds']}s",
                            classes="note",
                        )
                    )

        def action_new_chat(self) -> None:
            self.conversation = None
            log = self.query_one("#log", VerticalScroll)
            log.remove_children()
            self.add(Static("New chat. 🐱", classes="note"))

        def action_cycle_tier(self) -> None:
            self.tier = TIERS[(TIERS.index(self.tier) + 1) % len(TIERS)]
            self.update_title()
            self.notify(f"Model size: {TIER_LABEL[self.tier]}")

        def action_stop(self) -> None:
            picker = self.query_one("#picker", OptionList)
            if picker.has_class("shown"):
                picker.remove_class("shown")
                self.query_one("#input", Input).focus()
                return
            if self.busy:
                client.stop(self.conversation)
                self.notify("Stopping…")

        def action_pick_chat(self) -> None:
            picker = self.query_one("#picker", OptionList)
            picker.clear_options()
            for row in Conversation.list_all()[:60]:
                picker.add_option(
                    Option(f"{row['title'][:44]}  [{row['source']}]", id=row["id"])
                )
            picker.add_class("shown")
            picker.focus()

        @on(OptionList.OptionSelected, "#picker")
        def picked(self, event: OptionList.OptionSelected) -> None:
            self.conversation = event.option.id
            event.option_list.remove_class("shown")
            if self.conversation:
                self.replay(self.conversation)
            self.query_one("#input", Input).focus()

    return ChatApp()


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="acchan", description="Acchan, the local assistant."
    )
    parser.add_argument("message", nargs="*", help="send one message and exit")
    parser.add_argument(
        "-m",
        "--model",
        choices=["tiny", "small", "medium", "large"],
        help="force a model size",
    )
    parser.add_argument(
        "-c",
        "--continue",
        dest="cont",
        action="store_true",
        help="continue the latest terminal chat",
    )
    args = parser.parse_args()
    conversation = None
    if args.cont:
        recent = [r for r in Conversation.list_all() if r["source"] in ("tui", "cli")]
        conversation = recent[0]["id"] if recent else None
    if args.message:
        sys.exit(one_shot(" ".join(args.message), conversation, args.model))
    if not sys.stdin.isatty():
        piped = sys.stdin.read().strip()
        if piped:
            sys.exit(one_shot(piped, conversation, args.model))
    run_app(conversation, args.model)


if __name__ == "__main__":
    main()
