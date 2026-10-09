"""Windows and workspaces, plus keystrokes into any window, on Hyprland or
GNOME (see desktop.py for how each is driven).

Windows are matched loosely: "firefox", "the pdf", "qobuz", "terminal" all
work, against the app class and the window title.
"""

from __future__ import annotations

import difflib
from typing import Annotated

from ..desktop import current
from ..registry import ToolError, tool

TOOLSET = "windows"
TOOLSET_SUMMARY = "list/focus/close/fullscreen/move windows, switch workspaces, press keys or type into any window"

TOOLSET_KEYWORDS = (
    "window",
    "windows",
    "focus",
    "switch to",
    "close",
    "fullscreen",
    "minimise",
    "workspace",
    "press",
    "shortcut",
    "type",
    "keyboard",
    "alt",
    "ctrl",
)
# (what a person says, tool, arguments): few-shot lines for the prompt
TOOLSET_EXAMPLES = [
    ("close this window", "close_window", {"window": "this"}),
    ("switch to firefox", "focus_window", {"window": "firefox"}),
]

ALIASES = {
    "terminal": ("terminal", "kitty", "console", "foot", "alacritty"),
    "file explorer": ("dolphin", "nautilus", "thunar", "files"),
    "files": ("dolphin", "nautilus", "thunar", "files"),
    "browser": ("firefox", "chromium", "chrome"),
    "pdf": ("okular", "evince", "papers", "zathura", ".pdf"),
    "qobuz": ("qbz", "qobuz"),
    "forge": ("forge",),
}
THIS = ("", "this", "current", "this window", "active", "focused", "it")


def clients() -> list[dict]:
    return current().windows()


def active() -> dict:
    return current().active()


def find_window(query: str) -> dict:
    """The window a person means. Empty query or 'this' = the focused one."""
    q = query.strip().lower()
    if q in THIS:
        win = active()
        if not win:
            raise ToolError("No window has focus.")
        return win
    wins = clients()
    if not wins:
        raise ToolError("There are no windows open.")
    needles = ALIASES.get(q, (q,))

    def score(win: dict) -> float:
        cls = (win.get("class") or "").lower()
        title = (win.get("title") or "").lower()
        best = 0.0
        for needle in needles:
            if needle == cls or cls.endswith("." + needle):
                best = max(best, 1.0)
            elif needle in cls:
                best = max(best, 0.9)
            elif needle in title:
                best = max(best, 0.8)
            else:
                best = max(
                    best, difflib.SequenceMatcher(None, needle, cls).ratio() * 0.8
                )
        return best - win.get("focusHistoryID", 0) * 0.001

    ranked = sorted(wins, key=score, reverse=True)
    if score(ranked[0]) < 0.55:
        names = ", ".join(sorted({w.get("class", "") for w in wins}))
        raise ToolError(f"No window matches {query!r}. Open windows: {names}.")
    return ranked[0]


def describe(win: dict) -> str:
    ws = win.get("workspace_name")
    where = f" (workspace {ws})" if ws else ""
    return f"{win.get('class')} — {(win.get('title') or '')[:80]}{where}"


def focus(win: dict) -> None:
    current().focus(win)


def send_keys(combos: list[str]) -> None:
    current().keys(combos)


def type_into(text: str) -> None:
    current().type_text(text)


@tool(
    TOOLSET,
    show=True,
    phrases=["what windows are open", "list windows", "show me windows"],
    voice="ok",
)
def list_windows() -> str:
    """List open windows with their app and title. The focused one is marked *."""
    rows = [f"{'*' if w.get('active') else ' '} {describe(w)}" for w in clients()]
    return "\n".join(rows) or "No windows open."


@tool(
    TOOLSET,
    example={"window": "firefox"},
    phrases=[
        "switch to {window}",
        "focus {window}",
        "go to {window} window",
        "show me {window} window",
        "bring up {window} window",
        "switch to {window} window",
    ],
    voice="ok",
)
def focus_window(
    window: Annotated[str, "App or title words, like firefox, terminal, pdf"],
) -> str:
    """Bring a window to the front and focus it."""
    win = find_window(window)
    focus(win)
    return f"Focused {describe(win)}."


@tool(TOOLSET, example={"window": "dolphin"}, risky=True)
def close_window(
    window: Annotated[str, "App or title words; 'this' for the focused window"],
) -> str:
    """Close a window (like clicking its X; the app may ask to save)."""
    win = find_window(window)
    current().close(win)
    return f"Closed {describe(win)}."


@tool(
    TOOLSET,
    example={"window": "this"},
    phrases=[
        "fullscreen",
        "full screen",
        "go fullscreen",
        "make it fullscreen",
        "make it full screen",
    ],
    voice="ok",
)
def fullscreen_window(
    window: Annotated[
        str, "App or title words; 'this' for the focused window"
    ] = "this",
) -> str:
    """Toggle fullscreen on a window."""
    win = find_window(window)
    current().fullscreen(win)
    return f"Toggled fullscreen on {describe(win)}."


@tool(TOOLSET, example={"window": "firefox", "workspace": "2"}, voice="ok")
def move_window(
    window: Annotated[str, "App or title words"],
    workspace: Annotated[str, "Workspace number to move it to"],
) -> str:
    """Move a window to another workspace."""
    win = find_window(window)
    current().move_to_workspace(win, workspace)
    return f"Moved {win.get('class')} to workspace {workspace}."


@tool(
    TOOLSET,
    example={"workspace": "3"},
    phrases=[
        "workspace {workspace}",
        "go to workspace {workspace}",
        "switch to workspace {workspace}",
        "show workspace {workspace}",
    ],
    voice="ok",
)
def switch_workspace(workspace: Annotated[str, "Workspace number"]) -> str:
    """Switch to a workspace."""
    current().switch_workspace(str(workspace))
    return f"Now on workspace {workspace}."


@tool(TOOLSET, example={"keys": "ctrl+t", "window": "firefox"})
def press_keys(
    keys: Annotated[
        str, "Key combos separated by spaces, like ctrl+t or ctrl+shift+tab or enter"
    ],
    window: Annotated[str, "Window to focus first; empty for the focused one"] = "",
) -> str:
    """Press keyboard shortcuts in a window. Works in any app."""
    if window.strip().lower() not in THIS:
        focus(find_window(window))
    combos = keys.split()
    send_keys(combos)
    return f"Pressed {' '.join(combos)}."


@tool(TOOLSET, example={"text": "hello", "window": "", "enter": False})
def type_text(
    text: Annotated[str, "Text to type"],
    window: Annotated[str, "Window to focus first; empty for the focused one"] = "",
    enter: Annotated[bool, "Press Enter afterwards"] = False,
) -> str:
    """Type text into a window as if on the keyboard."""
    if window.strip().lower() not in THIS:
        focus(find_window(window))
    type_into(text)
    if enter:
        send_keys(["enter"])
    return f"Typed {len(text)} characters."
