"""Screen sight and scrolling for Nyarch Assistant.

Drop this file in ~/.var/app/moe.nyarchlinux.assistant/config/extensions/ and
the assistant gains two tools: one that looks at the screen, and one that
scrolls it.  Together they let it read a long document a screenful at a time
and talk you through it.

The real work happens on the host, in ~/Forge/nyarch/screenview.py, because the
assistant runs inside a Flatpak sandbox that cannot reach the screen-share
portal or the ydotool socket directly.  Calls hop out through
`flatpak-spawn --host`, which this Flatpak is permitted to use.
"""

import os
import subprocess
import time

from nyarchassistant.extensions import NewelleExtension
from nyarchassistant.tools import Tool, ToolResult
from nyarchassistant.utility.system import get_spawn_command

HELPER = os.path.expanduser("~/Forge/nyarch/screenview.py")
SHOT_DIR = os.path.expanduser("~/.cache/nyarch-screenview")
# Keep a few recent captures so the model can compare before/after a scroll,
# but never let them pile up on a machine that is short on disk.
KEEP_SHOTS = 6
TIMEOUT_SECONDS = 120

# The vision model's time is dominated by how many tokens the picture becomes,
# not by how big the model is. Measured on this machine, reading one screenful:
#   1280 px -> 956 image tokens -> 47 s
#   1024 px -> 612 image tokens -> 31 s   <- default: same answer, a third faster
#    800 px -> 386 image tokens -> 23 s
# 1024 still reads terminal text correctly; go wider only for genuinely small
# print, which is what high_detail is for.
NORMAL_WIDTH = 1024
DETAIL_WIDTH = 1280

TEACHING_PROMPT = """\
## Looking at the screen

You can see the user's screen and scroll it.

- `see_screen` takes a fresh picture of the screen and puts it in your context.
  Call it whenever the user refers to what is on screen, what they are looking
  at, or asks you to read, check or explain something they have open.
- `scroll_screen` scrolls the window under the mouse pointer and, unless told
  otherwise, takes a new picture afterwards so you can carry on reading.

When the user asks you to read a document to them or teach them something they
have open:

1. Call `see_screen` and actually read what is there.
2. Explain that screenful in your own words, in plain language. Do not just
   read the text back verbatim unless they asked you to read it word for word.
3. If text-to-speech is on, your reply is spoken aloud, so write it to be
   heard rather than skimmed: short sentences, no markdown tables, no code
   blocks unless they matter.
4. Call `scroll_screen` to move down, then repeat from step 1.
5. Stop at the end of the document, or when the user interrupts, and offer to
   go back over anything.

Scroll in small steps (3 to 5 notches) so nothing is skipped between pictures.
"""


class ScreenViewExtension(NewelleExtension):
    name = "Screen View"
    id = "screenview"

    def get_additional_prompts(self) -> list:
        return [
            {
                "key": "screenview",
                "setting_name": "screenview",
                "title": "Screen Reading",
                "description": "Teach the model how to read the screen aloud",
                "editable": True,
                "show_in_settings": True,
                "default": True,
                "text": TEACHING_PROMPT,
            }
        ]

    def _next_shot_path(self) -> str:
        os.makedirs(SHOT_DIR, exist_ok=True)
        shots = sorted(
            (f for f in os.listdir(SHOT_DIR) if f.endswith(".png")),
            key=lambda f: os.path.getmtime(os.path.join(SHOT_DIR, f)),
        )
        for stale in shots[: max(0, len(shots) - (KEEP_SHOTS - 1))]:
            try:
                os.remove(os.path.join(SHOT_DIR, stale))
            except OSError:
                pass
        return os.path.join(SHOT_DIR, f"screen-{int(time.time() * 1000)}.png")

    def _run_helper(self, arguments: list[str]) -> tuple[bool, str]:
        try:
            finished = subprocess.run(
                get_spawn_command() + ["python3", HELPER] + arguments,
                capture_output=True,
                text=True,
                timeout=TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired:
            return False, "The screen helper timed out."
        except Exception as error:
            return False, f"Could not run the screen helper: {error}"
        if finished.returncode != 0:
            return False, (finished.stderr or finished.stdout or "").strip()
        return True, (finished.stdout or "").strip()

    def _capture(self, width: int = NORMAL_WIDTH) -> tuple[bool, str]:
        path = self._next_shot_path()
        ok, message = self._run_helper(["shot", "--out", path, "--width", str(width)])
        if not ok:
            return False, message
        if not os.path.isfile(path):
            return False, "The screen helper reported success but wrote no image."
        return True, path

    def see_screen(self, detail: str = "", high_detail: bool = False) -> ToolResult:
        """Capture the screen and hand the picture to the model."""
        result = ToolResult()
        ok, payload = self._capture(DETAIL_WIDTH if high_detail else NORMAL_WIDTH)
        if not ok:
            result.set_output(f"Could not see the screen: {payload}")
            return result
        context_message = f"```image\n{payload}\n```"
        result.set_context_messages([context_message])
        result.set_display_text("Looked at the screen.")
        result.set_output(context_message)
        return result

    def scroll_screen(
        self,
        direction: str = "down",
        amount: int = 4,
        then_look: bool = True,
    ) -> ToolResult:
        """Scroll the window under the pointer, then look again by default."""
        result = ToolResult()
        direction = "up" if str(direction).lower().startswith("u") else "down"
        try:
            amount = max(1, min(30, int(amount)))
        except (TypeError, ValueError):
            amount = 4

        ok, message = self._run_helper(
            ["scroll", "--amount", str(amount), "--direction", direction]
        )
        if not ok:
            result.set_output(f"Could not scroll: {message}")
            return result

        if not then_look:
            result.set_display_text(message)
            result.set_output(message)
            return result

        # Give the window a moment to repaint before photographing it.
        time.sleep(0.4)
        ok, payload = self._capture()
        if not ok:
            result.set_output(f"{message} But the new picture failed: {payload}")
            return result
        context_message = f"```image\n{payload}\n```"
        result.set_context_messages([context_message])
        result.set_display_text(f"Scrolled {direction} and looked again.")
        result.set_output(f"{message}\n{context_message}")
        return result

    def get_tools(self) -> list:
        return [
            Tool(
                name="see_screen",
                description=(
                    "Take a picture of the user's screen right now and read it. "
                    "Use this whenever the user refers to something they are "
                    "looking at, or asks you to read or explain what is open."
                ),
                func=self.see_screen,
                schema={
                    "type": "object",
                    "properties": {
                        "detail": {
                            "type": "string",
                            "description": (
                                "Optional note about what to pay attention to."
                            ),
                        },
                        "high_detail": {
                            "type": "boolean",
                            "default": False,
                            "description": (
                                "Capture at higher resolution. Roughly 50% "
                                "slower; use only when the text is too small "
                                "to read at the normal size."
                            ),
                        },
                    },
                },
                title="See Screen",
                default_on=True,
                tools_group="Screen",
                icon_name="video-display-symbolic",
            ),
            Tool(
                name="scroll_screen",
                description=(
                    "Scroll the window under the mouse pointer and take a new "
                    "picture of the screen, so you can keep reading a long "
                    "document one screenful at a time."
                ),
                func=self.scroll_screen,
                schema={
                    "type": "object",
                    "properties": {
                        "direction": {
                            "type": "string",
                            "enum": ["down", "up"],
                            "default": "down",
                        },
                        "amount": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 30,
                            "default": 4,
                            "description": "Wheel notches. 3-5 keeps lines from being skipped.",
                        },
                        "then_look": {
                            "type": "boolean",
                            "default": True,
                            "description": "Take a picture after scrolling.",
                        },
                    },
                },
                title="Scroll Screen",
                default_on=True,
                tools_group="Screen",
                icon_name="go-down-symbolic",
            ),
        ]
