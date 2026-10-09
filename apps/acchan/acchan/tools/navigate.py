"""Getting around inside apps: scrolling, and moving back, forward, finding
and zooming in Firefox or any window, with the keys a person would press.

Each action is a name mapped to key combos (ACTIONS), so a new one is a new
line, not a new tool. Nothing here needs the app to publish anything.
"""

from __future__ import annotations

from typing import Annotated

from ..registry import ToolError, tool
from . import windows

TOOLSET = "navigate"
TOOLSET_SUMMARY = "scroll, go back/forward, reload, find on the page, zoom, next/previous tab, in Firefox or any window"
TOOLSET_KEYWORDS = (
    "scroll",
    "go back",
    "back",
    "forward",
    "reload",
    "refresh",
    "zoom",
    "find on",
    "find in",
    "next tab",
    "previous tab",
    "top of",
    "bottom of",
    "page down",
    "page up",
    "navigate",
)
TOOLSET_EXAMPLES = [
    ("go back a page in firefox", "navigate", {"action": "back", "window": "firefox"}),
    ("scroll down", "scroll", {"direction": "down", "times": 3}),
]

# action -> key combos, the same shortcuts in Firefox, Chrome, Dolphin, Papers...
ACTIONS = {
    "back": ["alt+left"],
    "forward": ["alt+right"],
    "reload": ["f5"],
    "top": ["ctrl+home"],
    "bottom": ["ctrl+end"],
    "zoom in": ["ctrl+plus"],
    "zoom out": ["ctrl+minus"],
    "zoom reset": ["ctrl+0"],
    "next tab": ["ctrl+tab"],
    "previous tab": ["ctrl+shift+tab"],
    "home": ["alt+home"],
    "address bar": ["ctrl+l"],
}
SCROLL = {
    "down": "pagedown",
    "up": "pageup",
    "left": "left",
    "right": "right",
}


def _focus(window: str) -> None:
    if window.strip().lower() not in windows.THIS:
        windows.focus(windows.find_window(window))


@tool(TOOLSET, example={"action": "back", "window": "firefox"}, voice="ok")
def navigate(
    action: Annotated[
        str,
        "back, forward, reload, top, bottom, zoom in, zoom out, zoom reset, next tab, previous tab, home or address bar",
    ],
    window: Annotated[str, "Window to act in; empty for the focused one"] = "",
) -> str:
    """Move around in a window the way a person would: back, forward, reload, top/bottom of the page, zoom, next/previous tab."""
    key = action.strip().lower().replace("_", " ")
    key = {"refresh": "reload", "go back": "back", "go forward": "forward"}.get(
        key, key
    )
    if key not in ACTIONS:
        raise ToolError(f"Unknown action {action!r}. Use one of: {', '.join(ACTIONS)}.")
    _focus(window)
    windows.send_keys(ACTIONS[key])
    return f"Did {key}."


@tool(TOOLSET, example={"direction": "down", "times": 3}, voice="ok")
def scroll(
    direction: Annotated[str, "down, up, left or right"],
    times: Annotated[int, "How many screens (pages) to scroll, 1-20"] = 1,
    window: Annotated[str, "Window to scroll; empty for the focused one"] = "",
) -> str:
    """Scroll a window by whole screens."""
    key = SCROLL.get(direction.strip().lower())
    if key is None:
        raise ToolError("direction must be down, up, left or right.")
    _focus(window)
    windows.send_keys([key] * max(1, min(int(times), 20)))
    return f"Scrolled {direction} {times}x."


@tool(TOOLSET, example={"text": "exam date", "window": "firefox"}, voice="ok")
def find_on_page(
    text: Annotated[str, "Words to find"],
    window: Annotated[str, "Window to search in; empty for the focused one"] = "",
) -> str:
    """Jump to words on the page or document shown in a window (its Find bar)."""
    _focus(window)
    windows.send_keys(["ctrl+f"])
    windows.type_into(text)
    windows.send_keys(["enter"])
    return f"Searched the page for {text!r}."
