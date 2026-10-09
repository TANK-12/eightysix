"""Seeing the screen, and finding what is behind it.

Three ways to see, cheapest first: `read_screen` (OCR of the focused window,
no model), `look_at_screen` (screenshot to the vision model), and
`whats_on_screen`, which works out which file or web page the focused window
is showing so the whole thing can be read, not just the visible part. That
last one is what makes "explain question 3 of this worksheet" work when
question 3 is off screen.
"""

from __future__ import annotations

import base64
import re
import tempfile
from pathlib import Path
from typing import Annotated
from urllib.parse import unquote

from ..desktop import current
from ..registry import ToolError, tool
from ..sysutil import run
from . import windows

TOOLSET = "screen"
TOOLSET_SUMMARY = "see the screen (OCR or vision), and find the file or web page behind the focused window to read it whole"

TOOLSET_KEYWORDS = (
    "screen",
    "see",
    "look",
    "looking at",
    "on my screen",
    "showing",
    "visible",
    "screenshot",
    "error on",
    "what's on",
    "read this",
    "explain this",
)
# (what a person says, tool, arguments): few-shot lines for the prompt
TOOLSET_EXAMPLES = [
    ("read me the first page of the pdf on my screen", "whats_on_screen", {}),
    ("what am I looking at", "whats_on_screen", {}),
    (
        "what does the error on my screen say",
        "look_at_screen",
        {"question": "What does the error message say?"},
    ),
]

DOC_VIEWERS = (
    "okular",
    "evince",
    "papers",
    "zathura",
    "atril",
    "xreader",
    "mupdf",
    "sioyek",
    "libreoffice",
    "foliate",
)
RECENT = Path.home() / ".local/share/recently-used.xbel"


def _grab(window: str = "this", scale: int = 1280) -> Path:
    """PNG of one window (or the whole screen with window='screen')."""
    shot = Path(tempfile.mkstemp(suffix=".png", prefix="acchan-shot-")[1])
    win = None if window == "screen" else windows.find_window(window)
    current().screenshot(shot, win)
    if scale:
        small = shot.with_suffix(".s.png")
        code, _ = run(
            [
                "ffmpeg",
                "-y",
                "-loglevel",
                "error",
                "-i",
                str(shot),
                "-vf",
                f"scale='min({scale},iw)':-2",
                str(small),
            ],
            timeout=30,
        )
        if code == 0 and small.exists():
            shot.unlink()
            return small
    return shot


@tool(TOOLSET, example={"window": "this"}, voice="ok")
def read_screen(
    window: Annotated[
        str, "Window to read ('this' = focused, 'screen' = everything)"
    ] = "this",
) -> str:
    """Read the text visible in a window by OCR. Fast, no vision model."""
    shot = _grab(window, scale=0)
    code, out = run(["tesseract", str(shot), "-", "--psm", "3"], timeout=60)
    shot.unlink(missing_ok=True)
    text = re.sub(r"\n{3,}", "\n\n", out).strip()
    return text[:9000] or "No readable text on screen."


@tool(
    TOOLSET, example={"question": "what error is shown?", "window": "this"}, voice="ok"
)
def look_at_screen(
    question: Annotated[
        str, "What to find out from the screen"
    ] = "Describe what is on screen.",
    window: Annotated[
        str, "Window to look at ('this' = focused, 'screen' = everything)"
    ] = "this",
) -> str:
    """Take a screenshot and have the vision model answer a question about it."""
    from ..llm import describe_image

    shot = _grab(window)
    data = base64.b64encode(shot.read_bytes()).decode()
    shot.unlink(missing_ok=True)
    return describe_image(data, question)


@tool(TOOLSET, example={"path": "~/Pictures/shot.png"}, voice="ok")
def take_screenshot(
    path: Annotated[str, "Where to save the PNG"] = "~/Pictures/Screenshots/acchan.png",
    window: Annotated[str, "'screen' for everything or a window name"] = "screen",
) -> str:
    """Save a screenshot to a file."""
    from ..sysutil import path as to_path

    shot = _grab(window, scale=0)
    target = to_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    shot.replace(target)
    return f"Saved {target}."


def _recent_file(title: str) -> Path | None:
    """The recently opened file whose name appears in a window title."""
    if not RECENT.exists():
        return None
    xml = RECENT.read_text(encoding="utf-8", errors="replace")
    hrefs = re.findall(r'href="file://([^"]+)"', xml)
    lowered = title.lower()
    for href in reversed(hrefs):
        file = Path(unquote(href))
        if file.name.lower() in lowered or file.stem.lower() in lowered:
            if file.exists():
                return file
    return None


def _title_file(title: str) -> Path | None:
    for candidate in re.findall(r"(/[^\s:—–|]+\.\w{2,5})", title):
        if Path(candidate).exists():
            return Path(candidate)
    names = re.findall(
        r"([\w .,()'&-]+\.(?:pdf|docx?|odt|pptx?|epub|md|txt|py|js|html))", title, re.I
    )
    if names:
        found = _recent_file(names[0].strip())
        if found:
            return found
        code, out = run(
            ["fd", "-1", "-t", "f", "-F", names[0].strip(), str(Path.home())],
            timeout=20,
        )
        if out.strip():
            return Path(out.strip().splitlines()[0])
    return _recent_file(title)


@tool(TOOLSET, voice="ok")
def whats_on_screen() -> str:
    """Find out what the focused window shows and return its content: the document page or web page text, the file behind it, or the window's text. Use this first for "this", "my screen", "the pdf I have open"."""
    win = windows.active()
    if not win:
        raise ToolError("No window has focus.")
    cls = (win.get("class") or "").lower()
    title = win.get("title") or ""
    lines = [f"Focused window: {win.get('class')} — {title}"]
    if "firefox" in cls or "chrom" in cls or "browser" in cls:
        try:
            from .browser import current_tab_url, fetch

            tab_title, url = current_tab_url()
            lines.append(f"Web page: {tab_title}\nAddress: {url}")
            try:
                _t, text = fetch(url)
                lines.append(f"Page text (start):\n{text[:2500]}")
                lines.append(
                    "For the rest: read_web_page. For a question about the whole page: ask_document with the address."
                )
            except Exception as exc:
                lines.append(
                    f"(Could not fetch the page: {exc}; use look_at_screen to see it.)"
                )
        except ToolError as exc:
            lines.append(f"(Could not get the address: {exc})")
    elif any(v in cls for v in DOC_VIEWERS) or re.search(
        r"\.(pdf|docx?|odt|pptx?|epub)\b", title, re.I
    ):
        file = _title_file(title)
        if file:
            page_match = re.search(r"(?:page|p\.)\s*(\d+)", title, re.I)
            page = int(page_match.group(1)) if page_match else 1
            lines.append(
                f"Document file: {file}"
                + (f" (showing page {page})" if page_match else "")
            )
            from .docs import document_text

            _name, text = document_text(str(file))
            parts = re.split(r"(?=\[page \d+\])", text)
            shown = [
                p for p in parts if re.match(rf"\[page ({page}|{page + 1})\]", p)
            ] or parts[:2]
            lines.append("Text of the page(s) shown:\n" + "".join(shown)[:3500])
            lines.append(
                f"The whole document has {len(text)} characters: use ask_document or read_document with {file} for other parts."
            )
        else:
            lines.append(
                "Could not find the file behind this viewer. Visible text by OCR:"
            )
            lines.append(read_screen("this")[:3000])
    elif any(t in cls for t in ("kitty", "console", "terminal")):
        lines.append("A terminal. Visible text:")
        lines.append(read_screen("this")[-3000:])
    else:
        file = _title_file(title)
        if file:
            lines.append(f"File in this window: {file}")
        try:
            from .ui import read_window_text

            text = read_window_text("this")
        except ToolError:
            text = ""
        if len(text) < 80:
            text = read_screen("this")
        lines.append("Window text:\n" + text[:3000])
    return "\n".join(lines)
