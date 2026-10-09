"""Controls inside any app: see its buttons and fields, press them, fill them.

Uses the accessibility tree (AT-SPI), which GTK, Qt, Electron and most apps
publish, so this works on apps nobody wrote a tool for. When an app publishes
nothing, the error says to fall back to press_keys or look_at_screen.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

from ..registry import ToolError, tool
from ..sysutil import json_line, run
from .windows import find_window

TOOLSET = "ui"
TOOLSET_SUMMARY = "see and press buttons, menus, tabs and fields inside any app window"

TOOLSET_KEYWORDS = (
    "button",
    "click",
    "press the",
    "menu",
    "field",
    "type into",
    "fill",
    "control",
    "checkbox",
    "setting in",
)
# (what a person says, tool, arguments): few-shot lines for the prompt
TOOLSET_EXAMPLES = [
    (
        "click the Play button in QBZ",
        "press_control",
        {"window": "qbz", "control": "Play"},
    )
]

HELPER = str(Path(__file__).resolve().parent.parent / "atspi_helper.py")
SYSTEM_PYTHON = "/usr/bin/python3"


def _helper(*args: str) -> dict:
    code, out = run([SYSTEM_PYTHON, HELPER, *args], timeout=25)
    try:
        data = json_line(out)
    except ValueError:
        raise ToolError(f"Accessibility helper failed: {out.strip()[-400:]}")
    if "error" in data:
        raise ToolError(
            f"{data['error']}. Try press_keys with the app's shortcuts, or look_at_screen."
        )
    return data


@tool(TOOLSET, example={"window": "dolphin", "filter": ""}, voice="ok")
def app_controls(
    window: Annotated[
        str, "App or title words; 'this' for the focused window"
    ] = "this",
    filter: Annotated[str, "Only controls whose name contains this"] = "",
) -> str:
    """List the buttons, menu items, tabs and text fields visible in an app window."""
    win = find_window(window)
    data = _helper("list", str(win["pid"]), filter)
    rows = data.get("controls") or []
    if not rows:
        return f"{win.get('class')} shows no named controls{' matching ' + repr(filter) if filter else ''}."
    more = (
        f"\n... {data['total'] - len(rows)} more"
        if data.get("total", 0) > len(rows)
        else ""
    )
    return f"Controls in {win.get('class')}:\n" + "\n".join(rows) + more


@tool(TOOLSET, example={"window": "qobuz", "control": "Play"})
def press_control(
    window: Annotated[str, "App or title words; 'this' for the focused window"],
    control: Annotated[
        str, "Name of the button, menu item, tab or link, as app_controls shows it"
    ],
) -> str:
    """Press (click) a named button, menu item, tab or link in an app window."""
    win = find_window(window)
    return _helper("press", str(win["pid"]), control)["ok"]


@tool(TOOLSET, example={"window": "this", "field": "Search", "text": "lofi"})
def fill_field(
    window: Annotated[str, "App or title words; 'this' for the focused window"],
    field: Annotated[str, "Name of the text field (empty for the first one)"],
    text: Annotated[str, "Text to put in it"],
) -> str:
    """Put text into a named text field in an app window."""
    win = find_window(window)
    return _helper("text", str(win["pid"]), field, text)["ok"]


@tool(TOOLSET, example={"window": "this"}, voice="ok")
def read_window_text(
    window: Annotated[
        str, "App or title words; 'this' for the focused window"
    ] = "this",
) -> str:
    """Read the visible text of an app window through accessibility (no screenshot needed)."""
    win = find_window(window)
    text = _helper("read", str(win["pid"])).get("text", "")
    return text or f"{win.get('class')} exposes no readable text. Try read_screen."
