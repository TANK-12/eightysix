"""One interface over the two desktops this laptop runs: Hyprland and GNOME.

Emerson switches between them, so every window, keyboard and screenshot
action goes through `current()`, which picks the backend from the session:

    Hyprland  hyprctl for windows and workspaces, wtype for keys, grim for shots
    GNOME     AT-SPI for the window list, ydotool (its daemon already runs as a
              user service) for keys and typing, Nyarch's screenview.py (the
              screen-share portal with a remembered grant) for shots. GNOME 50
              blocks Shell.Eval, gnome-screenshot and wlr protocols, so focusing
              a window cycles the "cycle-windows" shortcut until AT-SPI reports
              the target active, and close/fullscreen/workspace moves press the
              shortcuts GNOME itself has configured (read from gsettings).

A window is a dict with at least class, title, pid, address, active.
"""

from __future__ import annotations

import ast
import json
import os
import subprocess
import time
from pathlib import Path

from .registry import ToolError
from .sysutil import json_line, run

HELPER = str(Path(__file__).resolve().parent / "atspi_helper.py")
SCREENVIEW = Path.home() / "Forge" / "nyarch" / "screenview.py"
SYSTEM_PYTHON = "/usr/bin/python3"

# Linux input event codes, for ydotool.
KEYCODES = {
    "esc": 1,
    "escape": 1,
    "minus": 12,
    "equal": 13,
    "backspace": 14,
    "tab": 15,
    "enter": 28,
    "return": 28,
    "ctrl": 29,
    "control": 29,
    "shift": 42,
    "alt": 56,
    "space": 57,
    "capslock": 58,
    "super": 125,
    "logo": 125,
    "win": 125,
    "meta": 125,
    "home": 102,
    "up": 103,
    "pageup": 104,
    "prior": 104,
    "page_up": 104,
    "left": 105,
    "right": 106,
    "end": 107,
    "down": 108,
    "pagedown": 109,
    "next": 109,
    "page_down": 109,
    "insert": 110,
    "delete": 111,
    "del": 111,
    "comma": 51,
    "period": 52,
    "dot": 52,
    "slash": 53,
    "semicolon": 39,
    "apostrophe": 40,
    "grave": 41,
    "backslash": 43,
    "leftbrace": 26,
    "rightbrace": 27,
    "plus": 13,
    "f11": 87,
    "f12": 88,
    "kp_next": 109,
    "kp_prior": 104,
}
for _i, _c in enumerate("1234567890"):
    KEYCODES[_c] = 2 + _i
for _row, _start in (("qwertyuiop", 16), ("asdfghjkl", 30), ("zxcvbnm", 44)):
    for _i, _c in enumerate(_row):
        KEYCODES[_c] = _start + _i
for _i in range(1, 11):
    KEYCODES[f"f{_i}"] = 58 + _i
MODIFIER_WORDS = {"ctrl", "control", "shift", "alt", "super", "logo", "win", "meta"}


def split_combo(combo: str) -> tuple[list[str], str]:
    """'ctrl+shift+t' -> (['ctrl', 'shift'], 't'). Accepts GTK style too:
    '<Super><Shift>Page_Down'."""
    text = combo.strip()
    if text.startswith("<"):
        mods = [m.lower() for m in __import__("re").findall(r"<(\w+)>", text)]
        key = text[text.rfind(">") + 1 :]
        return [("ctrl" if m == "primary" else m) for m in mods], key
    parts = [p for p in text.replace(" ", "").split("+") if p]
    if not parts:
        raise ToolError("No keys given.")
    return [p.lower() for p in parts[:-1]], parts[-1]


class Desktop:
    name = "unknown"

    def windows(self) -> list[dict]:
        raise NotImplementedError

    def active(self) -> dict:
        for win in self.windows():
            if win.get("active"):
                return win
        return {}

    def focus(self, win: dict) -> None:
        raise NotImplementedError

    def close(self, win: dict) -> None:
        raise NotImplementedError

    def fullscreen(self, win: dict) -> None:
        raise NotImplementedError

    def move_to_workspace(self, win: dict, workspace: str) -> None:
        raise NotImplementedError

    def switch_workspace(self, workspace: str) -> None:
        raise NotImplementedError

    def keys(self, combos: list[str]) -> None:
        raise NotImplementedError

    def type_text(self, text: str) -> None:
        raise NotImplementedError

    def screenshot(self, out: Path, win: dict | None = None) -> Path:
        raise NotImplementedError

    def exec(self, command: str) -> None:
        subprocess.Popen(
            ["/bin/bash", "-c", command],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )


class Hyprland(Desktop):
    name = "hyprland"
    WTYPE_NAMES = {
        "ctrl": "ctrl",
        "control": "ctrl",
        "shift": "shift",
        "alt": "alt",
        "super": "logo",
        "win": "logo",
        "meta": "logo",
        "logo": "logo",
        "enter": "Return",
        "return": "Return",
        "esc": "Escape",
        "escape": "Escape",
        "tab": "Tab",
        "space": "space",
        "backspace": "BackSpace",
        "delete": "Delete",
        "del": "Delete",
        "up": "Up",
        "down": "Down",
        "left": "Left",
        "right": "Right",
        "home": "Home",
        "end": "End",
        "pageup": "Prior",
        "pagedown": "Next",
        "prior": "Prior",
        "next": "Next",
        "plus": "plus",
        "minus": "minus",
    }

    def _dispatch(self, *args: str) -> None:
        code, out = run(["hyprctl", "dispatch", *args], timeout=5)
        if "ok" not in out:
            raise ToolError(f"Hyprland refused {' '.join(args)}: {out.strip()}")

    def windows(self) -> list[dict]:
        _code, out = run(["hyprctl", "clients", "-j"], timeout=5)
        _c2, act = run(["hyprctl", "activewindow", "-j"], timeout=5)
        try:
            items = json.loads(out)
            focused = (json.loads(act) or {}).get("address")
        except ValueError:
            raise ToolError("Could not read windows from Hyprland.")
        wins = []
        for c in items:
            if not c.get("mapped", True) or c.get("class") is None:
                continue
            c["active"] = c.get("address") == focused
            c["workspace_name"] = (c.get("workspace") or {}).get("name", "")
            wins.append(c)
        return wins

    def focus(self, win: dict) -> None:
        self._dispatch("focuswindow", f"address:{win['address']}")
        time.sleep(0.15)

    def close(self, win: dict) -> None:
        self._dispatch("closewindow", f"address:{win['address']}")

    def fullscreen(self, win: dict) -> None:
        self.focus(win)
        self._dispatch("fullscreen", "0")

    def move_to_workspace(self, win: dict, workspace: str) -> None:
        self._dispatch("movetoworkspacesilent", f"{workspace},address:{win['address']}")

    def switch_workspace(self, workspace: str) -> None:
        self._dispatch("workspace", str(workspace))

    def keys(self, combos: list[str]) -> None:
        for combo in combos:
            mods, key = split_combo(combo)
            args: list[str] = []
            for mod in mods:
                args += ["-M", self.WTYPE_NAMES.get(mod, mod)]
            key = self.WTYPE_NAMES.get(
                key.lower(), key if len(key) > 1 else key.lower()
            )
            if key.lower().startswith("f") and key[1:].isdigit():
                key = key.upper()
            args += ["-k", key]
            for mod in reversed(mods):
                args += ["-m", self.WTYPE_NAMES.get(mod, mod)]
            run(["wtype", *args], timeout=5, check=True)
            time.sleep(0.05)

    def type_text(self, text: str) -> None:
        run(["wtype", "-d", "4", "--", text], timeout=60, check=True)

    def screenshot(self, out: Path, win: dict | None = None) -> Path:
        cmd = ["grim", "-l", "1"]
        if win and win.get("at") and win.get("size"):
            x, y = win["at"]
            w, h = win["size"]
            cmd += ["-g", f"{x},{y} {w}x{h}"]
        run([*cmd, str(out)], timeout=15, check=True)
        return out

    def exec(self, command: str) -> None:
        code, out = run(["hyprctl", "dispatch", "exec", command], timeout=10)
        if code != 0 or "ok" not in out:
            super().exec(command)


class Gnome(Desktop):
    name = "gnome"

    def _binding(self, key: str, fallback: str) -> str:
        code, out = run(
            ["gsettings", "get", "org.gnome.desktop.wm.keybindings", key], timeout=5
        )
        try:
            values = ast.literal_eval(out.strip().replace("@as ", ""))
        except (ValueError, SyntaxError):
            values = []
        return values[0] if values else fallback

    def windows(self) -> list[dict]:
        code, out = run([SYSTEM_PYTHON, HELPER, "windows"], timeout=20)
        try:
            data = json_line(out)
        except ValueError:
            raise ToolError(f"Could not list windows: {out.strip()[-300:]}")
        return data.get("windows", [])

    def _is_active(self, win: dict) -> bool:
        now = self.active()
        return (
            bool(now)
            and now.get("pid") == win.get("pid")
            and now.get("title") == win.get("title")
        )

    def focus(self, win: dict) -> None:
        if self._is_active(win):
            return
        cycle = self._binding("cycle-windows", "<Alt>Escape")
        for _ in range(max(2, len(self.windows()) + 1)):
            self.keys([cycle])
            time.sleep(0.25)
            if self._is_active(win):
                return
        raise ToolError(
            f"Could not bring {win.get('class')} to the front on GNOME. It may be on another workspace or minimised."
        )

    def close(self, win: dict) -> None:
        self.focus(win)
        self.keys([self._binding("close", "<Alt>F4")])

    def fullscreen(self, win: dict) -> None:
        self.focus(win)
        self.keys([self._binding("toggle-fullscreen", "F11")])

    def move_to_workspace(self, win: dict, workspace: str) -> None:
        self.focus(win)
        self.keys([self._binding("move-to-workspace-1", "<Super><Shift>Home")])
        steps = max(0, int(workspace) - 1) if str(workspace).isdigit() else 0
        self.keys(
            [self._binding("move-to-workspace-right", "<Super><Shift>Page_Down")]
            * steps
        )

    def switch_workspace(self, workspace: str) -> None:
        self.keys([self._binding("switch-to-workspace-1", "<Super>Home")])
        steps = max(0, int(workspace) - 1) if str(workspace).isdigit() else 0
        self.keys(
            [self._binding("switch-to-workspace-right", "<Super>Page_Down")] * steps
        )

    def _code(self, name: str) -> int:
        code = KEYCODES.get(name.lower())
        if code is None:
            raise ToolError(f"Unknown key {name!r}.")
        return code

    def keys(self, combos: list[str]) -> None:
        env = {
            **os.environ,
            "YDOTOOL_SOCKET": os.environ.get(
                "YDOTOOL_SOCKET", f"/run/user/{os.getuid()}/.ydotool_socket"
            ),
        }
        for combo in combos:
            mods, key = split_combo(combo)
            codes = [self._code(m) for m in mods] + [self._code(key)]
            seq = [f"{c}:1" for c in codes] + [f"{c}:0" for c in reversed(codes)]
            done = subprocess.run(
                ["ydotool", "key", *seq],
                env=env,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if done.returncode != 0:
                raise ToolError(f"ydotool failed: {done.stderr.strip()[-200:]}")
            time.sleep(0.06)

    def type_text(self, text: str) -> None:
        env = {
            **os.environ,
            "YDOTOOL_SOCKET": os.environ.get(
                "YDOTOOL_SOCKET", f"/run/user/{os.getuid()}/.ydotool_socket"
            ),
        }
        done = subprocess.run(
            ["ydotool", "type", "-d", "6", "--", text],
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if done.returncode != 0:
            raise ToolError(f"ydotool failed: {done.stderr.strip()[-200:]}")

    def screenshot(self, out: Path, win: dict | None = None) -> Path:
        if not SCREENVIEW.exists():
            raise ToolError("Screenshots on GNOME need ~/Forge/nyarch/screenview.py.")
        code, text = run(
            [
                SYSTEM_PYTHON,
                str(SCREENVIEW),
                "shot",
                "--out",
                str(out),
                "--width",
                "1600",
            ],
            timeout=45,
        )
        if not out.exists():
            raise ToolError(f"Screenshot failed: {text.strip()[-300:]}")
        return out


class Headless(Desktop):
    name = "none"

    def windows(self) -> list[dict]:
        raise ToolError("No desktop session is reachable from here.")

    def keys(self, combos: list[str]) -> None:
        raise ToolError("No desktop session is reachable from here.")

    type_text = keys  # type: ignore[assignment]


def _hyprland_signature() -> str:
    sig = os.environ.get("HYPRLAND_INSTANCE_SIGNATURE", "")
    if sig:
        return sig
    base = Path(os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")) / "hypr"
    if base.is_dir():
        live = sorted(base.iterdir(), key=lambda p: p.stat().st_mtime)
        if live:
            os.environ["HYPRLAND_INSTANCE_SIGNATURE"] = live[-1].name
            return live[-1].name
    return ""


# What a launched app needs to reach the screen. acchan.service starts at
# login, before GNOME hands these to the user manager, so the backend itself
# has none of them: every app it launched failed to open, except the terminal
# (gnome-terminal asks a D-Bus service, which has them, to make its window).
SESSION_KEYS = (
    "WAYLAND_DISPLAY",
    "DISPLAY",
    "XAUTHORITY",
    "XDG_CURRENT_DESKTOP",
    "XDG_SESSION_TYPE",
    "XDG_SESSION_DESKTOP",
    "DESKTOP_SESSION",
    "XDG_DATA_DIRS",
)
_ADOPTED: set[str] = set()


def _manager_env() -> dict[str, str]:
    """The session variables the systemd user manager holds right now."""
    try:
        code, out = run(["systemctl", "--user", "show-environment"], timeout=5)
    except ToolError:
        return {}
    if code != 0:
        return {}
    pairs = (line.partition("=") for line in out.splitlines())
    return {key: value for key, sep, value in pairs if sep and key in SESSION_KEYS}


def adopt_session_env() -> None:
    """Fill in the display variables this process lacks from the live session.
    A variable this process started with is kept; one adopted earlier is
    refreshed, so a new login (GNOME to Hyprland) is followed."""
    for key, value in _manager_env().items():
        if key in os.environ and key not in _ADOPTED:
            continue
        os.environ[key] = value
        _ADOPTED.add(key)


def detect() -> Desktop:
    adopt_session_env()
    if _hyprland_signature():
        return Hyprland()
    session = (
        os.environ.get("XDG_CURRENT_DESKTOP", "")
        + os.environ.get("DESKTOP_SESSION", "")
    ).lower()
    if (
        "gnome" in session
        or subprocess.run(
            ["pgrep", "-x", "gnome-shell"], capture_output=True
        ).returncode
        == 0
    ):
        return Gnome()
    return Headless()


_CACHED: tuple[float, Desktop] | None = None


def current() -> Desktop:
    """The running desktop, re-checked every 30 s (the user may log out of
    one and into the other while the backend keeps running)."""
    global _CACHED
    now = time.monotonic()
    if _CACHED is None or now - _CACHED[0] > 30:
        _CACHED = (now, detect())
    return _CACHED[1]
