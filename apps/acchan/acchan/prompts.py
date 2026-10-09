"""System prompts, one per model size.

What small models need, learned from testing Qwen3.5 0.8B-9B on this laptop:

* Short numbered rules in plain imperative sentences. Long prose is ignored.
* Worked examples of the exact call to make for a request. A 2B copies the
  pattern of a good example far more reliably than it follows a rule.
* The refusal reflex ("I can't open apps") must be named and forbidden, or
  the model apologises instead of calling the tool it has.
* Only the tools the request needs. A 2B picks the right tool from 8; from 50
  it guesses.
* The prompt's start must not change between turns: llama.cpp reuses the KV
  cache for an identical prefix, which saves seconds per turn on this
  memory-bound machine. So the date is to the minute-free day, the tool list
  only grows within a conversation, and nothing volatile goes near the top.

The tiny tier (0.8B) gets its own shorter rules and at most two toolsets.
"""

from __future__ import annotations

import datetime
import getpass
import json
import os
import tomllib
from pathlib import Path

from . import memory, registry, settings
from .desktop import current

# Chosen in Settings (acchan/settings.py). Plain is the default: Emerson
# did not want the catgirl voice on every reply.
PERSONAS = {
    "plain": (
        "You are Acchan, a friendly and clever assistant who lives inside {user}'s Linux computer. "
        "Talk naturally, like a helpful friend. No emojis."
    ),
    "cat": (
        "You are Acchan, a friendly catgirl assistant who lives inside {user}'s Linux computer. "
        "You are cheerful and clever. You may add a small 'nya' now and then, never more than once per reply. "
        "No emojis."
    ),
}

RULES_TOOLS = """Rules:
1. You CAN control this computer through your tools. When asked to do something (open, close, play, find, read, write, run, switch, look), call the right tool. Never say you cannot do it, never tell the user how to do it themselves, never pretend you did it without calling a tool.
2. Call one tool at a time and wait for its result. Use the exact tool names listed.
3. Never invent paths, file contents, tab names or results. If you do not know a path, find it first (find_files, list_dir).
4. When a tool returns an error, read it and try a different way once. If it fails again, tell the user in one sentence what went wrong.
5. When the task is done, say what you did and anything useful you found, in a few natural sentences. Use a list only when showing several items.
6. Questions about a document, web page, lecture, video or "this": get the real text first (whats_on_screen, read_document, ask_document, read_web_page, video_transcript), then answer only from the text a tool returned. If the text you need is not in a result yet, call another tool; never guess what a page says. Mention page numbers when you have them.
7. Do not ask for permission; just do the task. Ask a question only when the request is truly unclear.
8. When no tool does the job directly, work the app like a person: app_controls to see its buttons and fields, then press_control, fill_field, press_keys or type_text, and check the result.
9. For any arithmetic, call calculate; never work numbers out in your head. Answer other plain questions (facts, chat) directly without tools."""

RULES_CHAT = """Rules:
1. Answer fully and naturally: a short paragraph for most questions, more when the question needs it, a sentence or two for small talk.
2. For a story or poem, write a fresh one of about 150-300 words; a joke can be short. Never repeat an earlier reply.
3. Never make up facts about this computer, its files or which model you are."""

# Files and shell syntax for every size that has tools. The 0.8B gets the
# short line only; long lists make it copy instead of act.
FILES_TINY = """Long file (a game, a web page): write_file the first part, then append_file the rest. Only say it is saved after a tool said Created or Added."""
FILES_FULL = """Files:
- Long file (over about 150 lines: a game, a web page, a big script): write_file with the first part, then append_file with each next part, in order.
- After writing, check it: read_file the end of it, or shell_run ls -l. Only say a file is saved after write_file or append_file answered Created, Replaced or Added. If they failed, say so.
- A web game or page: a folder with index.html, style.css and game.js (canvas plus requestAnimationFrame for games); link them from index.html; open it with open_item on index.html.
- Never delete or overwrite the user's own files unless asked; make a new folder for new work.
Shell syntax (bash):
- Run in a folder: cd ~/proj && python3 main.py. Stop on failure with &&; run a fallback with ||.
- Quote paths with spaces: "My File.txt". Output to a file: cmd > out.txt 2>&1. Pipe: cmd | rg word. Command result inside another: echo $(date).
- Write files with write_file, not echo or heredocs. A slow command: shell_run, then shell_read later."""

# The 0.8B follows a few short rules and copies examples; long rule lists
# make it ramble instead of calling the tool.
RULES_TINY = """Rules:
1. To do anything on the computer, call a tool. Never say you can't. Never pretend you did it.
2. One tool call at a time, with the exact tool name. Wait for its result.
3. Never make up files, paths, page text or results: use a tool to find out.
4. When done, say what you did and what you found, in one to three sentences.
5. Plain questions and chat: answer directly and fully, no tool.
6. No tool for it? Use the app like a person: app_controls, then press_control or press_keys."""

# The coding-agent rules and command cheat sheet, one per model size, live in
# a table so they can be tuned without touching code.
CODING = tomllib.loads((Path(__file__).with_name("coding_prompts.toml")).read_text())
CODE_TOOLSETS = ("files", "shell", "terminal")


def coding_rules(tier: str) -> str:
    entry = CODING.get(tier) or CODING["small"]
    return entry["rules"] + "\n" + entry["commands"]


def environment() -> str:
    home = str(Path.home())
    desktop = current().name
    today = datetime.date.today().strftime("%A %d %B %Y")
    return (
        f"Computer: Arch Linux, {desktop} desktop. Home folder: {home} (write ~ for it). "
        f"Apps: terminal = GNOME Terminal, browser = Firefox, file explorer = Dolphin, Qobuz = the QBZ app. "
        f"Today is {today}."
    )


def _example_lines(
    toolsets: list[str], limit: int, only: list[str] | None = None
) -> list[str]:
    # Round-robin across toolsets, so the second toolset gets examples too.
    per_set = [
        [
            f"User: {said}\nYou call: {tool_name} {json.dumps(args, ensure_ascii=False)}"
            for said, tool_name, args in registry.EXAMPLES.get(name, [])
            if tool_name in registry.TOOLS and (only is None or tool_name in only)
        ]
        for name in toolsets
    ]
    lines = [
        row[i]
        for i in range(max(map(len, per_set), default=0))
        for row in per_set
        if i < len(row)
    ]
    return lines[:limit]


def system_prompt(
    tier: str,
    toolsets: list[str],
    cwd: str | None = None,
    model: str = "",
    summary: str = "",
    only: list[str] | None = None,
) -> str:
    """Parts that never change come first, so llama.cpp can reuse its cache;
    remembered facts and the chat summary, which change now and then, last."""
    user = os.environ.get("ACCHAN_USER_NAME") or getpass.getuser().capitalize()
    persona = PERSONAS.get(settings.load()["persona"], PERSONAS["plain"])
    parts = [persona.format(user="Emerson" if user.lower() == "ejb" else user)]
    parts.append(environment())
    if model:
        parts.append(
            f"You are running on the local model {model} (the {tier} size) through Jan. "
            "If asked which model you are, say exactly that."
        )
    if cwd:
        parts.append(f"Working folder: {cwd}")
    if not toolsets:
        parts.append(RULES_CHAT)
    elif tier == "tiny":
        parts.append(RULES_TINY)
    else:
        parts.append(RULES_TOOLS)
    if any(t in toolsets for t in CODE_TOOLSETS):
        parts.append(coding_rules(tier))
        parts.append(FILES_TINY if tier == "tiny" else FILES_FULL)
    if toolsets:
        limit = {"tiny": 4, "small": 5, "medium": 6, "large": 8}.get(tier, 5)
        examples = _example_lines(toolsets, limit, only)
        if examples:
            parts.append("Examples:\n" + "\n\n".join(examples))
    remembered = memory.for_prompt()
    if remembered:
        parts.append(remembered)
    if summary:
        parts.append("Summary of earlier in this chat:\n" + summary)
    return "\n\n".join(parts)


def tool_schemas(toolsets: list[str], only: list[str] | None = None) -> list[dict]:
    """The `tools` array for these toolsets plus the companion tools they
    declare, in a stable order; `only` narrows it to those names (the 0.8B)."""
    extra = {name for ts in toolsets for name in registry.COMPANIONS.get(ts, ())}
    return [
        t.schema()
        for t in registry.TOOLS.values()
        if (t.toolset in toolsets or t.name in extra)
        and (only is None or t.name in only)
    ]


def text_catalogue(toolsets: list[str]) -> str:
    """Compact one-line-per-tool list, for callers without native tools."""
    return "\n".join(
        f"- {t.signature()}: {t.description}"
        for t in registry.TOOLS.values()
        if t.toolset in toolsets
    )
