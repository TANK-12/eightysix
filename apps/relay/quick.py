"""Quick commands: answered by plain Python on any channel, no model at all.

Emerson (2026-10-07): "command list" on WhatsApp got nothing back, and he
wants kill switches and a look at what is eating the laptop without waiting
for a model. Each command is one entry in COMMANDS: the phrases that call it
(whole message, case and a trailing "." or "!" ignored), the line the command
list shows, and its handler. A new quick command is one entry here.

The top lists number their rows and remember them (hogs.json in the data
folder, for HOGS_MINUTES) so "kill 3" ends row 3 of the list he saw; the pid
is checked against its start time first, so a reused pid is never hit.
Protected processes (the desktop, the shell, Relay itself and its WhatsApp)
are never killed.

"find <name>" searches his home for files the same way (found.json) so
"send 2" sends row 2 to WhatsApp (Emerson, 2026-10-07: "let me search for
files and get them sent"). Hidden folders, key-like names and Relay's own
data are never searched or sent.
"""

from __future__ import annotations

import fnmatch
import os
import re
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parent
SHARED = Path(os.environ.get("FORGE_SHARED_DIR") or ROOT.parent.parent / "shared")
for extra in (str(ROOT), str(SHARED)):
    if extra not in sys.path:
        sys.path.insert(0, extra)

import forge_sysinfo  # noqa: E402
import store  # noqa: E402

HOGS_MINUTES = 15
# comm names (as /proc/<pid>/comm shows them) that a kill never touches
PROTECTED = (
    "systemd",
    "gnome-shell",
    "Hyprland",
    "Xwayland",
    "gdm",
    "dbus-daemon",
    "dbus-broker",
    "pipewire",
    "wireplumber",
    "sshd",
    "earlyoom",
    "whatsie",  # Relay's own WhatsApp: killing it cuts this chat
)


@dataclass
class Quick:
    name: str
    phrases: str  # a regex for the whole message; groups go to the handler
    help: str  # the command list line ("" keeps it off the list)
    run: Callable[..., str]


POLITE = re.compile(
    r"^(please|pls|plz|hey|ok|okay|relay)[ ,]+|[ ,]+(please|pls|plz|thanks|ta|mate|now)$"
)


def _clean(text: str) -> str:
    said = re.sub(r"\s+", " ", text.strip().lower()).strip(" .!?").lstrip("-/ ")
    for _ in range(3):  # "please kill all now thanks"
        said = POLITE.sub("", said).strip(" .!?,")
    return said


# ---- the machine ---------------------------------------------------------------


def _gpu_busy() -> str:
    import forge_gpuload

    rows = [r for r in forge_gpuload.top_gpu(3, 0.5) if r["share"] >= 0.01]
    if not rows:
        return "GPU idle"
    total = sum(r["share"] for r in rows)
    return f"GPU {total * 100:.0f}% busy (mostly {rows[0]['name']})"


def stats_text(cpu_sample_seconds: float = 0.5) -> str:
    """One short block: CPU, temperature, memory, GPU, battery, disk, Jan."""
    sample = forge_sysinfo.system_stats()[1]
    time.sleep(cpu_sample_seconds)
    stats, _ = forge_sysinfo.system_stats(sample)
    temps = forge_sysinfo.temperatures()
    parts = []
    line = f"CPU {stats['cpu']}%" if stats.get("cpu") is not None else "CPU ?"
    if "cpu" in temps:
        line += f", {temps['cpu']:.0f}°C"
    if temps.get("fans"):
        line += f", fan {temps['fans'][0]} rpm"
    try:
        line += ", load " + " ".join(open("/proc/loadavg").read().split()[:3])
    except OSError:
        pass
    parts.append(line)
    if stats.get("mem") is not None:
        parts.append(f"Memory {stats['mem']}% used")
    parts.append(_gpu_busy())
    if stats.get("battery") is not None:
        plug = "plugged in" if stats.get("plugged") else "on battery"
        parts.append(f"Battery {stats['battery']}%, {plug}")
    disks = forge_sysinfo.disks()
    if disks:
        d = disks[0]
        parts.append(
            f"Fullest disk {d.get('name')} {d.get('used')}% used "
            f"({d.get('free_gb', '?')} GB free)"
        )
    jan = forge_sysinfo.jan_status()
    loaded = ", ".join(jan.get("loaded") or []) or "no model loaded"
    parts.append(f"Jan {'up' if _jan_up() else 'down'}: {loaded}")
    others = {k: v for k, v in temps.items() if k not in ("cpu", "fans")}
    if others:
        parts.append(
            "Other temps: "
            + ", ".join(f"{k} {v:.0f}°C" for k, v in sorted(others.items()))
        )
    try:
        up = float(open("/proc/uptime").read().split()[0])
        parts.append(f"Up {int(up // 3600)}h{int(up % 3600 // 60):02d}m")
    except (OSError, ValueError):
        pass
    return "\n".join(parts)


def _jan_up() -> bool:
    import forge_jan

    return forge_jan.router_alive(timeout=1.0)


def _hogs_file() -> Path:
    return store.data_dir() / "hogs.json"


def _remember(kind: str, rows: list[dict]) -> None:
    store.write_json(
        _hogs_file(),
        {
            "at": time.time(),
            "kind": kind,
            "rows": [
                {"pid": r["pid"], "start": r.get("start"), "comm": r["comm"]}
                for r in rows
            ],
        },
    )


def top_text(kind: str = "cpu", count: int = 10) -> str:
    if kind == "gpu":
        import forge_gpuload

        rows = forge_gpuload.top_gpu(count, 1.0)
        for r in rows:
            r["start"] = forge_sysinfo.start_time(r["pid"])
        lines = [
            f"{i}. {r['name']} {r['share'] * 100:.0f}% (pid {r['pid']})"
            + (" [desktop/Forge]" if r["ours"] else "")
            for i, r in enumerate(rows, 1)
        ]
        title = "Top GPU users over 1 s"
    else:
        rows = forge_sysinfo.top_cpu(count, 1.0)
        lines = [
            f"{i}. {r['comm']} {r['cpu']}% CPU, {r['mem_mb']} MB (pid {r['pid']})"
            for i, r in enumerate(rows, 1)
        ]
        title = "Top CPU users over 1 s (100% = one core)"
    if not rows:
        return f"Nothing is using the {kind.upper()} right now."
    _remember(kind, rows)
    return (
        title
        + ":\n"
        + "\n".join(lines)
        + "\n\nkill 3 ends number 3 (force kill 3 if it will not go)."
    )


def protected(pid: int, comm: str) -> str:
    """Why a process may not be killed ("" when it may)."""
    if pid <= 1 or pid == os.getpid() or pid in _ancestors(os.getpid()):
        return "it is Relay itself or the system"
    if comm.startswith(PROTECTED) or comm.startswith("systemd"):
        return f"{comm} keeps the desktop or this chat running"
    cmd = _cmdline(pid)
    if "boss.py" in cmd and "relay" in cmd:
        return "it is Relay's boss"
    return ""


def _cmdline(pid: int) -> str:
    try:
        return Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\0", b" ").decode()
    except OSError:
        return ""


def _ancestors(pid: int) -> set[int]:
    seen: set[int] = set()
    at = pid
    for _ in range(30):
        try:
            stat = Path(f"/proc/{at}/stat").read_text()
            at = int(stat[stat.rfind(")") + 2 :].split()[1])
        except (OSError, ValueError, IndexError):
            break
        if at <= 1 or at in seen:
            break
        seen.add(at)
    return seen


def _gone(pid: int, start) -> bool:
    """Ended (or a zombie waiting for its parent), or the pid now belongs to
    a newer process."""
    if forge_sysinfo.start_time(pid) != start:
        return True
    try:
        stat = Path(f"/proc/{pid}/stat").read_text()
    except OSError:
        return True
    return stat[stat.rfind(")") + 2 :].startswith("Z")


def kill_rows(numbers: list[int], force: bool = False) -> str:
    data = store.read_json(_hogs_file()) or {}
    if not data.get("rows") or time.time() - data.get("at", 0) > HOGS_MINUTES * 60:
        return "No fresh list to pick from. Write top cpu or top gpu first."
    rows = data["rows"]
    out = []
    for n in numbers:
        if not 1 <= n <= len(rows):
            out.append(f"{n}: not on the list (1 to {len(rows)}).")
            continue
        row = rows[n - 1]
        pid, comm = int(row["pid"]), str(row["comm"])
        if _gone(pid, row.get("start")):
            out.append(f"{n}. {comm}: already gone.")
            continue
        why = protected(pid, comm)
        if why:
            out.append(f"{n}. {comm}: left alone, {why}.")
            continue
        sig = signal.SIGKILL if force else signal.SIGTERM
        try:
            os.kill(pid, sig)
        except OSError as e:
            out.append(f"{n}. {comm}: could not ({e.strerror}).")
            continue
        end = time.time() + 3
        while time.time() < end and not _gone(pid, row.get("start")):
            time.sleep(0.2)
        gone = _gone(pid, row.get("start"))
        store.event("kill", f"{'force ' if force else ''}killed {comm} (pid {pid})")
        out.append(
            f"{n}. {comm}: "
            + (
                "ended."
                if gone
                else "asked to stop, still there. force kill " + str(n) + " ends it."
            )
        )
    return "\n".join(out)


# ---- Relay ----------------------------------------------------------------------


def kill_everything() -> str:
    """Every running Relay session stopped and launches paused."""
    import chat
    import items
    import runs

    stopped = []
    for run in runs.active():
        runs.stop(run)
        task = items.find_task(run["task"]) if run.get("task") else None
        if task:
            task["status"] = chat.IDLE if chat.is_chat(task) else "stopped"
            items.save(task)
        stopped.append(str(run.get("task") or run.get("goal") or run["id"]))
    store.save_settings({"paused": True})
    try:
        import frontdesk

        frontdesk.JAN.release_mine()
    except Exception:  # Jan not reachable: nothing of ours is loaded anyway
        pass
    store.event("stop", f"kill everything: {len(stopped)} session(s)")
    store.poke()
    done = (
        f"Stopped {len(stopped)} session(s): task {', '.join(stopped)}"
        if stopped
        else "Nothing was running"
    )
    return done + ". New launches are paused; write resume to allow them again."


def kill_task(number: str) -> str:
    import actions

    return actions.stop_task(int(number))


# ---- the chat mode ----------------------------------------------------------------


def mode_text() -> str:
    import localchat

    return localchat.describe()


def set_mode(mode: str) -> str:
    import localchat

    return localchat.set_mode(mode)


def local_model(choice: str = "") -> str:
    import localchat

    return localchat.pick_model(choice)


# Emerson asked the local model to "shut down the computer" (2026-10-07
# 15:52) and got filler. A model never does it; this command asks first and
# only "yes shut down" within POWER_WAIT seconds turns the laptop off.
POWER_WAIT = 120
POWER_DELAY = 15


def _power_file() -> Path:
    return store.path("shutdown.json")


def shutdown_ask() -> str:
    store.write_json(_power_file(), {"asked": time.time()})
    return (
        "Sure? That turns the laptop off: every running Claude session, Jan and "
        "Forge stop, and Relay is gone until you switch it back on. Reply yes "
        f"shut down within {POWER_WAIT // 60} minutes to do it."
    )


def _power_off() -> None:
    if os.environ.get("PYTEST_CURRENT_TEST"):  # never from a test run
        return
    subprocess.Popen(
        ["sh", "-c", f"sleep {POWER_DELAY}; systemctl poweroff"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def shutdown_yes() -> str:
    asked = (store.read_json(_power_file()) or {}).get("asked") or 0
    if time.time() - asked > POWER_WAIT:
        return "No shut down was asked in the last two minutes. Write shut down first."
    store.write_json(_power_file(), {"asked": 0, "done": time.time()})
    store.event("quick", "shut down confirmed")
    _power_off()
    return f"Shutting the laptop down in {POWER_DELAY} seconds. Night!"


def think(value: str) -> str:
    import localchat

    return localchat.set_thinking(value)


def web(query: str) -> str:
    import forge_websearch

    return forge_websearch.text(query, 6)


def jan_text(start: bool = False) -> str:
    import forge_jan

    if start:
        ok = forge_jan.ensure_router(wait=40.0)
        if not ok:
            return "Could not start Jan (its llama-server build or preset is missing)."
    loaded = forge_jan.loaded_models()
    if not _jan_up():
        return "Jan is down. jan start starts its model server (no window)."
    return "Jan is up. Loaded: " + (", ".join(loaded) or "nothing right now") + "."


# ---- files: find, then send ----------------------------------------------------------

FIND_SECONDS = 6.0
FIND_ROWS = 10
SEND_MAX_MB = 100
# folder names a search never walks into (besides hidden ones)
SKIP_DIRS = ("node_modules", "__pycache__", "site-packages", "wineprefix", "venv")
SECRET_NAME = re.compile(
    r"secret|passw|token|credential|id_rsa|id_ed25519|\.pem$|\.key$|\.kdbx$", re.I
)


def _found_file() -> Path:
    return store.data_dir() / "found.json"


def unsendable(path: Path) -> str:
    """Why a file may not be searched for or sent, or "" when it may."""
    home = Path.home().resolve()
    path = path.resolve()
    if home not in path.parents:
        return "only files in your home folder"
    data = store.data_dir().resolve()
    if path == data or data in path.parents:
        return "never Relay's own data"
    if any(part.startswith(".") for part in path.relative_to(home).parts):
        return "never hidden files (keys and settings live there)"
    if SECRET_NAME.search(path.name):
        return "that looks like a key or password file"
    return ""


def find_files(query: str, root: Path | None = None) -> tuple[list[Path], bool]:
    """Files in his home whose name holds every word of `query` (or matches
    it as a glob such as *.blend), newest first, and whether the search ran
    out of time before it covered everything."""
    query = query.strip().lower()
    words = query.split()
    glob = any(c in query for c in "*?[")
    end = time.time() + FIND_SECONDS
    hits: list[Path] = []
    timed_out = False
    for folder, dirs, files in os.walk(root or Path.home()):
        dirs[:] = [d for d in dirs if not d.startswith(".") and d not in SKIP_DIRS]
        for name in files:
            low = name.lower()
            if fnmatch.fnmatch(low, query) if glob else all(w in low for w in words):
                hits.append(Path(folder) / name)
        if time.time() > end or len(hits) >= 400:
            timed_out = True
            break

    def newest(p: Path) -> float:
        try:
            return p.stat().st_mtime
        except OSError:
            return 0.0

    hits = [p for p in hits if not unsendable(p)]
    return sorted(hits, key=newest, reverse=True), timed_out


def _size(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return ""


def find_text(query: str) -> str:
    if not query.strip():
        return "Find what? find <part of the name>, or find *.blend"
    hits, timed_out = find_files(query)
    rows = hits[:FIND_ROWS]
    store.write_json(
        _found_file(), {"at": time.time(), "paths": [str(p) for p in rows]}
    )
    if not rows:
        return f"No files called {query} in your home folder." + (
            " (the search stopped after a few seconds; try a longer name)"
            if timed_out
            else ""
        )
    home = str(Path.home())
    lines = []
    for i, p in enumerate(rows, 1):
        try:
            st = p.stat()
            when = time.strftime("%-d %b", time.localtime(st.st_mtime))
            info = f"{_size(st.st_size)}, {when}"
        except OSError:
            info = "gone"
        lines.append(f"{i}. {p.name} ({str(p.parent).replace(home, '~', 1)}, {info})")
    more = len(hits) - len(rows)
    tail = f"\n...and {more} more; add a word to narrow it." if more > 0 else ""
    if timed_out:
        tail += "\n(stopped after a few seconds, so there may be more)"
    return (
        f"Files matching {query}:\n" + "\n".join(lines) + tail + "\nsend 2 sends one."
    )


def send_found(numbers: list[int]) -> str:
    data = store.read_json(_found_file()) or {}
    if not data.get("paths") or time.time() - data.get("at", 0) > 2 * HOGS_MINUTES * 60:
        return "No fresh file list. Write find <name> first."
    paths, out = data["paths"], []
    picked: list[str] = []
    for n in numbers:
        if not 1 <= n <= len(paths):
            out.append(f"{n}: not on the list (1 to {len(paths)}).")
            continue
        path = Path(paths[n - 1])
        why = unsendable(path) or ("" if path.is_file() else "it is gone")
        if not why and path.stat().st_size > SEND_MAX_MB * 1024 * 1024:
            why = f"over {SEND_MAX_MB} MB"
        if why:
            out.append(f"{n}. {path.name}: not sent, {why}.")
        else:
            picked.append(str(path))
    if picked:
        import chat

        out.append(chat.send_files(picked))
    return "\n".join(out)


def tidy_chat() -> str:
    import chatlog  # the boss's chat log and tidy-up

    return chatlog.request()


def help_lines(lead: str = "- ") -> str:
    return "\n".join(f"{lead}{q.help}" for q in COMMANDS if q.help)


def command_list() -> str:
    lines = ["Quick commands (instant, no model):", help_lines()]
    lines += [
        "",
        "Relay: status, progress, progress 12, usage, pause, resume, stop 12, "
        "retry 12, tell 12 text, #12 text, new: job, notify quiet / mine / all.",
        "",
        "Anything else is chat: Claude answers, or the local model when you "
        "write local (or when Claude is out of usage).",
    ]
    return "\n".join(lines)


COMMANDS = [
    Quick(
        "commands",
        r"(command[ -]?list|commands?[ -]?list|list (of )?commands|commands|cmds?|menu|h"
        r"|what can (you|i) (do|say|type|write))",
        "command list: this list",
        lambda: command_list(),
    ),
    Quick(
        "stats",
        r"(stats|system|pc|laptop|computer|temps?|temperature|heat|how hot)",
        "stats: CPU, temperature, memory, GPU, battery, disk, Jan",
        lambda: stats_text(),
    ),
    Quick(
        "top-gpu",
        r"(top gpu|gpu top|gpu hogs?|hogs? gpu|gpu)",
        "top gpu: the 10 biggest GPU users, numbered",
        lambda: top_text("gpu"),
    ),
    Quick(
        "top-cpu",
        r"(top|top cpu|cpu top|top 10|cpu hogs?|hogs?|cpu)",
        "top cpu: the 10 biggest CPU users, numbered",
        lambda: top_text("cpu"),
    ),
    Quick(
        "force-kill",
        r"(?:force kill|kill -9|kill hard)\s+((?:\d+[ ,]*(?:and\s+)?)+)",
        "kill 3 (or kill 3 5): end those rows of the last top list; force kill 3",
        lambda nums: kill_rows([int(n) for n in re.findall(r"\d+", nums)], True),
    ),
    Quick(
        "kill-task",
        r"(?:kill|stop) task\s*#?(\d+)",
        "kill task 12: stop Relay task 12",
        lambda n: kill_task(n),
    ),
    Quick(
        "kill",
        r"kill\s+((?:\d+[ ,]*(?:and\s+)?)+)",
        "",
        lambda nums: kill_rows([int(n) for n in re.findall(r"\d+", nums)]),
    ),
    Quick(
        "kill-all",
        r"(kill (all|everything|it all)|stop (all|everything)|kill switch)",
        "kill all: stop every Relay session and pause new ones",
        lambda: kill_everything(),
    ),
    Quick(
        "local",
        r"(local|offline|go local|use local|local mode|local chat|use jan|jan mode)",
        "local: the local model answers the chat (no usage); claude: back to Claude",
        lambda: set_mode("local"),
    ),
    Quick(
        "claude",
        r"(claude|online|go claude|use claude|claude mode|back to claude|claude chat)",
        "",
        lambda: set_mode("claude"),
    ),
    Quick(
        "desk",
        r"(desk|front desk|desk mode)",
        "desk: the local model answers first and hands bigger things to Claude",
        lambda: set_mode("desk"),
    ),
    Quick(
        "boss",
        r"(boss|boss mode|boss line|talk to (the )?boss)",
        "boss: every message goes to Relay's boss (or one: boss <question>)",
        lambda: set_mode("boss"),
    ),
    Quick(
        "mode",
        r"(mode|chat mode|which mode|who is answering|whos answering)",
        "mode: who answers the chat right now",
        lambda: mode_text(),
    ),
    Quick(
        "local-model",
        r"(?:local model|small model|jan model)\s*(.*)",
        "local model (or local model 2b): list or pick the local model",
        lambda choice: local_model(choice),
    ),
    Quick(
        "shutdown-yes",
        r"(?:yes,? ?)(?:shut ?down|power off|turn (?:it )?off)",
        "",
        lambda: shutdown_yes(),
    ),
    Quick(
        "shutdown",
        r"(?:(?:shut ?down|power off)(?: the| my)?(?: computer| laptop| pc)?"
        r"|turn off(?: the| my)? (?:computer|laptop|pc))",
        "shut down: turn the laptop off (asks you to reply yes shut down first)",
        lambda: shutdown_ask(),
    ),
    Quick(
        "think",
        r"think(?:ing)?\s+(on|off|auto)",
        "think on / off / auto: the local model reasons first (auto: hard questions)",
        lambda value: think(value),
    ),
    Quick(
        "web",
        r"(?:web search|google(?!\s+(?:is|was|has|keeps|just|seems|'s)\b)"
        r"|search (?:the )?(?:web|online|internet)(?: for)?)\s+(.+)",
        "google <words> (or web search <words>): search the web, numbered",
        lambda query: web(query),
    ),
    Quick(
        "jan",
        r"(?:jan|jan status)( start)?",
        "jan / jan start: is Jan up, start it",
        lambda start: jan_text(bool(start)),
    ),
    Quick(
        "find-files",
        r"(?:(?:find|search(?: for)?|look for|locate)\s+files?\s+"
        r"|(?:find|search|locate)\s+(?=\S+$)(?!(?:out|it|that|this|them|me|more|why|how)$))(.+)",
        "find report (or find *.blend): search your files, numbered",
        lambda query: find_text(query),
    ),
    Quick(
        "send-found",
        r"send\s+(?:file\s+|number\s+|no\.?\s*)?((?:\d+[ ,]*(?:and\s+)?)+)",
        "send 2 (or send 1 3): send those files from the last find to WhatsApp",
        lambda nums: send_found([int(n) for n in re.findall(r"\d+", nums)]),
    ),
    Quick(
        "tidy-chat",
        r"(tidy( up)?( the)?( chat)?|clean ?up( the)? chat|summari[sz]e( the)? chat)",
        "tidy chat: older messages become one summary (full text kept in a log)",
        lambda: tidy_chat(),
    ),
]
_COMPILED = [(q, re.compile(q.phrases + r"$", re.I)) for q in COMMANDS]


def match(text: str) -> tuple[str, tuple] | None:
    """(command name, its arguments) when the whole message is a quick
    command, else None."""
    said = _clean(text)
    for q, pattern in _COMPILED:
        m = pattern.match(said)
        if m:
            args = m.groups() if q.run.__code__.co_argcount else ()
            return q.name, tuple(a or "" for a in args[: q.run.__code__.co_argcount])
    return None


def run(name: str, args: tuple = ()) -> str:
    for q in COMMANDS:
        if q.name == name:
            try:
                return q.run(*args)
            except Exception as e:  # a quick command never takes the boss down
                store.event("error", f"quick {name}: {type(e).__name__}: {e}")
                return f"That failed: {type(e).__name__}: {e}"
    return f"No quick command {name}."
