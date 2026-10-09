"""Terminal windows and tabs, driven by keystrokes.

`open_terminal` is headless by default (Emerson, 2026-09-27): it starts one of
the background shells in tools/shell.py and returns the output; with
terminal_view set to "visible" it opens a real window as before.

Emerson asked for kitty to be left alone and uses GNOME Terminal, so there is
no terminal remote control: new tabs, switching and closing are the
terminal's own shortcuts sent to its window. Each supported terminal's shortcuts live in
one table, so another terminal is one more row.
"""

from __future__ import annotations

import shutil
import time
from pathlib import Path
from typing import Annotated

from .. import settings, shells
from ..registry import ToolError, tool
from ..sysutil import spawn
from ..sysutil import folder as find_folder
from . import windows
from .shell import _result

TOOLSET = "terminal"
TOOLSET_SUMMARY = (
    "open terminals, open/switch/close terminal tabs, type commands into a terminal"
)

TOOLSET_KEYWORDS = (
    "terminal",
    "console",
    "shell tab",
    "new tab",
    "gnome terminal",
    "kitty",
)
# (what a person says, tool, arguments): few-shot lines for the prompt
TOOLSET_EXAMPLES = [
    ("open a terminal in my Forge folder", "open_terminal", {"folder": "~/Forge"}),
    ("open a new terminal tab and run htop", "terminal_new_tab", {"command": "htop"}),
]

# class substring -> shortcuts
SHORTCUTS = {
    "kitty": {
        "new_tab": "ctrl+shift+t",
        "next": "ctrl+shift+right",
        "previous": "ctrl+shift+left",
        "close": "ctrl+shift+q",
    },
    "console": {
        "new_tab": "ctrl+shift+t",
        "next": "ctrl+Next",
        "previous": "ctrl+Prior",
        "close": "ctrl+shift+w",
    },
    "terminal": {
        "new_tab": "ctrl+shift+t",
        "next": "ctrl+Next",
        "previous": "ctrl+Prior",
        "close": "ctrl+shift+w",
    },
}


def _terminal() -> tuple[dict, dict]:
    win = windows.find_window("terminal")
    cls = (win.get("class") or "").lower()
    for key, keys in SHORTCUTS.items():
        if key in cls:
            return win, keys
    raise ToolError(f"{win.get('class')} is not a terminal I know the shortcuts for.")


@tool(TOOLSET, example={"command": "htop", "folder": "~"}, voice="fast")
def open_terminal(
    command: Annotated[str, "Command to run in it; empty for a plain shell"] = "",
    folder: Annotated[str, "Folder to start in"] = "~",
) -> str:
    """Open a terminal window for the user, or with a command run it in a headless shell and return the output."""
    where = str(find_folder(folder))
    # A bare "open a terminal" is a person who wants one on screen; headless
    # only makes sense when there is a command whose output comes back.
    if command and settings.load()["terminal_view"] != "visible":
        name = Path(where).name or "main"
        shell, _new = shells.get(name, where)
        done = f"Opened background shell '{shell.name}' in {where}."
        if command:
            done += f"\n{_result(shell.run(command, 60))}"
        return done + " Say 'show the terminal' to watch it."
    if shutil.which("gnome-terminal"):
        cmd = ["gnome-terminal", f"--working-directory={where}"]
        if command:
            cmd += ["--", "bash", "-lc", command + "; exec bash"]
    else:
        cmd = ["kitty", "--directory", where]
        if command:
            cmd += ["--hold", "bash", "-lc", command]
    spawn(cmd)
    return "Opened a terminal" + (f" running {command}." if command else ".")


@tool(TOOLSET, example={"command": "ls"}, voice="fast")
def terminal_new_tab(
    command: Annotated[str, "Command to type in the new tab"] = "",
) -> str:
    """Open a new tab in the terminal window, optionally typing a command into it."""
    win, keys = _terminal()
    windows.focus(win)
    windows.send_keys([keys["new_tab"]])
    if command:
        time.sleep(0.5)
        windows.type_into(command)
        windows.send_keys(["enter"])
    return "Opened a new terminal tab" + (f" and ran {command}." if command else ".")


@tool(TOOLSET, example={"direction": "next", "times": 1}, voice="ok")
def terminal_switch_tab(
    direction: Annotated[str, "next or previous"] = "next",
    times: Annotated[int, "How many tabs to move"] = 1,
) -> str:
    """Switch to the next or previous tab in the terminal."""
    win, keys = _terminal()
    key = keys["previous"] if direction.lower().startswith("p") else keys["next"]
    windows.focus(win)
    windows.send_keys([key] * max(1, min(times, 20)))
    return f"Moved {times} tab(s) {direction}."


@tool(TOOLSET, risky=True)
def terminal_close_tab() -> str:
    """Close the current terminal tab."""
    win, keys = _terminal()
    windows.focus(win)
    windows.send_keys([keys["close"]])
    return "Closed the terminal tab."


@tool(TOOLSET, example={"text": "git pull", "enter": True})
def terminal_type(
    text: Annotated[str, "Text or command to type into the terminal"],
    enter: Annotated[bool, "Press Enter afterwards to run it"] = True,
) -> str:
    """Type a command into the terminal window you can see. To get a command's output back, use run_command instead."""
    win, _keys = _terminal()
    windows.focus(win)
    windows.type_into(text)
    if enter:
        windows.send_keys(["enter"])
    return f"Typed into {win.get('class')}."
