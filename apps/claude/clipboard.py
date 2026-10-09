"""Images through the desktop clipboard, for pasting into and copying out of
the Claude panel.

WHY
    The panel runs inside WebKitGTK, whose paste event does not always hand a
    copied screenshot to the page as a file. The backend runs in the same
    Wayland session, so it reads and writes the clipboard itself with
    wl-paste and wl-copy (the wl-clipboard package). FORGE_WL_PASTE and
    FORGE_WL_COPY name other binaries, which is how the tests stand in for the
    real clipboard.
"""

from __future__ import annotations

import os
import subprocess

# Preferred first: PNG keeps a screenshot exact.
IMAGE_TYPES = ("image/png", "image/jpeg", "image/webp", "image/gif")
EXTENSIONS = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
    "image/gif": ".gif",
}
TIMEOUT = 5


def _tool(name: str) -> str:
    return os.environ.get("FORGE_" + name.upper().replace("-", "_"), name)


def read_image() -> tuple[bytes, str] | None:
    """(bytes, media type) of the image on the clipboard, or None when there
    is none or the clipboard cannot be read."""
    paste = _tool("wl-paste")
    try:
        listed = subprocess.run(
            [paste, "--list-types"], capture_output=True, timeout=TIMEOUT
        )
        offered = listed.stdout.decode(errors="replace").split()
        media = next((t for t in IMAGE_TYPES if t in offered), None)
        if listed.returncode != 0 or media is None:
            return None
        got = subprocess.run(
            [paste, "--no-newline", "--type", media],
            capture_output=True,
            timeout=TIMEOUT,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if got.returncode != 0 or not got.stdout:
        return None
    return got.stdout, media


def write_image(data: bytes, media: str) -> None:
    """Put an image on the clipboard. wl-copy keeps serving it after it
    returns, as it does from a terminal."""
    if media not in IMAGE_TYPES or not data:
        raise ValueError("Only an image can be copied")
    try:
        done = subprocess.run(
            [_tool("wl-copy"), "--type", media],
            input=data,
            capture_output=True,
            timeout=TIMEOUT,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        raise OSError(f"Could not reach the clipboard: {e}") from e
    if done.returncode != 0:
        raise OSError(done.stderr.decode(errors="replace").strip() or "wl-copy failed")
