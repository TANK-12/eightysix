"""Usage meters and accounts, read through ~/.claude/tools/usage.py.

That script is imported rather than copied, so its shared cache and its
back-off after HTTP 429 cover Relay too. On top of it Relay keeps its own
3-minute cache so the boss never asks more often than that. Accounts are the
ones usage.py knows: the default ~/.claude plus every Forge profile that has
a login.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
import time
from datetime import datetime
from pathlib import Path

USAGE_PY = Path(
    os.environ.get("RELAY_USAGE_PY") or Path.home() / ".claude" / "tools" / "usage.py"
)
CACHE_SECONDS = 180
_cache: dict = {"at": 0.0, "data": {}}
# A login whose token ran out reads HTTP 401 until a Claude Code process
# refreshes it (after the 2026-10-07 boot both meters read 401 and Relay
# launched nothing until a session ran on hey). `claude auth status` does not
# refresh; a one-word call does. At most once per REFRESH_GAP per account.
REFRESH_GAP = 1200
UNAUTHORISED = re.compile(r"HTTP Error 401|\b401\b.*Unauthori[sz]ed|Unauthori[sz]ed")
STALE_AFTER = 900
_refreshed: dict[str, float] = {}


def _usage():
    spec = importlib.util.spec_from_file_location("claude_usage", USAGE_PY)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {USAGE_PY}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def accounts() -> dict[str, Path]:
    try:
        return dict(_usage().all_configs())
    except (OSError, RuntimeError, SyntaxError):
        return {"default": Path.home() / ".claude"}


def env_for(account: str) -> dict:
    """The environment a session on `account` runs with."""
    env = dict(os.environ)
    env.pop("CLAUDE_CONFIG_DIR", None)
    env.pop("CLAUDECODE", None)
    config = accounts().get(account)
    if config and account != "default":
        env["CLAUDE_CONFIG_DIR"] = str(config)
    local_bin = str(Path.home() / ".local" / "bin")
    if local_bin not in env.get("PATH", "").split(":"):
        env["PATH"] = local_bin + ":" + env.get("PATH", "/usr/bin:/bin")
    return env


def simplify(raw: dict) -> dict:
    """usage.py's answer for one account -> {"five", "week", "resets"}."""
    five = raw.get("five_hour") or {}
    week = raw.get("seven_day") or {}
    return {
        "five": five.get("utilization"),
        "week": week.get("utilization"),
        "resets": five.get("resets_at"),
        "week_resets": week.get("resets_at"),
        "age": raw.get("_age", 0),
    }


def token_expired(config: Path, now: float | None = None) -> bool:
    """The login's access token is past its expiry time."""
    try:
        creds = json.loads((config / ".credentials.json").read_text())
        expires = float((creds.get("claudeAiOauth") or {}).get("expiresAt") or 0)
    except (OSError, ValueError, AttributeError):
        return False
    return bool(expires) and expires / 1000 < (now or time.time())


def refresh_login(account: str, now: float | None = None, spawn=None) -> bool:
    """Start a tiny Claude call on `account` so Claude Code refreshes its
    login; False when one ran in the last REFRESH_GAP seconds."""
    now = now or time.time()
    if now - _refreshed.get(account, 0) < REFRESH_GAP:
        return False
    _refreshed[account] = now
    from claude_launch import find_claude  # the boss's PATH has no ~/.local/bin

    claude = find_claude("RELAY_CLAUDE_BIN")
    if not claude:
        return False
    argv = [
        claude,
        "-p",
        "Reply with the single word ok.",
        "--model",
        "haiku",
        "--max-turns",
        "1",
        "--no-session-persistence",
        "--tools",
        "",
    ]
    try:
        (spawn or _spawn)(argv, env_for(account))
    except OSError:
        return False
    return True


def _spawn(argv: list[str], env: dict) -> None:
    subprocess.Popen(
        argv,
        cwd="/tmp",
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def _past(stamp, now: float) -> bool:
    try:
        return datetime.fromisoformat(str(stamp)).timestamp() < now
    except ValueError:
        return False


def stale(reading: dict, now: float | None = None) -> bool:
    """An old cached reading whose window has already reset says nothing
    about now (the default account showed a 4-day-old week at 99 percent
    while the usage server kept answering 429)."""
    now = now or time.time()
    if float(reading.get("age") or 0) < STALE_AFTER:
        return False
    return any(_past(reading.get(k), now) for k in ("resets", "week_resets"))


def read(force: bool = False) -> dict:
    """{account: {"five": %, "week": %, ...}}; an account that failed has
    "error" and no numbers."""
    if not force and time.time() - _cache["at"] < CACHE_SECONDS:
        return _cache["data"]
    out: dict = {}
    try:
        usage = _usage()
        configs = usage.all_configs()
    except (OSError, RuntimeError, SyntaxError) as e:
        return {"default": {"five": None, "week": None, "error": str(e)}}
    now = time.time()
    for name, config in configs.items():
        try:
            out[name] = simplify(usage.fetch(config))
        except Exception as e:  # network, token, JSON: all mean "no reading"
            out[name] = {"five": None, "week": None, "error": str(e)[:200]}
        if stale(out[name], now):
            age = int(out[name].get("age") or 0) // 60
            out[name] = {
                "five": None,
                "week": None,
                "error": f"stale reading ({age} min old)",
            }
        if UNAUTHORISED.search(str(out[name].get("error", ""))) or token_expired(
            config, now
        ):
            if refresh_login(name, now):
                out[name]["error"] = (
                    out[name].get("error") or "login expired"
                ) + "; refreshing the login"
    _cache.update(at=time.time(), data=out)
    return out


def until(iso, now: float | None = None) -> str:
    """ "14:23 (in 2h05m)" for an ISO reset time, "" when there is none."""
    try:
        at = datetime.fromisoformat(str(iso)).timestamp()
    except ValueError:
        return ""
    left = max(0, int(at - (now or time.time())))
    clock = time.strftime(
        "%H:%M" if left < 20 * 3600 else "%a %H:%M", time.localtime(at)
    )
    return f"{clock} (in {left // 3600}h{left % 3600 // 60:02d}m)"


def describe(readings: dict, settings: dict, now: float | None = None) -> list[str]:
    """Both meters, calmly: one line per account, a full one only saying when
    it is back, then which accounts can take work. Emerson has two
    subscriptions (2026-10-07: "stop complaining about one being at full
    usage"), so the one warning, "No account can launch", is said only when
    none has room."""
    import picker  # pure; imported here so picker never depends on meters

    room = picker.has_room(readings, settings)
    lines, backs = [], []
    for name, m in sorted(readings.items()):
        if m.get("five") is None:
            lines.append(
                f"{name}: no reading ({str(m.get('error') or 'unknown')[:80]})"
            )
            continue
        line = f"{name}: 5-hour {m['five']:.0f}%, week {m.get('week') or 0:.0f}%"
        if name not in room:
            week_full = (m.get("week") or 0) >= picker.limits(settings, name)[
                "weekly_stop_at"
            ]
            back = until(m.get("week_resets" if week_full else "resets"), now)
            line += ", resting" + (f", back {back}" if back else "")
            if back:
                backs.append((m.get("week_resets" if week_full else "resets"), back))
        lines.append(line)
    if room:
        lines.append("Room to launch on " + " and ".join(room) + ".")
    elif readings:
        soonest = min(backs)[1] if backs else ""
        lines.append(
            "No account can launch now"
            + (f"; usage comes back {soonest}" if soonest else "")
            + "."
        )
    return lines
