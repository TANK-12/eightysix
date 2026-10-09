"""Small system things: clipboard, notifications, battery, time, reminders."""

from __future__ import annotations

import ast
import datetime
import math
import operator
import re
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Annotated

from ..registry import ToolError, tool
from ..sysutil import run, spawn

TOOLSET = "system"
TOOLSET_SUMMARY = (
    "clipboard, notifications, reminders, battery, date and time, system status"
)

TOOLSET_KEYWORDS = (
    "calculate",
    "times",
    "plus",
    "minus",
    "divided",
    "percent",
    "sqrt",
    "square root",
    "multiply",
    "sum of",
    "clipboard",
    "copy",
    "paste",
    "notify",
    "notification",
    "remind",
    "reminder",
    "timer",
    "battery",
    "memory",
    "ram",
    "time",
    "date",
    "status",
    "what time",
    "brightness",
    "brighter",
    "dimmer",
    "screen brightness",
    "lock",
    "lock the screen",
    "wifi",
    "wi-fi",
    "internet",
    "bluetooth",
    "weather",
    "temperature",
    "rain",
    "forecast",
)
# (what a person says, tool, arguments): few-shot lines for the prompt
TOOLSET_EXAMPLES = [
    (
        "remind me in 10 minutes to stretch",
        "remind_me",
        {"minutes": 10, "message": "stretch"},
    ),
    ("copy that to my clipboard", "set_clipboard", {"text": "..."}),
    ("what time is it", "what_time", {}),
    ("make the screen brighter", "set_brightness", {"percent": "+10"}),
    ("what's the weather like", "weather", {"place": ""}),
]


_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}
_FUNCS = {
    name: getattr(math, name)
    for name in (
        "sqrt",
        "sin",
        "cos",
        "tan",
        "asin",
        "acos",
        "atan",
        "log",
        "log10",
        "log2",
        "exp",
        "floor",
        "ceil",
        "factorial",
        "radians",
        "degrees",
    )
}
_FUNCS.update(abs=abs, round=round, min=min, max=max)
_CONSTS = {"pi": math.pi, "e": math.e, "tau": math.tau}


def _eval(node: ast.AST) -> float:
    if isinstance(node, ast.Expression):
        return _eval(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.Name) and node.id in _CONSTS:
        return _CONSTS[node.id]
    if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
        left, right = _eval(node.left), _eval(node.right)
        if isinstance(node.op, ast.Pow) and abs(right) > 1000:
            raise ToolError("Exponent too large.")
        return _OPS[type(node.op)](left, right)
    if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_eval(node.operand))
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in _FUNCS
    ):
        return _FUNCS[node.func.id](*[_eval(a) for a in node.args])
    raise ToolError(
        "Only numbers, + - * / // % **, brackets and maths functions like sqrt, sin, log are allowed."
    )


@tool(TOOLSET, example={"expression": "17 * 23"}, voice="ok")
def calculate(
    expression: Annotated[
        str, "A maths expression, like 17*23 or sqrt(2)/3 or 15% of 80 as 0.15*80"
    ],
) -> str:
    """Work out arithmetic exactly. Always use this for any calculation instead of doing it in your head."""
    text = (
        expression.replace("^", "**")
        .replace("×", "*")
        .replace("÷", "/")
        .replace(",", "")
    )
    text = re.sub(r"(\d+(?:\.\d+)?)\s*%\s*of\s*", r"(\1/100)*", text)
    try:
        tree = ast.parse(text, mode="eval")
    except SyntaxError:
        raise ToolError(
            f"{expression!r} is not a maths expression. Write it like 17*23."
        )
    value = _eval(tree)
    if isinstance(value, float) and value.is_integer() and abs(value) < 1e15:
        value = int(value)
    return f"{expression} = {value}"


@tool(TOOLSET)
def get_clipboard() -> str:
    """Read the text currently in the clipboard."""
    code, out = run(["wl-paste", "--no-newline"], timeout=5)
    return out[:9000] if code == 0 and out else "The clipboard is empty."


@tool(TOOLSET, example={"text": "hello"})
def set_clipboard(text: Annotated[str, "Text to copy"]) -> str:
    """Copy text to the clipboard."""
    run(["wl-copy", "--", text], timeout=5, check=True)
    return "Copied to the clipboard."


@tool(TOOLSET, example={"message": "Tea is ready", "title": "Acchan"}, voice="ok")
def notify(
    message: Annotated[str, "What the notification says"],
    title: Annotated[str, "Notification title"] = "Acchan",
) -> str:
    """Show a desktop notification."""
    run(["notify-send", "-a", "Acchan", title, message], timeout=5, check=True)
    return "Notification shown."


@tool(TOOLSET, example={"minutes": 10, "message": "stretch"}, voice="ok")
def remind_me(
    minutes: Annotated[float, "Minutes from now"],
    message: Annotated[str, "What to remind about"],
) -> str:
    """Show a notification reminder after some minutes (lasts until the computer restarts)."""
    seconds = max(1, int(minutes * 60))
    spawn(
        [
            "systemd-run",
            "--user",
            f"--on-active={seconds}",
            "--timer-property=AccuracySec=1s",
            "notify-send",
            "-u",
            "critical",
            "-a",
            "Acchan",
            "Reminder",
            message,
        ]
    )
    at = (datetime.datetime.now() + datetime.timedelta(seconds=seconds)).strftime(
        "%H:%M"
    )
    return f"Reminder set for {at}."


@tool(TOOLSET, voice="ok")
def system_status() -> str:
    """Battery, memory, disk, CPU load and the current date and time."""
    lines = [datetime.datetime.now().strftime("Now: %A %d %B %Y, %H:%M")]
    for bat in Path("/sys/class/power_supply").glob("BAT*"):
        try:
            cap = (bat / "capacity").read_text().strip()
            status = (bat / "status").read_text().strip()
            lines.append(f"Battery: {cap}% ({status})")
        except OSError:
            pass
    info = dict(
        line.split(":", 1)
        for line in Path("/proc/meminfo").read_text().splitlines()
        if ":" in line
    )
    total = int(info["MemTotal"].split()[0]) / 1048576
    avail = int(info["MemAvailable"].split()[0]) / 1048576
    lines.append(f"Memory: {total - avail:.1f} of {total:.1f} GB used")
    code, out = run(["df", "-h", "--output=avail,pcent", str(Path.home())], timeout=5)
    parts = out.splitlines()[-1].split() if out else ["?", "?"]
    lines.append(f"Disk: {parts[0]} free ({parts[1]} used)")
    load = Path("/proc/loadavg").read_text().split()[:3]
    lines.append(f"CPU load: {' '.join(load)}")
    return "\n".join(lines)


@tool(
    TOOLSET,
    phrases=[
        "what time is it",
        "what is time",
        "tell me time",
        "time",
        "what day is it",
        "what is date",
        "what is date today",
    ],
    voice="ok",
)
def what_time() -> str:
    """The current time, day and date."""
    return datetime.datetime.now().strftime("It is %H:%M on %A %d %B %Y.")


@tool(
    TOOLSET,
    example={"percent": "60"},
    phrases=[
        "brightness {percent}",
        "set brightness to {percent}",
        "brightness to {percent}",
        "turn brightness to {percent}",
        ("brighter", {"percent": "+10"}),
        ("turn brightness up", {"percent": "+10"}),
        ("make screen brighter", {"percent": "+10"}),
        ("dimmer", {"percent": "-10"}),
        ("turn brightness down", {"percent": "-10"}),
        ("dim screen", {"percent": "-10"}),
    ],
    voice="ok",
)
def set_brightness(
    percent: Annotated[
        str, "Screen brightness: a level like 60, or a change like +10 or -10"
    ],
) -> str:
    """Set the screen brightness, or make it brighter (+10) or dimmer (-10)."""
    m = re.fullmatch(r"\s*([+-]?)\s*(\d{1,3})\s*%?\s*", str(percent))
    if not m:
        raise ToolError("Give a level like 60, or a change like +10 or -10.")
    sign, value = m.group(1), min(100, int(m.group(2)))
    arg = f"{value}%{sign}" if sign else f"{max(value, 5)}%"
    code, out = run(["brightnessctl", "-m", "set", arg], timeout=5)
    if code != 0:
        raise ToolError(f"brightnessctl failed: {out.strip()[:200]}")
    level = out.strip().split(",")[3] if out.count(",") >= 3 else arg
    return f"Brightness is now {level}."


@tool(TOOLSET, voice="ok")
def lock_screen() -> str:
    """Lock the screen."""
    code, out = run(["loginctl", "lock-session"], timeout=5)
    if code != 0:
        raise ToolError(f"Could not lock the screen: {out.strip()[:200]}")
    return "Screen locked."


@tool(TOOLSET, example={"turn": "status"}, voice="ok")
def wifi(turn: Annotated[str, "on, off, or status"] = "status") -> str:
    """Wi-Fi: turn it on or off, or say whether it is connected and to what."""
    turn = turn.strip().lower()
    if turn in ("on", "off"):
        code, out = run(["nmcli", "radio", "wifi", turn], timeout=10)
        if code != 0:
            raise ToolError(f"nmcli failed: {out.strip()[:200]}")
        return f"Wi-Fi turned {turn}."
    code, out = run(["nmcli", "-t", "-f", "ACTIVE,SSID,SIGNAL", "dev", "wifi"], 10)
    active = [line.split(":") for line in out.splitlines() if line.startswith("yes:")]
    if active:
        return f"Connected to {active[0][1]} (signal {active[0][2]}%)."
    _code, radio = run(["nmcli", "radio", "wifi"], timeout=5)
    return f"Not connected to Wi-Fi (radio {radio.strip() or 'unknown'})."


@tool(TOOLSET, example={"turn": "on"}, voice="ok")
def bluetooth(turn: Annotated[str, "on, off, or status"] = "status") -> str:
    """Bluetooth: turn it on or off, or list what is connected."""
    turn = turn.strip().lower()
    if turn in ("on", "off"):
        code, out = run(["bluetoothctl", "power", turn], timeout=10)
        if code != 0 or "Failed" in out:
            raise ToolError(f"bluetoothctl failed: {out.strip()[:200]}")
        return f"Bluetooth turned {turn}."
    _code, show = run(["bluetoothctl", "show"], timeout=5)
    powered = "on" if "Powered: yes" in show else "off"
    _code, out = run(["bluetoothctl", "devices", "Connected"], timeout=5)
    names = [line.split(" ", 2)[2] for line in out.splitlines() if line.count(" ") >= 2]
    connected = ", ".join(names) if names else "nothing"
    return f"Bluetooth is {powered}; connected: {connected}."


@tool(
    TOOLSET,
    example={"place": "Perth"},
    phrases=[
        "what is weather",
        "how is weather",
        "weather",
        "weather today",
        "what is weather like",
        "is it going to rain",
        "weather in {place}",
        "what is weather in {place}",
        "what is weather like in {place}",
        "how is weather in {place}",
    ],
    voice="ok",
)
def weather(
    place: Annotated[str, "Town or city; empty for where the computer is"] = "",
) -> str:
    """Current weather and today's forecast (from wttr.in)."""
    url = (
        "https://wttr.in/"
        + urllib.parse.quote(place.strip())
        + "?format=%l:+%C,+%t+(feels+%f),+wind+%w,+rain+%p;+today+%m"
    )
    request = urllib.request.Request(url, headers={"User-Agent": "curl/8"})
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            text = response.read().decode("utf-8", "replace").strip()
    except OSError as exc:
        raise ToolError(f"The weather service did not answer: {exc}") from exc
    if not text or "Unknown location" in text:
        raise ToolError(f"No weather found for {place!r}; try a nearby city.")
    return text
