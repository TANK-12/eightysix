"""Running Claude Code for the panel: one `claude -p` process per conversation.

The process speaks stream-json both ways (shapes checked against the real CLI,
2.1.270): the panel writes `{"type": "user", "message": {...}}` lines to its
stdin and reads events from its stdout - `system` (init: session id, model),
`stream_event` (live text deltas), `assistant` (whole messages, tool calls),
`user` (tool results), `result` (cost, duration, errors).

A conversation's process is started on its first message and kept for the next
ones. If it stops (Stop, a settings change, a crash, a Forge restart) the next
message starts a new one with `--resume <session id>`, so the conversation
carries on. Events other than the live deltas are written to disk, so the
history is there after a restart.

Accounts: `Profiles` keeps one config directory per Claude account. "default"
is Claude Code's own (~/.claude); every other profile is
<data>/profiles/<name>, handed to the CLI as CLAUDE_CONFIG_DIR, so it holds its
own login. Everything else that shapes Claude (CLAUDE.md, settings, skills,
agents, output styles, commands, plugins, and projects/ with its memory and
transcripts) is a symlink to the default profile's, made by
`Profiles.link_shared`, so every account acts and knows the same and a session
id resumes under any of them. A conversation remembers its profile.

Nothing here knows about the web page: web_app.py serves this over HTTP.
"""

from __future__ import annotations

import base64
import importlib.util
import json
import math
import os
import re
import shutil
import signal
import secrets
import subprocess
import threading
import time
import uuid
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

import names
import panel_commands
import personas

USAGE_TOOL = Path.home() / ".claude/tools/usage.py"
# Emerson (2026-09-27): conversations in no folder move to Archived once they
# have been quiet this long. The live value is Settings > Apps (web_app.py).
AUTO_ARCHIVE_HOURS = 2.0
# Sent to a conversation that was cut off mid-turn by a restart.
RESUME_MESSAGE = (
    "Forge restarted while you were working (a Forge restart or a reboot). "
    "Carry on from where you stopped. Check the state of anything that was "
    "running before repeating it."
)
USAGE_EVERY = 120  # seconds between live usage checks per account
USAGE_MAX_BACKOFF = 900  # the longest wait after the endpoint says "too many"


def usage_from_live(raw: dict) -> dict:
    """The usage endpoint's answer, in the shape the stream's rate_limit_event
    gives: used as a fraction, resets_at in epoch seconds."""
    # usage.py hands back its last reading, with its age, when the server
    # asks it to wait; date it by that age, not by now
    try:
        age = max(0.0, float(raw.get("_age") or 0))
    except (TypeError, ValueError):
        age = 0.0
    seen = time.time() - age
    out: dict = {"seen": seen, "source": "live"}
    for key in ("five_hour", "seven_day"):
        window = raw.get(key)
        if not isinstance(window, dict) or window.get("utilization") is None:
            continue
        resets = window.get("resets_at")
        try:
            resets = int(datetime.fromisoformat(str(resets)).timestamp())
        except ValueError:
            resets = None
        out[key] = {
            "used": window["utilization"] / 100,
            "resets_at": resets,
            "seen": seen,
        }
    return out


def merge_usage(stored: dict, live: dict) -> dict:
    """A live reading merged into what is stored, never going back in time
    (Emerson, 2026-10-07: the bar flipped between fresh numbers and a 4-day-old
    cached reading usage.py hands back while the endpoint answers 429). Each
    window keeps whichever reading is newer, dated by its own "seen" or else
    the stored one's; "seen" and "source" follow only when the live reading is
    the newer one. A good check clears the last error, an old one notes why."""
    merged = dict(stored)
    stored_seen = float(stored.get("seen") or 0)
    live_seen = float(live.get("seen") or 0)
    for key in ("five_hour", "seven_day"):
        window = live.get(key)
        if not isinstance(window, dict):
            continue
        old = stored.get(key)
        old_seen = (
            float(old.get("seen") or stored_seen) if isinstance(old, dict) else -1.0
        )
        if live_seen >= old_seen:
            merged[key] = window
    if live_seen >= stored_seen:
        merged["seen"] = live_seen
        merged["source"] = live.get("source", "live")
        merged.pop("check", None)
    else:
        merged["check"] = {
            "at": time.time(),
            "error": "usage server is rate-limiting; showing the newer numbers from this panel",
            "retry_in": 0,
        }
    return merged


def _usage_tool_fetch():
    """usage.py's fetch(config_dir), shared rather than copied; None if missing."""
    if not USAGE_TOOL.is_file():
        return None
    spec = importlib.util.spec_from_file_location("forge_usage_tool", USAGE_TOOL)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return getattr(module, "fetch", None)


APP = Path(__file__).resolve().parent
DATA_DIR = Path(
    os.environ.get("FORGE_CLAUDE_DATA", Path.home() / ".local/share/forge/claude")
)
BROWSER_URL = os.environ.get("FORGE_BROWSER_URL", "http://127.0.0.1:8444")

DEFAULT_PROFILE = "default"
# session_costs key for a cost summed before the 2026-10-07 fix (too high)
EARLIER_COST = "earlier"
PROFILE_NAME = re.compile(r"[a-z0-9][a-z0-9_-]{0,31}")
STATUS_CACHE_SECONDS = 60
# The default profile's config directory, which the others share from.
MAIN_CONFIG = Path.home() / ".claude"
MAIN_JSON = Path.home() / ".claude.json"  # user-level MCP servers live here
# What every profile shares with the default one; the login (.credentials.json,
# .claude.json) and per-process scratch folders stay each profile's own.
SHARED_FILES = ("CLAUDE.md", "settings.json")
SHARED_DIRS = (
    "skills",
    "agents",
    "output-styles",
    "commands",
    "plugins",
    "projects",
    # each running session writes <pid>.json here; one shared folder lets
    # Crew Room, the Board and the notes hook see every account's sessions
    "sessions",
)


def claude_command() -> list[str]:
    """How to start Claude Code. FORGE_CLAUDE_BIN may hold a full command."""
    override = os.environ.get("FORGE_CLAUDE_BIN")
    if override:
        return override.split()
    found = shutil.which("claude")
    if found:
        return [found]
    # Forge started from the desktop launcher often has no ~/.local/bin on
    # PATH, which is where Claude Code's installer puts `claude`.
    for candidate in (
        Path.home() / ".local/bin/claude",
        Path.home() / ".claude/local/claude",
        Path("/usr/local/bin/claude"),
        Path("/usr/bin/claude"),
    ):
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return [str(candidate)]
    return []


# Permission levels, least to most. The key is Claude Code's --permission-mode.
# Every level can read, search the web and use the Forge Browser; anything that
# would need a yes/no prompt is refused, because nobody can answer one here.
MODES = {
    "dontAsk": "Read files, search the web and use the Browser",
    "plan": "Plan only: look around and propose, change nothing",
    "acceptEdits": "Also edit files in the working folder",
    "auto": "Claude Code's auto mode decides what is safe to run",
    "bypassPermissions": "Anything, with no checks",
}
DEFAULT_MODE = "dontAsk"
ALWAYS_ALLOWED = ["Read", "Glob", "Grep", "WebSearch", "WebFetch", "mcp__forge-browser"]

# "" leaves the choice to Claude Code's own default.
MODELS = {
    "": "Claude Code's default",
    "opus": "Opus",
    "fable": "Fable",
    "claude-sonnet-5-5": "Sonnet 5.5",
    "sonnet": "Sonnet (newest)",
    "haiku": "Haiku",
}
# claude --effort; "" leaves it to Claude Code.
EFFORTS = {
    "": "Default",
    "low": "Low",
    "medium": "Medium",
    "high": "High",
    "xhigh": "Extra high",
    "max": "Max",
}

# Ultracode (Claude Code 2.1.289): standing dynamic-workflow orchestration for
# the whole session, at any effort. Checked live 2026-10-07 with the
# get_settings control request: {"ultracode": true} alone is not applied while
# dynamic workflows are off, so enableWorkflows goes with it; Opus, Fable,
# Sonnet and the default model take it, Haiku does not.
ULTRACODE_SETTINGS = {"ultracode": True, "enableWorkflows": True}
ULTRACODE_UNSUPPORTED = ["haiku"]
# The control request sent at start when ultracode is asked for; its answer
# says whether it is really in effect (meta["ultracode_state"]).
SETTINGS_PROBE = "forge-settings"

# Limits on the helpers (subagents) a conversation may start, each one an
# environment variable Claude Code reads at start. The page draws its controls
# from this, so a new limit is one entry here. Unset = Claude Code's default.
AGENT_LIMITS: dict[str, dict] = {
    "max_helpers": {
        "env": "CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS",
        "kind": "int",
        "min": 1,
        "max": 50,
        "default": "20",
        "label": "Helpers at once",
        "help": "How many helpers (subagents) may run at the same time",
    },
    "spawn_depth": {
        "env": "CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH",
        "kind": "int",
        "min": 1,
        "max": 6,
        "default": "Claude Code's",
        "label": "Helper nesting",
        "help": "How many levels deep helpers may start helpers of their own",
    },
    "helper_model": {
        "env": "CLAUDE_CODE_SUBAGENT_MODEL",
        "kind": "choice",
        "choices": {k: v for k, v in MODELS.items() if k},
        "default": "each helper's own",
        "label": "Helper model",
        "help": "The model every helper runs on",
    },
}


def clean_limits(raw: dict) -> dict:
    """Checked limit values: an int clamped to its range, a known choice, or
    None for "" (back to Claude Code's default). Anything else is dropped."""
    out: dict = {}
    if not isinstance(raw, dict):
        return out
    for key, value in raw.items():
        spec = AGENT_LIMITS.get(key)
        if spec is None:
            continue
        if value is None or value == "":
            out[key] = None
        elif spec["kind"] == "int":
            if isinstance(value, bool) or not isinstance(value, (int, float, str)):
                continue
            try:
                real = float(value)
            except (ValueError, OverflowError):
                continue
            if not math.isfinite(real):
                continue
            number = int(real)
            out[key] = max(spec["min"], min(spec["max"], number))
        elif isinstance(value, str) and value in spec["choices"]:
            out[key] = value
    return out


def apply_limits(env: dict, meta: dict) -> dict:
    """The process environment with this conversation's limits; a limit it does
    not set is removed, so an inherited value never leaks in."""
    limits = meta.get("limits") if isinstance(meta.get("limits"), dict) else {}
    for key, spec in AGENT_LIMITS.items():
        value = (limits or {}).get(key)
        if value is None or value == "":
            env.pop(spec["env"], None)
        else:
            env[spec["env"]] = str(value)
    return env


IMAGE_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
}
MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_ATTACHMENT_BYTES = 50 * 1024 * 1024

SYSTEM_NOTE = (
    "You are running inside Forge, the user's desktop hub, in its Claude panel. "
    "The forge-browser tools drive the Forge Browser, which the user can see on "
    "screen and which carries their logins: use it for web pages they mention, are "
    "logged into, or ask you to look at, and tell them what you opened. Files the "
    "user attaches are listed by path in their message; read them with the Read tool. "
    "The panel_command tool runs Claude Code commands on this session (such as "
    "/compact when your context grows large); it runs once your turn ends."
)

# Live-only events: shown as they stream, not kept on disk.
TRANSIENT = {"stream_event", "rate_limit_event"}
# how long a long poll keeps gathering once the first new event arrives
BATCH_SECONDS = 0.09


def safe_name(name: str) -> str:
    base = Path(str(name or "file")).name
    cleaned = re.sub(r"[^\w.\- ()]+", "_", base).strip(" .") or "file"
    return cleaned[:120]


def clean_text(text: str) -> str:
    """Text with any lone UTF-16 half (a surrogate, from an emoji cut in two)
    replaced by U+FFFD: such text cannot be written as UTF-8, to Claude
    Code's stdin or to the page."""
    return text.encode("utf-16", "surrogatepass").decode("utf-16", "replace")


def mcp_config(
    data_dir: Path | None = None,
    user_config: Path | None = None,
    conv_id: str = "",
) -> Path:
    """The MCP config for every conversation, written once per start: the
    forge-browser server plus the user's own servers from ~/.claude.json
    (Acchan's blender_*, godot_*, assets_* tools). An account other than the
    default reads its own config folder, which has none of them."""
    data_dir = data_dir or DATA_DIR
    data_dir.mkdir(parents=True, exist_ok=True)
    python = "/usr/bin/python3" if Path("/usr/bin/python3").exists() else "python3"
    try:
        user = json.loads((user_config or MAIN_JSON).read_text()).get("mcpServers")
    except (OSError, ValueError, AttributeError):
        user = None
    servers = dict(user) if isinstance(user, dict) else {}
    servers["forge-browser"] = {
        "command": python,
        "args": [str(APP / "browser_mcp.py")],
        "env": {"FORGE_BROWSER_URL": BROWSER_URL},
    }
    path = data_dir / "mcp.json"
    if conv_id:
        # this conversation's own copy: its server queues panel commands
        servers["forge-browser"]["env"]["FORGE_PANEL_QUEUE"] = str(
            command_queue(data_dir, conv_id)
        )
        path = data_dir / "mcp" / f"{safe_name(conv_id)}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
    config = {"mcpServers": servers}
    path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    return path


def command_queue(data_dir: Path, conv_id: str) -> Path:
    """Where a conversation's panel commands wait for its turn to end."""
    return data_dir / "commands" / f"{safe_name(conv_id)}.jsonl"


def command(
    meta: dict, config: Path, attachments: Path, extra_prompt: str = ""
) -> list[str]:
    mode = meta.get("mode") if meta.get("mode") in MODES else DEFAULT_MODE
    args = [
        *claude_command(),
        "-p",
        "--input-format",
        "stream-json",
        "--output-format",
        "stream-json",
        "--verbose",
        "--include-partial-messages",
        "--mcp-config",
        str(config),
        "--permission-mode",
        mode,
        "--permission-prompts",
        "none",
        "--allowedTools",
        ",".join(ALWAYS_ALLOWED),
        "--add-dir",
        str(attachments),
        "--append-system-prompt",
        SYSTEM_NOTE + ("\n\n" + extra_prompt if extra_prompt else ""),
    ]
    if meta.get("model") in MODELS and meta.get("model"):
        args += ["--model", meta["model"]]
    if meta.get("effort") in EFFORTS and meta.get("effort"):
        args += ["--effort", meta["effort"]]
    if meta.get("ultracode"):
        args += ["--settings", json.dumps(ULTRACODE_SETTINGS)]
    if meta.get("session_id"):
        args += ["--resume", meta["session_id"]]
    return args


def user_message(text: str, files: list[Path]) -> dict:
    """What goes to Claude's stdin: images inline, every file listed by path."""
    content: list[dict] = []
    for path in files:
        media = IMAGE_TYPES.get(path.suffix.lower())
        if media and path.stat().st_size <= MAX_IMAGE_BYTES:
            data = base64.standard_b64encode(path.read_bytes()).decode()
            content.append(
                {
                    "type": "image",
                    "source": {"type": "base64", "media_type": media, "data": data},
                }
            )
    note = text.strip()
    if files:
        listing = "\n".join(f"- {p}" for p in files)
        note = f"{note}\n\nAttached files:\n{listing}".strip()
    content.append({"type": "text", "text": note or "(no message)"})
    return {"type": "user", "message": {"role": "user", "content": content}}


def project_slug(cwd: str | Path) -> str:
    """How Claude Code names a working folder under <config>/projects."""
    return re.sub(r"[^\w-]", "-", str(Path(cwd).expanduser().resolve()))


def transcript_path(config_dir: Path, cwd: str | Path, session_id: str) -> Path:
    return config_dir / "projects" / project_slug(cwd) / f"{session_id}.jsonl"


class Login:
    """One `claude auth login` for a profile, run over pipes.

    The CLI prints the sign-in address (and opens the default browser on it),
    then waits on stdin for the code the sign-in page shows. The address and the
    prompt are relayed to the page; the code comes back through `code()`.
    """

    URL = re.compile(r"https://\S+")

    def __init__(self, profile: str, args: list[str], env: dict, cwd: Path):
        self.profile = profile
        self.url = ""
        self.output = ""
        self.error = ""
        self.state = "starting"
        self.started = time.time()
        self._stderr: list[str] = []
        self.proc = subprocess.Popen(
            args,
            cwd=cwd,
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
        threading.Thread(target=self._read, daemon=True).start()
        threading.Thread(target=self._drain, daemon=True).start()

    def _read(self) -> None:
        assert self.proc.stdout is not None
        fd = self.proc.stdout.fileno()
        while True:
            chunk = os.read(fd, 4096)
            if not chunk:
                break
            self.output += chunk.decode("utf-8", "replace")
            for found in self.URL.findall(self.output):
                self.url = found.rstrip(".,)")
            if self.url and self.state == "starting":
                self.state = "waiting"
        code = self.proc.wait()
        if self.state == "cancelled":
            return
        if code == 0:
            self.state = "done"
        else:
            self.state = "failed"
            tail = "\n".join(self._stderr[-3:]).strip()
            self.error = tail or f"claude auth login exited with code {code}"

    def _drain(self) -> None:
        assert self.proc.stderr is not None
        for line in self.proc.stderr:
            self._stderr.append(line.decode("utf-8", "replace").rstrip())
            del self._stderr[:-20]

    def running(self) -> bool:
        return self.proc.poll() is None

    def code(self, text: str) -> None:
        if not self.running():
            raise RuntimeError("That sign-in is over; start it again")
        assert self.proc.stdin is not None
        self.proc.stdin.write((text.strip() + "\n").encode())
        self.proc.stdin.flush()
        self.state = "checking"

    def cancel(self) -> None:
        if self.running():
            self.state = "cancelled"
            try:
                os.killpg(self.proc.pid, signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                pass

    def snapshot(self) -> dict:
        return {
            "profile": self.profile,
            "state": self.state,
            "url": self.url,
            "error": self.error,
            "seconds": round(time.time() - self.started),
        }


def _aside(path: Path) -> Path:
    """A free name beside `path` to keep a profile's own copy under."""
    aside = path.with_name(path.name + ".before-shared")
    n = 1
    while aside.exists() or aside.is_symlink():
        n += 1
        aside = path.with_name(f"{path.name}.before-shared-{n}")
    return aside


def _merge_into(own: Path, shared: Path) -> None:
    """Move everything in `own` that `shared` lacks into `shared`, recursing
    into folders both have. What would clash stays behind in `own`."""
    for entry in list(own.iterdir()):
        target = shared / entry.name
        if entry.is_dir() and not entry.is_symlink() and target.is_dir():
            _merge_into(entry, target)
            if not any(entry.iterdir()):
                entry.rmdir()
        elif not (target.exists() or target.is_symlink()):
            shutil.move(str(entry), str(target))


class Profiles:
    """The account profiles, one config directory each. See the module note."""

    def __init__(self, data_dir: Path | None = None, main_dir: Path | None = None):
        self.data_dir = data_dir or DATA_DIR
        self.main_dir = main_dir or MAIN_CONFIG
        self.folder = self.data_dir / "profiles"
        self.file = self.data_dir / "profiles.json"
        self.logins: dict[str, Login] = {}
        self._status: dict[str, tuple[float, dict]] = {}
        self._lock = threading.Lock()
        self.usage_fetch = None  # set in tests; loaded from usage.py otherwise
        self._usage_polled: dict[str, float] = {}
        self._usage_retry: dict[str, float] = {}  # no check before this time
        self._usage_wait: dict[str, float] = {}  # the last backoff, doubled on repeat

    # --- the registry file -------------------------------------------------------

    def _read(self) -> dict:
        try:
            data = json.loads(self.file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        data.setdefault("active", DEFAULT_PROFILE)
        data.setdefault("usage", {})
        return data

    def _write(self, data: dict) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        tmp = self.file.with_name(".profiles.json.tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        tmp.replace(self.file)

    def names(self) -> list[str]:
        others = sorted(
            p.name
            for p in (self.folder.iterdir() if self.folder.is_dir() else [])
            if p.is_dir() and PROFILE_NAME.fullmatch(p.name)
        )
        return [DEFAULT_PROFILE, *others]

    def exists(self, name: str) -> bool:
        return name in self.names()

    def config_dir(self, name: str) -> Path | None:
        """None for the default profile: Claude Code's own directory."""
        if name == DEFAULT_PROFILE:
            return None
        return self.folder / name

    def env(self, name: str) -> dict:
        env = dict(os.environ)
        config = self.config_dir(name)
        if config is None:
            env.pop("CLAUDE_CONFIG_DIR", None)
        else:
            self.link_shared(name)
            env["CLAUDE_CONFIG_DIR"] = str(config)
        return env

    def link_shared(self, name: str) -> None:
        """Point a profile's instructions, skills, settings, plugins and
        projects (memory and transcripts) at the default profile's, so every
        account acts and knows the same; only the login stays its own.

        Whatever the profile had of its own is merged into the shared copy
        first. Anything that would overwrite is kept aside as
        <item>.before-shared, so nothing is lost.
        """
        config = self.config_dir(name)
        if config is None:
            return
        config.mkdir(parents=True, exist_ok=True)
        for item in SHARED_FILES + SHARED_DIRS:
            source = self.main_dir / item
            link = config / item
            if item in SHARED_DIRS:
                source.mkdir(parents=True, exist_ok=True)
            elif not source.exists():
                continue
            if link.is_symlink():
                if link.resolve() == source.resolve():
                    continue
                link.unlink()
            elif link.is_dir() and item in SHARED_DIRS:
                _merge_into(link, source)
                if any(link.iterdir()):
                    link.rename(_aside(link))
                else:
                    link.rmdir()
            elif link.exists():
                link.rename(_aside(link))
            link.symlink_to(source)

    def active(self) -> str:
        name = str(self._read().get("active") or DEFAULT_PROFILE)
        return name if self.exists(name) else DEFAULT_PROFILE

    def set_active(self, name: str) -> None:
        if not self.exists(name):
            raise ValueError("No such account")
        data = self._read()
        data["active"] = name
        self._write(data)

    def add(self, name: str) -> str:
        name = name.strip().lower()
        if not PROFILE_NAME.fullmatch(name):
            raise ValueError(
                "An account name is 1 to 32 characters: letters, digits, - or _"
            )
        if self.exists(name):
            raise ValueError("That account name is taken")
        (self.folder / name).mkdir(parents=True, exist_ok=True)
        self.link_shared(name)
        return name

    def remove(self, name: str) -> None:
        if name == DEFAULT_PROFILE:
            raise ValueError("The default account is Claude Code's own; keep it")
        if not self.exists(name):
            raise ValueError("No such account")
        login = self.logins.pop(name, None)
        if login:
            login.cancel()
        data = self._read()
        if data.get("active") == name:
            data["active"] = DEFAULT_PROFILE
        data["usage"].pop(name, None)
        self._write(data)
        shutil.rmtree(self.folder / name, ignore_errors=True)
        self._status.pop(name, None)

    # --- what the CLI says about each --------------------------------------------

    def status(self, name: str, refresh: bool = False) -> dict:
        """`claude auth status --json` for the profile, cached for a minute."""
        with self._lock:
            cached = self._status.get(name)
            if (
                cached
                and not refresh
                and time.time() - cached[0] < STATUS_CACHE_SECONDS
            ):
                return cached[1]
        cmd = claude_command()
        result: dict = {"logged_in": False, "email": "", "org": "", "plan": ""}
        if not cmd:
            result["error"] = "Claude Code is not installed"
        else:
            try:
                run = subprocess.run(
                    [*cmd, "auth", "status", "--json"],
                    env=self.env(name),
                    capture_output=True,
                    text=True,
                    timeout=20,
                )
                info = json.loads(run.stdout or "{}")
                result["logged_in"] = bool(info.get("loggedIn"))
                result["email"] = str(info.get("email") or "")
                result["org"] = str(info.get("orgName") or "")
                result["plan"] = str(info.get("subscriptionType") or "")
            except (OSError, ValueError, subprocess.SubprocessError) as e:
                result["error"] = f"Could not read the login state ({e})"
        with self._lock:
            self._status[name] = (time.time(), result)
        return result

    def forget_status(self, name: str) -> None:
        with self._lock:
            self._status.pop(name, None)

    def note_usage(self, name: str, info: dict) -> None:
        """The last rate_limit_event a conversation on this profile streamed,
        merged into what is stored. Most events carry a status and no numbers;
        replacing the stored usage with one wiped the bars until the next live
        check (Emerson, 2026-09-28: "the usage bars keep breaking"), so only
        the numbers an event really has are taken, and "seen" moves only then."""
        windows = info.get("unifiedWindows") or {}
        with self._lock:
            data = self._read()
            usage = dict(data["usage"].get(name) or {})
            if info.get("status"):
                usage["status"] = info["status"]
            fresh = False
            for key in ("five_hour", "seven_day"):
                window = windows.get(key) or {}
                used = window.get("utilization")
                if isinstance(used, (int, float)) and not isinstance(used, bool):
                    usage[key] = {
                        "used": used,
                        "resets_at": window.get("resetsAt"),
                        "seen": time.time(),
                    }
                    fresh = True
            kind = info.get("rateLimitType")
            if kind and not windows and info.get("resetsAt"):
                usage[str(kind)] = {
                    **(usage.get(str(kind)) or {}),
                    "resets_at": info["resetsAt"],
                }
            if fresh or "seen" not in usage:
                usage["seen"] = time.time()
                usage["source"] = "stream"
            data["usage"][name] = usage
            self._write(data)

    def poll_usage(self, name: str, wait: bool = False) -> bool:
        """Ask the account's real usage, at most every USAGE_EVERY seconds, in a
        thread so the page never waits. Terminal sessions on the same account
        use the same window, and the panel's own stream only sees its turns.
        Returns whether a check started. A failed check keeps the last numbers."""
        with self._lock:
            now = time.time()
            if now - self._usage_polled.get(name, 0) < USAGE_EVERY:
                return False
            if now < self._usage_retry.get(name, 0):
                return False
            self._usage_polled[name] = now
        if self.usage_fetch is None:
            self.usage_fetch = _usage_tool_fetch()
        fetch = self.usage_fetch
        if fetch is None:
            return False
        config = self.config_dir(name) or self.main_dir

        def run() -> None:
            try:
                live = usage_from_live(fetch(config))
            except Exception as e:  # offline, signed out, rate limited
                self._usage_failed(name, e)
                return
            with self._lock:
                self._usage_retry.pop(name, None)
                self._usage_wait.pop(name, None)
                data = self._read()
                # a window the answer lacks keeps its last numbers; the status
                # is the stream's; an older reading never replaces a newer one
                data["usage"][name] = merge_usage(data["usage"].get(name) or {}, live)
                self._write(data)

        if wait:
            run()
        else:
            threading.Thread(target=run, daemon=True).start()
        return True

    def _usage_failed(self, name: str, error: Exception) -> None:
        """Keep the last good numbers and say why they are old. When the
        endpoint answers 429 (checked too often, often by several sessions at
        once), wait as long as it asks, or twice the last wait, before the
        next check."""
        code = getattr(error, "code", None)
        if code == 429:
            try:
                wait = float(error.headers.get("Retry-After"))  # type: ignore[attr-defined]
            except (AttributeError, TypeError, ValueError):
                wait = self._usage_wait.get(name, USAGE_EVERY / 2) * 2
            wait = min(max(wait, USAGE_EVERY), USAGE_MAX_BACKOFF)
            text = "the usage check is busy (too many requests); trying again later"
        else:
            wait = 0
            text = f"could not check: {type(error).__name__}"
        with self._lock:
            if wait:
                self._usage_wait[name] = wait
                self._usage_retry[name] = time.time() + wait
            data = self._read()
            usage = data["usage"].setdefault(name, {})
            usage["check"] = {"at": time.time(), "error": text, "retry_in": wait}
            self._write(data)

    def describe(self) -> dict:
        """Everything the page shows: each profile with its login and usage."""
        for name in self.names():
            if (
                name == DEFAULT_PROFILE
                or (self.folder / name / ".credentials.json").is_file()
            ):
                self.poll_usage(name)
        data = self._read()
        active = self.active()
        profiles = []
        for name in self.names():
            login = self.logins.get(name)
            profiles.append(
                {
                    "name": name,
                    "default": name == DEFAULT_PROFILE,
                    "active": name == active,
                    "config_dir": str(self.config_dir(name) or Path.home() / ".claude"),
                    **self.status(name),
                    "usage": data["usage"].get(name),
                    "login": login.snapshot() if login else None,
                }
            )
        # Two profiles signed in to the same Claude account share one usage
        # meter, so the page says so instead of showing the numbers twice.
        first: dict[tuple[str, str], str] = {}
        for p in profiles:
            if p.get("logged_in") and p.get("email"):
                key = (str(p["email"]).lower(), str(p.get("org") or ""))
                if key in first:
                    p["same_as"] = first[key]
                else:
                    first[key] = p["name"]
        return {"active": active, "profiles": profiles}

    # --- signing in -----------------------------------------------------------------

    def login(self, name: str) -> Login:
        if not self.exists(name):
            raise ValueError("No such account")
        cmd = claude_command()
        if not cmd:
            raise RuntimeError("Claude Code (the claude command) is not installed")
        live = self.logins.get(name)
        if live and live.running():
            return live
        self.forget_status(name)
        login = Login(name, [*cmd, "auth", "login"], self.env(name), Path.home())
        self.logins[name] = login
        return login

    def login_state(self, name: str) -> dict | None:
        login = self.logins.get(name)
        if login is None:
            return None
        if login.state == "done":
            self.forget_status(name)
        return login.snapshot()

    def stop_all(self) -> None:
        for login in list(self.logins.values()):
            login.cancel()


class Conversation:
    def __init__(
        self,
        meta: dict,
        data_dir: Path | None = None,
        profiles: Profiles | None = None,
    ):
        self.data_dir = data_dir or DATA_DIR
        self.profiles = profiles or Profiles(self.data_dir)
        self.personas = personas.Personas(self.data_dir)
        self.meta = meta
        # requests run on parallel threads; one temp file each at a time
        self._save_lock = threading.Lock()
        self.meta.setdefault("profile", DEFAULT_PROFILE)
        self.events: list[dict] = []
        self.busy = False
        self._late_send = False  # a message was sent while a turn ran
        self._close_after_turn = False  # its tab closed while a turn ran
        self._events_seen = 0
        self.proc: subprocess.Popen | None = None
        self._cond = threading.Condition()
        # one writer at a time into the process, and stop/close/send never
        # interleave: a message can not land in a process being ended
        self._write = threading.Lock()
        # clear while a send is between writing a message and recording it
        self._recorded = threading.Event()
        self._recorded.set()
        # this backend run's id for the conversation: a page that read events
        # from an earlier run must reload them (seq numbers are not kept)
        self.boot = secrets.token_hex(6)
        self._load_history()
        self._recount_cost()

    # --- files -----------------------------------------------------------------

    @property
    def folder(self) -> Path:
        return self.data_dir / "conversations"

    @property
    def attachments(self) -> Path:
        return self.data_dir / "attachments" / self.meta["id"]

    def save_meta(self) -> None:
        self.folder.mkdir(parents=True, exist_ok=True)
        path = self.folder / f"{self.meta['id']}.json"
        tmp = path.with_name(f".{path.name}.tmp")
        text = json.dumps(self.snapshot(), indent=2)
        with self._save_lock:
            tmp.write_text(text, encoding="utf-8")
            tmp.replace(path)

    def snapshot(self) -> dict:
        """A copy of meta taken in one step. Other threads change meta while
        it is saved or sent to the page; the C JSON encoder (no indent) walks
        it without letting another Python thread run, so the copy is whole."""
        return json.loads(json.dumps(self.meta))

    def _load_history(self) -> None:
        path = self.folder / f"{self.meta['id']}.jsonl"
        if not path.is_file():
            return
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                event = json.loads(line)
            except ValueError:
                continue
            event["seq"] = len(self.events)
            self.events.append(event)

    def _record(self, event: dict) -> None:
        with self._cond:
            event["seq"] = len(self.events)
            self.events.append(event)
            if event.get("type") not in TRANSIENT:
                self.folder.mkdir(parents=True, exist_ok=True)
                stored = {k: v for k, v in event.items() if k != "seq"}
                with open(
                    self.folder / f"{self.meta['id']}.jsonl", "a", encoding="utf-8"
                ) as f:
                    f.write(json.dumps(stored) + "\n")
            self._cond.notify_all()

    def note_turn(self, result: dict) -> None:
        """How the last turn ended, for the Enjoy layout's "needs you"."""
        bad = bool(result.get("is_error")) or result.get("subtype") not in (
            None,
            "success",
        )
        self.meta["last_turn"] = {
            "at": time.time(),
            "ok": not bad,
            "denied": len(result.get("permission_denials") or []),
        }

    def mark_seen(self) -> None:
        self.meta["seen"] = time.time()
        self.save_meta()

    def save_attachment(self, name: str, data: bytes) -> Path:
        if len(data) > MAX_ATTACHMENT_BYTES:
            raise ValueError("That file is larger than 50 MB")
        self.attachments.mkdir(parents=True, exist_ok=True)
        target = self.attachments / safe_name(name)
        stem, suffix, n = target.stem, target.suffix, 1
        while target.exists():
            target = self.attachments / f"{stem} ({n}){suffix}"
            n += 1
        target.write_bytes(data)
        return target

    # --- the process --------------------------------------------------------------

    def running(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    @property
    def profile(self) -> str:
        name = str(self.meta.get("profile") or DEFAULT_PROFILE)
        return name if self.profiles.exists(name) else DEFAULT_PROFILE

    def _start(self) -> None:
        # a close meant for an earlier process (say one that crashed) is void
        self._close_after_turn = False
        if not claude_command():
            raise RuntimeError("Claude Code (the claude command) is not installed")
        state = self.profiles.status(self.profile)
        if not state.get("logged_in"):
            raise RuntimeError(
                f"The account '{self.profile}' is not signed in; sign in from the account picker or pick another"
            )
        cwd = Path(os.path.expanduser(self.meta.get("cwd") or "~"))
        if not cwd.is_dir():
            cwd = Path.home()
        self.attachments.mkdir(parents=True, exist_ok=True)
        cast = self.personas.prefs()["enabled"]
        args = command(
            self.meta,
            mcp_config(self.data_dir, conv_id=self.meta["id"]),
            self.attachments,
            self.personas.roster_prompt() if cast else "",
        )
        self.proc = subprocess.Popen(
            args,
            cwd=cwd,
            env=apply_limits(self.profiles.env(self.profile), self.meta),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            start_new_session=True,
        )
        proc = self.proc
        self.meta.pop("ultracode_state", None)
        if self.meta.get("ultracode") and proc.stdin is not None:
            # ask Claude Code whether ultracode really took effect
            probe = {"subtype": "get_settings"}
            try:
                proc.stdin.write(
                    json.dumps(
                        {
                            "type": "control_request",
                            "request_id": SETTINGS_PROBE,
                            "request": probe,
                        }
                    )
                    + "\n"
                )
                proc.stdin.flush()
            except (OSError, ValueError):
                pass  # it died at once; _read reports how
        stderr_tail: list[str] = []
        threading.Thread(
            target=self._drain_stderr, args=(proc, stderr_tail), daemon=True
        ).start()
        threading.Thread(
            target=self._read, args=(proc, stderr_tail), daemon=True
        ).start()

    @staticmethod
    def _drain_stderr(proc: subprocess.Popen, tail: list[str]) -> None:
        assert proc.stderr is not None
        for line in proc.stderr:
            tail.append(line.rstrip())
            del tail[:-20]

    def _read(self, proc: subprocess.Popen, stderr_tail: list[str]) -> None:
        assert proc.stdout is not None
        for line in proc.stdout:
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if not isinstance(event, dict):
                continue
            # a bounded wait: a stalled send never stalls the reader for long
            self._recorded.wait(2.0)
            if event.get("type") == "control_response":
                self._note_settings(event)
                continue
            if event.get("type") == "system" and event.get("subtype") == "init":
                self.meta["session_id"] = event.get("session_id") or self.meta.get(
                    "session_id"
                )
                self.meta["model_seen"] = event.get("model", "")
                self.save_meta()
            if event.get("type") == "rate_limit_event" and isinstance(
                event.get("rate_limit_info"), dict
            ):
                self.profiles.note_usage(self.profile, event["rate_limit_info"])
            self._events_seen += 1
            if not self.busy and event.get("type") in ("assistant", "stream_event"):
                self.busy = True  # a turn started by a message that landed late
            if event.get("type") == "result":
                # A turn ended; one ended by Forge stopping the process is
                # cut off, so the mark stays for the next start.
                if not getattr(proc, "forge_stopped", False):
                    self.meta.pop("working", None)
                self.note_turn(event)
                self._note_cost(event)
                self.meta["updated"] = time.time()
                self.save_meta()
                if self._late_send:
                    # A message sent during this turn was either folded into
                    # it or starts a turn of its own. Stay busy a moment; any
                    # event in that time means a second turn is running.
                    self._late_send = False
                    self._settle(self._events_seen)
                else:
                    self.busy = False
                    threading.Thread(target=self._after_turn, daemon=True).start()
            self._record(event)
        code = proc.wait()
        if self.proc is proc:
            was_busy = self.busy
            self.busy = False
            if not getattr(proc, "forge_stopped", False) and (code != 0 or was_busy):
                self.meta.pop("working", None)
                # a crashed turn is one that needs him (the Enjoy layout)
                self.meta["last_turn"] = {
                    "at": time.time(),
                    "ok": False,
                    "denied": 0,
                    "crashed": True,
                }
                self.save_meta()
                self._record(
                    {
                        "type": "forge_exit",
                        "code": code,
                        "stderr": "\n".join(stderr_tail[-8:]),
                    }
                )
            else:
                with self._cond:
                    self._cond.notify_all()

    def _note_cost(self, result: dict) -> None:
        """A result's total_cost_usd is the session's running total, not the
        turn's (Claude Code 2.1.289, checked live 2026-10-07: a /context turn
        repeated the /compact turn's figure, and a resumed process carried
        on from it). So meta keeps the latest total per session, and
        cost_usd is their sum. A figure summed before that fix stays in
        meta as "earlier" but is never shown: it was counted too high."""
        try:
            total = float(result.get("total_cost_usd") or 0)
        except (TypeError, ValueError):
            return
        if not math.isfinite(total):
            return
        sid = str(result.get("session_id") or self.meta.get("session_id") or "")
        costs = self.meta.get("session_costs")
        if not isinstance(costs, dict):
            costs = {}
            if self.meta.get("cost_usd"):
                costs[EARLIER_COST] = float(self.meta["cost_usd"])
        costs[sid] = max(float(costs.get(sid) or 0), total)
        self.meta["session_costs"] = costs
        self._recount_cost()

    def _recount_cost(self) -> None:
        """Redo an old overcounted figure from this conversation's own log.

        Every result event is on record with its session's running total, so
        the largest per session is what that session cost. (Claude Code's
        transcripts in ~/.claude/projects hold token counts but no cost.) A
        session with no result on record stays out; "earlier" is kept in
        meta, never deleted, and never counted."""
        costs = self.meta.get("session_costs")
        if not isinstance(costs, dict):
            return
        for event in self.events if EARLIER_COST in costs else ():
            if event.get("type") != "result" or not event.get("session_id"):
                continue
            try:
                total = float(event.get("total_cost_usd") or 0)
            except (TypeError, ValueError):
                continue
            if math.isfinite(total):
                sid = str(event["session_id"])
                costs[sid] = max(float(costs.get(sid) or 0), total)
        self.meta["cost_usd"] = round(
            sum(float(v or 0) for k, v in costs.items() if k != EARLIER_COST), 6
        )

    def _note_settings(self, event: dict) -> None:
        """The answer to the start's get_settings probe: is ultracode on?"""
        response = event.get("response") or {}
        if response.get("request_id") != SETTINGS_PROBE:
            return
        applied = (response.get("response") or {}).get("applied") or {}
        if response.get("subtype") != "success" or not isinstance(applied, dict):
            return
        self.meta["ultracode_state"] = {
            "active": bool(applied.get("ultracode")),
            "available": bool(applied.get("ultracodeAvailable")),
            "model": str(applied.get("model") or ""),
        }
        self.save_meta()

    def _settle(self, seen: int, grace: float = 1.0) -> None:
        """Clear busy after `grace` seconds unless new events arrived."""

        def check() -> None:
            if self._events_seen == seen and self.busy:
                self.busy = False
                with self._cond:
                    self._cond.notify_all()
                # No close or queued command from here: a second message may
                # have started a turn that has not said anything yet, and
                # ending the process would lose it. They wait for the next
                # real end of a turn (a result event).

        timer = threading.Timer(grace, check)
        timer.daemon = True
        timer.start()

    def _after_turn(self) -> None:
        """A turn is over. A command Claude queued for itself (panel_command)
        goes first, as the next message (any others wait for its turn to
        end); then a pending close or restart, which waits for that turn."""
        try:
            line = panel_commands.take_next(
                command_queue(self.data_dir, self.meta["id"])
            )
            if line:
                self._record({"type": "forge_asked", "command": line})
                try:
                    self.send(line, [])
                except (RuntimeError, OSError) as e:
                    self._record(
                        {"type": "forge_asked", "command": line, "error": str(e)}
                    )
        finally:
            if self._close_after_turn and not self.busy:
                self.close()

    def _write_line(self, line: str) -> None:
        if self.proc is None or self.proc.stdin is None:
            raise BrokenPipeError("no process")
        self.proc.stdin.write(line)
        self.proc.stdin.flush()

    def send(self, text: str, files: list[Path]) -> None:
        """Hand a message to Claude Code. Nothing is recorded until the
        process has really taken it, so a failed send leaves no bubble."""
        text = clean_text(text)
        # A slash command must reach Claude Code with "/" first, or it is
        # read as plain text: no persona tag in front of it, no spaces.
        slash = text.lstrip().startswith("/")
        if slash:
            text = text.strip()
        with self._write:
            if not self.running() or getattr(self.proc, "forge_stopped", False):
                self._start()
            tag, persona_event = "", None
            if not slash and self.personas.prefs()["enabled"]:
                persona, mood = self.personas.for_message(text)
                if persona:
                    tag = personas.Personas.tag(persona, mood)
                    persona_event = {
                        "type": "forge_persona",
                        "persona": persona.get("id"),
                        "name": persona.get("name"),
                        "mood": mood,
                    }
            line = json.dumps(user_message(tag + text, files)) + "\n"
            during = self.busy
            # Claude Code may answer before the message is recorded (a
            # /context reply is instant): _read holds its events until the
            # message is in the log, so the bubble comes first.
            self._recorded.clear()
            try:
                self._write_line(line)
            except (OSError, ValueError):
                # The process died under us (a broken pipe): start afresh
                # once; the message goes to the new process.
                self._stop_locked(quiet=True)
                during = False
                try:
                    self._start()
                except BaseException:
                    self._recorded.set()
                    raise
                try:
                    self._write_line(line)
                except (OSError, ValueError) as e:
                    self._recorded.set()
                    raise RuntimeError(
                        "Claude Code stopped taking messages; send it again"
                    ) from e
            if not self.meta.get("title"):
                self.meta["title"] = (text.strip().splitlines() or ["Files"])[0][
                    :60
                ] or "Files"
            self.meta["updated"] = time.time()
            self.meta.pop("archived", None)
            # A turn in progress, on disk: if Forge quits or the laptop goes
            # down before it ends, the next start carries it on
            # (Registry.resume_interrupted).
            self.meta["working"] = time.time()
            self.save_meta()
            if persona_event:
                self._record(persona_event)
            # Sent while Claude works: Claude Code adds it to the running turn.
            event = {
                "type": "forge_user",
                "text": text,
                "files": [p.name for p in files],
            }
            if during:
                event["during_turn"] = True
                self._late_send = True
            self._record(event)
            self.busy = True
            self._recorded.set()

    def stop(self, quiet: bool = False) -> bool:
        """End the process. The next message resumes the conversation."""
        with self._write:
            return self._stop_locked(quiet)

    def _stop_locked(self, quiet: bool) -> bool:
        proc = self.proc
        if proc is None or proc.poll() is not None:
            return False
        proc.forge_stopped = True  # type: ignore[attr-defined]
        for sig, wait in (
            (signal.SIGINT, 2.0),
            (signal.SIGTERM, 2.0),
            (signal.SIGKILL, 1.0),
        ):
            try:
                os.killpg(proc.pid, sig)
            except (ProcessLookupError, PermissionError):
                break
            try:
                proc.wait(timeout=wait)
                break
            except subprocess.TimeoutExpired:
                continue
        was_busy = self.busy
        self.busy = False
        if not quiet:
            # Stopped by the user: nothing to carry on after a restart.
            if self.meta.pop("working", None) is not None:
                self.save_meta()
            self._record({"type": "forge_stopped", "during_turn": was_busy})
        return True

    def close(self) -> bool:
        """Its tab was closed, or a setting changed: end the process, after
        the turn in progress if one is running (a message sent meanwhile
        keeps the mark: the process ends after that turn instead). Nothing
        carries on after a restart; the next message resumes the
        conversation."""
        with self._write:
            if self.busy:
                self._close_after_turn = True
                return False
            self._close_after_turn = False
            if self.meta.pop("working", None) is not None:
                self.save_meta()
            return self._stop_locked(quiet=True)

    def events_after(self, seq: int, wait: float = 0.0) -> list[dict]:
        """Events after `seq`, waiting up to `wait` seconds for the first. A
        wait that ends on a new event lingers BATCH_SECONDS more, so a reply
        streamed word by word reaches the page in a few batches instead of
        one round trip per word."""
        deadline = time.time() + wait
        with self._cond:
            if len(self.events) > seq + 1 or wait <= 0:
                return self.events[seq + 1 :]
            while len(self.events) <= seq + 1 and time.time() < deadline:
                self._cond.wait(max(0.0, deadline - time.time()))
            gather = min(deadline, time.time() + BATCH_SECONDS)
            while len(self.events) > seq + 1 and time.time() < gather:
                self._cond.wait(max(0.0, gather - time.time()))
            return self.events[seq + 1 :]


def _frontmatter(path: Path) -> dict[str, str]:
    """The simple `key: value` lines of a Markdown file's --- header, with
    folded (> or |) values joined onto one line."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return {}
    if not lines or lines[0].strip() != "---":
        return {}
    fields: dict[str, str] = {}
    key = ""
    for line in lines[1:]:
        if line.strip() == "---":
            break
        match = re.match(r"([\w-]+):\s*(.*)$", line)
        if match:
            key, value = match.group(1), match.group(2).strip()
            fields[key] = "" if value in (">", "|", ">-", "|-") else value
        elif key and line.startswith((" ", "\t")):
            fields[key] = (fields[key] + " " + line.strip()).strip()
    for key, value in fields.items():
        if len(value) > 1 and value[0] == value[-1] and value[0] in "\"'":
            fields[key] = value[1:-1]
    return fields


def scan_commands(main_dir: Path | None = None) -> dict[str, str]:
    """Skills and custom commands on disk, name -> one-line description,
    named the way Claude Code lists them: `skill`, `anthropic-skills:skill`
    for synced ones, `plugin:skill` and `plugin:command` for plugins. Every
    profile links these folders to the default config, so one scan serves
    all accounts."""
    main_dir = main_dir or MAIN_CONFIG
    found: dict[str, str] = {}

    def add(name: str, path: Path) -> None:
        info = _frontmatter(path)
        found.setdefault(name, info.get("description", ""))

    def skills(folder: Path, prefix: str) -> None:
        for path in sorted(folder.glob("*/SKILL.md")):
            add(prefix + (_frontmatter(path).get("name") or path.parent.name), path)

    def commands(folder: Path, prefix: str) -> None:
        for path in sorted(folder.glob("*.md")):
            add(prefix + path.stem, path)

    skills(main_dir / "skills", "")
    for bucket in sorted((main_dir / "skills" / "synced").glob("*/")):
        skills(bucket, "anthropic-skills:")
    commands(main_dir / "commands", "")
    try:
        installed = json.loads(
            (main_dir / "plugins" / "installed_plugins.json").read_text("utf-8")
        ).get("plugins", {})
    except (OSError, ValueError, AttributeError):
        installed = {}
    for key, installs in installed.items() if isinstance(installed, dict) else []:
        plugin = str(key).split("@")[0]
        for install in installs if isinstance(installs, list) else []:
            root = Path(str((install or {}).get("installPath") or ""))
            if not root.is_dir():
                continue
            # A plugin may list its skills (often nested in category folders)
            # in .claude-plugin/plugin.json; otherwise skills/<name>/SKILL.md.
            listed = _json_file(root / ".claude-plugin" / "plugin.json").get("skills")
            if isinstance(listed, list):
                for rel in listed:
                    path = root / str(rel) / "SKILL.md"
                    if path.is_file():
                        name = _frontmatter(path).get("name") or path.parent.name
                        add(plugin + ":" + name, path)
            else:
                skills(root / "skills", plugin + ":")
            commands(root / "commands", plugin + ":")
    return found


def _json_file(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _json_or_none(line: str):
    try:
        return json.loads(line)
    except ValueError:
        return None


class Registry:
    def __init__(self, data_dir: Path | None = None):
        self.data_dir = data_dir or DATA_DIR
        self.profiles = Profiles(self.data_dir)
        self.open: dict[str, Conversation] = {}
        self._lock = threading.Lock()
        self._focus: tuple[str, float] | None = None
        self.archive_hours = lambda: AUTO_ARCHIVE_HOURS
        self.resume_after_restart: Callable[[], bool] = lambda: True

    def find_session(self, session_id: str = "", pid: int = 0) -> dict | None:
        """The conversation running a Claude Code session, by its session id
        or the pid of its claude process."""
        for meta in self.list():
            live = self.open.get(meta["id"])
            proc = getattr(live, "proc", None)
            if (session_id and meta.get("session_id") == session_id) or (
                pid and proc is not None and proc.pid == pid
            ):
                return meta
        return None

    def ask_focus(self, conv_id: str) -> None:
        """Ask the page to open this conversation's tab (the Board's "Go to it")."""
        self._focus = (conv_id, time.time())

    def take_focus(self) -> str:
        """The conversation the page was asked to open, once, if asked in the
        last minute."""
        focus, self._focus = self._focus, None
        return focus[0] if focus and time.time() - focus[1] < 60 else ""

    def list(self) -> list[dict]:
        folder = self.data_dir / "conversations"
        metas = []
        for path in folder.glob("*.json") if folder.is_dir() else []:
            try:
                metas.append(json.loads(path.read_text(encoding="utf-8")))
            except ValueError:
                continue
        self._name_unnamed(metas)
        for meta in metas:
            live = self.open.get(meta["id"])
            meta["busy"] = bool(live and live.busy)
        self._archive_quiet(metas)
        return sorted(metas, key=lambda m: m.get("updated", 0), reverse=True)

    def _name_unnamed(self, metas: list[dict]) -> None:
        """Give conversations from before names existed one, oldest first, and
        save it so it never changes."""
        taken = [m["name"] for m in metas if m.get("name")]
        for meta in sorted(metas, key=lambda m: m.get("created", 0)):
            if meta.get("name"):
                continue
            meta["name"] = names.pick(meta["id"], taken)
            taken.append(meta["name"])
            self._store(meta, "name")

    def _store(self, meta: dict, key: str) -> None:
        """Write one field of a listed conversation to its file and to its
        open copy, so a later save from that copy keeps it."""
        live = self.open.get(meta["id"])
        if live is not None:
            live.meta[key] = meta[key]
        path = self.data_dir / "conversations" / f"{meta['id']}.json"
        try:
            stored = json.loads(path.read_text(encoding="utf-8"))
            stored[key] = meta[key]
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps(stored, indent=2), encoding="utf-8")
            tmp.replace(path)
        except (OSError, ValueError):
            pass

    def _archive_quiet(self, metas: list[dict]) -> None:
        """Move conversations in no folder to Archived once nothing has
        happened in them for archive_hours() (0 = never). A busy one stays;
        a message, a folder or the restore button brings one back."""
        hours = self.archive_hours()
        if hours <= 0:
            return
        now = time.time()
        for meta in metas:
            if meta.get("archived") or meta.get("folder") or meta.get("busy"):
                continue
            last = max(
                meta.get("updated") or 0,
                meta.get("created") or 0,
                meta.get("restored") or 0,
            )
            if now - last >= hours * 3600:
                meta["archived"] = now
                self._store(meta, "archived")

    def set_archived(self, conv_id: str, on: bool) -> None:
        """Archive a conversation by hand, or bring it back; brought back, it
        gets a fresh quiet window before it can go again."""
        conv = self.get(conv_id)
        if conv is None:
            raise ValueError("No such conversation")
        if on:
            conv.meta["archived"] = time.time()
        elif conv.meta.pop("archived", None):
            conv.meta["restored"] = time.time()
        conv.save_meta()

    def _init_commands(self) -> list[str]:
        """The slash commands and skills from the newest init event on record.

        Claude Code lists them every time a session starts; the newest
        conversation that has started one holds the freshest list.
        """
        for meta in self.list():
            live = self.open.get(meta["id"])
            if live is not None:
                events = reversed(live.events)
            else:
                path = self.data_dir / "conversations" / f"{meta['id']}.jsonl"
                try:
                    lines = path.read_text(encoding="utf-8").splitlines()
                except OSError:
                    continue
                events = (_json_or_none(line) for line in reversed(lines))
            for event in events:
                if (
                    isinstance(event, dict)
                    and event.get("type") == "system"
                    and event.get("subtype") == "init"
                    and isinstance(event.get("slash_commands"), list)
                ):
                    return [str(c) for c in event["slash_commands"]]
        return []

    def commands(self) -> list[dict]:
        """Everything the / menu offers: Claude Code's own list from its last
        init event (built-ins included), then any skill or command on disk it
        has not reported yet, each with its description where one exists."""
        described = scan_commands()
        names = self._init_commands()
        names += [n for n in described if n not in names]
        return [
            {"name": n, "description": described.get(n, "")}
            for n in names
            if not n.startswith("__")
        ]

    def create(
        self,
        cwd: str = "",
        model: str = "",
        mode: str = DEFAULT_MODE,
        profile: str = "",
        effort: str = "",
    ) -> Conversation:
        if not profile or not self.profiles.exists(profile):
            profile = self.profiles.active()
        conv_id = uuid.uuid4().hex[:12]
        meta = {
            "id": conv_id,
            "name": names.pick(conv_id, [m["name"] for m in self.list()]),
            "title": "",
            "cwd": cwd or str(Path.home()),
            "model": model if model in MODELS else "",
            "effort": effort if effort in EFFORTS else "",
            "mode": mode if mode in MODES else DEFAULT_MODE,
            "profile": profile,
            "session_id": "",
            "cost_usd": 0.0,
            "created": time.time(),
            "updated": time.time(),
        }
        conv = Conversation(meta, self.data_dir, self.profiles)
        conv.save_meta()
        with self._lock:
            self.open[meta["id"]] = conv
        return conv

    def get(self, conv_id: str) -> Conversation | None:
        if not re.fullmatch(r"[0-9a-f]{12}", conv_id or ""):
            return None
        with self._lock:
            if conv_id in self.open:
                return self.open[conv_id]
            path = self.data_dir / "conversations" / f"{conv_id}.json"
            if not path.is_file():
                return None
            conv = Conversation(
                json.loads(path.read_text(encoding="utf-8")),
                self.data_dir,
                self.profiles,
            )
            self.open[conv_id] = conv
            return conv

    def delete(self, conv_id: str) -> bool:
        conv = self.get(conv_id)
        if conv is None:
            return False
        conv.stop(quiet=True)
        with self._lock:
            self.open.pop(conv_id, None)
        for suffix in (".json", ".jsonl"):
            (self.data_dir / "conversations" / f"{conv_id}{suffix}").unlink(
                missing_ok=True
            )
        shutil.rmtree(conv.attachments, ignore_errors=True)
        return True

    # --- folders ------------------------------------------------------------------
    # A conversation's meta["folder"] names its folder ("" = none). The folder
    # list is kept in folders.json so an empty folder stays until deleted.

    def _folders_file(self) -> Path:
        return self.data_dir / "folders.json"

    def folders(self) -> list[dict]:
        try:
            data = json.loads(self._folders_file().read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = []
        rows = [f for f in data if isinstance(f, dict) and f.get("name")]
        known = {f["name"] for f in rows}
        for meta in self.list():  # a folder named by a conversation but not listed
            name = meta.get("folder") or ""
            if name and name not in known:
                rows.append({"name": name, "collapsed": False})
                known.add(name)
        return rows

    def set_folders(self, rows: list[dict]) -> None:
        """Save folder rows, extra fields included (the Enjoy layout keeps a
        project's id, working folder and workflows on its folder's row)."""
        self._save_folders([r for r in rows if isinstance(r, dict) and r.get("name")])

    def _save_folders(self, rows: list[dict]) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        tmp = self._folders_file().with_name(".folders.json.tmp")
        tmp.write_text(json.dumps(rows, indent=2), encoding="utf-8")
        tmp.replace(self._folders_file())

    @staticmethod
    def folder_name(name: str) -> str:
        name = " ".join(str(name or "").split())
        if not 1 <= len(name) <= 40:
            raise ValueError("A folder name is 1 to 40 characters")
        return name

    def add_folder(self, name: str) -> list[dict]:
        name = self.folder_name(name)
        rows = self.folders()
        if any(f["name"].lower() == name.lower() for f in rows):
            raise ValueError("There is already a folder with that name")
        rows.append({"name": name, "collapsed": False})
        self._save_folders(rows)
        return rows

    def _refile(self, old: str, new: str) -> None:
        for meta in self.list():
            if (meta.get("folder") or "") == old:
                conv = self.get(meta["id"])
                if conv is not None:
                    conv.meta["folder"] = new
                    conv.save_meta()

    def update_folder(
        self, name: str, new_name: str | None = None, collapsed: bool | None = None
    ) -> list[dict]:
        rows = self.folders()
        row = next((f for f in rows if f["name"] == name), None)
        if row is None:
            raise ValueError("No such folder")
        if new_name is not None and new_name != name:
            new_name = self.folder_name(new_name)
            if any(
                f is not row and f["name"].lower() == new_name.lower() for f in rows
            ):
                raise ValueError("There is already a folder with that name")
            self._refile(name, new_name)
            row["name"] = new_name
        if collapsed is not None:
            row["collapsed"] = bool(collapsed)
        self._save_folders(rows)
        return rows

    def delete_folder(self, name: str) -> list[dict]:
        """The folder goes; its conversations stay, moved out of any folder."""
        rows = self.folders()
        if not any(f["name"] == name for f in rows):
            raise ValueError("No such folder")
        self._refile(name, "")
        rows = [f for f in rows if f["name"] != name]
        self._save_folders(rows)
        return rows

    def file_into(self, conv_id: str, folder: str) -> None:
        conv = self.get(conv_id)
        if conv is None:
            raise ValueError("No such conversation")
        if folder and folder not in {f["name"] for f in self.folders()}:
            raise ValueError("No such folder")
        conv.meta["folder"] = folder
        if folder and conv.meta.pop("archived", None):
            conv.meta["restored"] = time.time()
        conv.save_meta()

    def resume_interrupted(self, gap: float = 20.0, wait: bool = False) -> list[str]:
        """Carry on the conversations whose turn was cut off by Forge quitting
        or the laptop going down (marked "working" on disk), oldest first and
        `gap` seconds apart, so a reboot doesn't start every session at once
        on a cold cache. Off in Settings, they stay marked and wait for a
        message. Returns the ids it resumes; runs on a thread unless `wait`."""
        if not self.resume_after_restart():
            return []
        metas = [m for m in self.list() if m.get("working") and m.get("session_id")]
        metas.sort(key=lambda m: m.get("working") or 0)
        ids = [m["id"] for m in metas]

        def run() -> None:
            for i, conv_id in enumerate(ids):
                if i and gap:
                    time.sleep(gap)
                conv = self.get(conv_id)
                if conv is None or conv.running():
                    continue
                conv._record({"type": "forge_resumed"})
                try:
                    conv.send(RESUME_MESSAGE, [])
                except (OSError, RuntimeError) as e:
                    conv._record({"type": "forge_exit", "code": -1, "stderr": str(e)})

        if wait:
            run()
        else:
            threading.Thread(target=run, daemon=True, name="resume").start()
        return ids

    def stop_all(self) -> None:
        for conv in list(self.open.values()):
            conv.stop(quiet=True)
        self.profiles.stop_all()
