"""Running shell commands: one-shot, or in background shells that stay open.

The background shells (acchan/shells.py) are headless, Emerson's default
(2026-09-27): a real bash that keeps its folder, variables and activated venv
between calls and returns each command's output and exit code, which is what
the coding loop needs. With the terminal_view setting on "visible", or on
`shell_show`, a window follows the shell live. They all close with Acchan.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Annotated

from .. import settings, shells
from ..registry import ToolError, tool
from ..sysutil import clip, run, spawn
from ..sysutil import folder as find_folder
from ..sysutil import path as to_path

TOOLSET = "shell"
TOOLSET_SUMMARY = "run bash commands (git, python, package queries, anything), in background shells that keep their folder and state"

TOOLSET_KEYWORDS = (
    "run",
    "command",
    "terminal",
    "bash",
    "install",
    "git",
    "python",
    "pip",
    "pacman",
    "npm",
    "test",
    "compile",
    "build",
    "process",
    "kill",
    "disk",
    "ls",
    "grep",
    "shell",
    "headless",
    "background",
    "repl",
)
# (what a person says, tool, arguments): few-shot lines for the prompt
TOOLSET_EXAMPLES = [
    (
        "show git status in ~/project",
        "shell_run",
        {"command": "cd ~/project && git status"},
    ),
    (
        "run the tests in ~/project",
        "shell_run",
        {"command": "cd ~/project && python -m pytest -q"},
    ),
]


@tool(TOOLSET, example={"command": "git status", "folder": "~/project"}, risky=True)
def run_command(
    command: Annotated[str, "A bash command line"],
    folder: Annotated[str, "Folder to run it in"] = ".",
    timeout: Annotated[int, "Seconds before giving up"] = 60,
) -> str:
    """Run a bash command and return its exit code and output. Do not use it to open apps or files: use launch_app or open_item."""
    code, out = run(command, timeout=max(1, min(timeout, 600)), cwd=to_path(folder))
    out = clip(out.strip(), 6000) or "(no output)"
    return f"exit code {code}\n{out}"


def _result(result: shells.Result) -> str:
    return clip(str(result), 6000)


def _open(name: str, folder: str) -> shells.Shell:
    where = find_folder(folder) if folder else None
    shell, new = shells.get(name, where)
    if new and settings.load()["terminal_view"] == "visible":
        _show(shell)
    return shell


def _show(shell: shells.Shell) -> None:
    """A terminal window that follows the shell and takes typing
    (acchan/shell_window.py); it closes when the shell or Acchan ends."""
    view = [
        "python3",
        str(Path(shells.__file__).with_name("shell_window.py")),
        shell.name,
        str(shell.log),
        str(shell.proc.pid),
        os.environ.get("ACCHAN_PORT", "8451"),
    ]
    if shutil.which("gnome-terminal"):
        spawn(["gnome-terminal", f"--title=Acchan: {shell.name}", "--"] + view)
    else:
        spawn(["kitty", "--title", f"Acchan: {shell.name}"] + view)


@tool(
    TOOLSET, example={"command": "git status", "shell": "main", "folder": "~/project"}
)
def shell_run(
    command: Annotated[str, "A bash command line"],
    shell: Annotated[
        str, "Name of the background shell; it keeps its folder and variables"
    ] = "main",
    folder: Annotated[str, "Folder a new shell starts in"] = "~",
    timeout: Annotated[
        int, "Seconds to wait before returning what it printed so far"
    ] = 60,
) -> str:
    """Run a command in a background shell that stays open (cd and variables carry over) and return its exit code and output."""
    return _result(_open(shell, folder).run(command, max(1, min(timeout, 600))))


@tool(TOOLSET, example={"text": "y", "shell": "main"})
def shell_send(
    text: Annotated[
        str, "Text to type (Enter is pressed after it), or ctrl+c / ctrl+d"
    ],
    shell: Annotated[str, "Name of the background shell"] = "main",
    wait: Annotated[float, "Seconds to wait for its reply"] = 1.0,
) -> str:
    """Type into a background shell's running program (answer a prompt, use a REPL, stop it with ctrl+c) and return what it printed."""
    target = shells.SHELLS.get(shell)
    if not target or not target.alive():
        raise ToolError(
            f"No background shell named '{shell}'. Start one with shell_run."
        )
    key = shells.CONTROL.get(text.strip().lower())
    return clip(target.send(key or text, wait=wait) or "(nothing printed)", 6000)


@tool(TOOLSET, example={"shell": "main"}, voice="ok")
def shell_read(shell: Annotated[str, "Name of the background shell"] = "main") -> str:
    """Read what a background shell printed since you last looked (for long-running commands)."""
    target = shells.SHELLS.get(shell)
    if not target:
        raise ToolError(f"No background shell named '{shell}'.")
    state = "" if target.alive() else " (the shell has ended)"
    return clip(target.read() or "(nothing new)", 6000) + state


@tool(TOOLSET, show=True, voice="ok")
def shell_list() -> str:
    """List Acchan's background shells."""
    live = [s for s in shells.SHELLS.values()]
    if not live:
        return "No background shells are open."
    return "\n".join(
        f"{s.name}: {'running' if s.alive() else 'ended'}, started in {s.folder}"
        for s in live
    )


@tool(TOOLSET, example={"shell": "main"}, voice="ok")
def shell_show(shell: Annotated[str, "Name of the background shell"] = "main") -> str:
    """Open a window that shows a background shell live, so the user can watch it."""
    target = shells.SHELLS.get(shell) or _open(shell, "~")
    _show(target)
    return f"Showing background shell '{target.name}' in a window."


@tool(TOOLSET, example={"shell": "main"})
def shell_close(
    shell: Annotated[
        str, "Name of the background shell; 'all' closes every one"
    ] = "main",
) -> str:
    """Close a background shell and everything running in it."""
    if shell.lower() == "all":
        count = len(shells.SHELLS)
        shells.close_all()
        return f"Closed {count} background shell(s)."
    if not shells.close(shell):
        raise ToolError(f"No background shell named '{shell}'.")
    return f"Closed background shell '{shell}'."
