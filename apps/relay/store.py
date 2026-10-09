"""Where Relay keeps everything: one data folder of plain files.

The boss and the page share these files and nothing else, so a crash, a reboot
or a restart of either loses nothing. Layout (RELAY_DATA_DIR overrides it):

    settings.json      Emerson's settings (defaults below fill the gaps)
    state.json         the boss's own bookkeeping (launch times, mail cursor...)
    events.jsonl       the event log, newest last
    heartbeat          touched by the boss every tick
    poke               touched by the page so the boss ticks straight away
    goals/<slug>.md    one goal each
    tasks/<goal>/<nnnn>-<slug>.md   one task each; loose tasks use goal "inbox"
    runs/<session id>/ one Claude session each: run.json, prompt.md,
                       output.jsonl, stderr.log
    outbox/            WhatsApp messages sessions queued (relay reply), sent
                       and removed by the boss
    secrets/           mode 700; the mail app password, mode 600
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

DEFAULTS: dict = {
    "max_sessions": 2,
    "paused": False,
    "default_folder": str(Path.home()),
    "model": "",
    # Emerson's pacing rule (memories usage-pacing-rule and
    # stop-at-95-percent-of-usage-limit).
    "slow_at": 70,
    "slow_gap_minutes": 15,
    "no_new_at": 92,
    "hand_over_at": 95,
    "weekly_stop_at": 99,
    # One account's own lines over the four above (Emerson, 2026-10-07: "hey,
    # ignoring the usage window unless it is actually 100 percent"; the sane
    # version: no 15-minute spacing, new launches up to 95, hand over at 98).
    # move_at (Emerson, 2026-10-08: hey is the Pro plan, default the 20x one;
    # "when it gets to 80 percent hand off to the default account"): past it
    # an account takes no new launches and its sessions hand over, but only
    # while another account has room; with none, it carries on to hand_over_at.
    "account_limits": {
        "hey": {"slow_at": 101, "no_new_at": 95, "hand_over_at": 98, "move_at": 80}
    },
    # Where an account's work goes when it runs out (Emerson, 2026-10-09: "when
    # hey runs out, switch to default by itself"). A task pinned to an account
    # that is out (its 5-hour or weekly line, or a usage-limit hit) launches
    # on the first of these with room; moves and hand-overs prefer it too.
    # A name or a list; chains follow (add "default": "second" for a third).
    "account_fallback": {"hey": "default"},
    "warm_minutes": 60,
    "stall_minutes": 20,
    "max_fails": 2,
    # Sessions without finishing (Emerson, 2026-10-08, replacing the old
    # max_rounds park): after review_after_rounds sessions a short fresh
    # review session (review.py) reads the task's State, commits and session
    # notes and decides whether it carries on or parks; then the same check
    # every review_every_rounds sessions (25, 35, 45...). No hard cap.
    # review_after_rounds 0: no reviews; review_every_rounds 0: only the first.
    "review_after_rounds": 25,
    "review_every_rounds": 10,
    "review_model": "opus",
    "review_effort": "medium",
    # Context (2026-10-06): every turn resends the whole context, so a long
    # session costs more per step. Past hand_over_context_k thousand tokens a
    # session writes its State and a fresh one carries on; a session that ends
    # with "continue" is only resumed while its context is under
    # resume_max_context_k (resuming reloads all of it).
    "hand_over_context_k": 170,
    "resume_max_context_k": 80,
    # A session close to finishing says so with `relay finishing` (Emerson,
    # 2026-10-08): for this many minutes after that it is not handed over for
    # its context size, so it finishes where it is. The usage hand-over
    # (hand_over_at) still applies.
    "finishing_minutes": 45,
    # Launches on one account at least this far apart, even with room, so a
    # meter reset does not start the whole queue in the same second.
    "launch_gap_minutes": 3,
    "check_timeout": 900,
    # Machine checks before a launch.
    "min_free_gb": 5,
    "max_load_per_cpu": 0.85,
    "busy_jan_cpu": 150,
    "wait_for_renders": True,
    # Mail. The Relay mailbox is the spare Gmail; the allowed senders are
    # Emerson's own addresses (his Outlook one first). Reports go to
    # report_to, or to the first allowed sender when that is blank.
    "mail_enabled": False,
    "mail_address": "",
    "allowed_senders": [],
    "report_to": "",
    "imap_host": "imap.gmail.com",
    "imap_port": 993,
    "smtp_host": "smtp.gmail.com",
    "smtp_port": 465,
    "trusted_authserv": "mx.google.com",
    "poll_minutes": 2,
    "digest_time": "17:00",
    "mail_on_start": False,
    "board": "forge",
    # WhatsApp: Relay's own hidden Whatsie (profile "relay") with its DevTools
    # port; one chat is the message board. See channels/whatsapp.py.
    "whatsapp_enabled": False,
    "whatsapp_chat": "",
    "whatsapp_port": 9333,
    "whatsapp_profile": "relay",
    "whatsapp_poll_seconds": 15,
    # After each message from Emerson: look every 2 s for 5 minutes, then
    # back to whatsapp_poll_seconds (Emerson, 2026-10-08). 0 minutes: off.
    "whatsapp_fast_seconds": 2,
    "whatsapp_fast_minutes": 5,
    "whatsapp_notify": "mine",
    "whatsapp_autostart": True,
    # The running chat log and the tidy-up (chatlog.py, Emerson 2026-10-07).
    "whatsapp_log_minutes": 10,
    "whatsapp_tidy": True,  # summarise old stretches by itself
    "whatsapp_tidy_minutes": 60,
    "whatsapp_tidy_keep": 30,
    "whatsapp_tidy_least": 15,
    "whatsapp_tidy_delete": True,  # false: post the summary, delete nothing
    # Chat mode (2026-10-06, see chat.py): plain messages go to one standing
    # chat task on a cheap model; real work to one work task on opus. The chat
    # resumes its Claude session while its context is under
    # whatsapp_chat_context_k thousand tokens, else starts fresh from State.
    "whatsapp_chat_task": 0,
    "whatsapp_work_task": 0,
    # "jan": a local Jan model answers first and hands off (frontdesk.py).
    "whatsapp_frontdesk": "off",  # or "local": localchat.py answers all
    # "auto": the local chat stands in while the Claude chat has no usage.
    "whatsapp_fallback": "auto",
    "local_thinking": "off",  # localchat: off, on, or auto (hard questions only)
    "whatsapp_chat_model": "haiku",  # Haiku 5.5: see chat.LIGHT
    "whatsapp_chat_effort": "low",
    "whatsapp_chat_context_k": 40,
    "whatsapp_work_model": "opus",
    "whatsapp_work_effort": "high",
    # The boss line (bossline.py): one lean Claude turn per question.
    "boss_line_model": "opus",
    "boss_line_effort": "low",
    # Files to send are copied here: the Whatsie flatpak can read Downloads.
    "whatsapp_files_dir": str(Path.home() / "Downloads" / "relay-outbox"),
    # Long messages are split into parts of this many characters, at most
    # whatsapp_max_parts. Emerson wants one message per answer (2026-10-07
    # 09:15), so only a very long one splits; WhatsApp folds anything past a
    # screenful behind "Read more" on the phone, one tap.
    "whatsapp_part_chars": 4000,
    "whatsapp_max_parts": 4,
}


CREW = Path.home() / ".claude" / "skills" / "crew" / "crew.py"

# Model names Relay passes to `claude --model` as a full id. Claude Code's own
# "haiku" alias still meant Haiku 4.5 on 2026-10-08; Relay's "haiku" is 5.5
# (checked live: claude-haiku-5-5 answers; the CLI only warns
# "unrecognized_model" because its table predates it). Relay task 99.
MODEL_IDS = {"haiku": "claude-haiku-5-5"}


def model_id(name: str) -> str:
    """The id to launch for a model name ("haiku" -> "claude-haiku-5-5")."""
    return MODEL_IDS.get((name or "").strip().lower(), name)


REAL_DIR = Path.home() / ".local" / "share" / "forge" / "relay"


def data_dir() -> Path:
    """RELAY_DATA_DIR, else the real folder. Never the real one under pytest:
    a scratch test that borrowed tests/test_boss.py's fixture without
    tests/conftest.py once wrote its tmp folder into the real settings and the
    WhatsApp chat could not launch for 20 minutes (Relay task 105)."""
    given = os.environ.get("RELAY_DATA_DIR")
    if given:
        return Path(given)
    if "pytest" in sys.modules or "PYTEST_CURRENT_TEST" in os.environ:
        raise RuntimeError(
            "Relay's real data folder is off limits to tests: set RELAY_DATA_DIR "
            "(apps/relay/tests/conftest.py does it for every test there)"
        )
    return REAL_DIR


def path(*parts: str) -> Path:
    return data_dir().joinpath(*parts)


def ensure() -> None:
    for sub in ("goals", "tasks/inbox", "runs"):
        path(sub).mkdir(parents=True, exist_ok=True)
    secrets = path("secrets")
    secrets.mkdir(parents=True, exist_ok=True)
    secrets.chmod(0o700)


def read_json(file: Path, default=None):
    try:
        with open(file, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return default


def write_json(file: Path, data) -> None:
    write_text(file, json.dumps(data, indent=2))


def write_text(file: Path, text: str) -> None:
    file.parent.mkdir(parents=True, exist_ok=True)
    tmp = file.with_name(f".{file.name}.{os.getpid()}.tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(file)


def settings() -> dict:
    saved = read_json(path("settings.json"), {}) or {}
    return {**DEFAULTS, **{k: v for k, v in saved.items() if k in DEFAULTS}}


def save_settings(changes: dict) -> dict:
    saved = read_json(path("settings.json"), {}) or {}
    for key, value in changes.items():
        if key not in DEFAULTS:
            raise ValueError(f"Unknown setting: {key}")
        default = DEFAULTS[key]
        if isinstance(default, bool):
            value = bool(value)
        elif isinstance(default, int):
            value = int(value)
        elif isinstance(default, float):
            value = float(value)
        elif isinstance(default, dict):
            value = json.loads(value) if isinstance(value, str) else dict(value)
        elif isinstance(default, list):
            if isinstance(value, str):
                value = [v.strip() for v in value.replace(";", ",").split(",")]
            value = [str(v).strip() for v in value if str(v).strip()]
        else:
            value = str(value).strip()
        saved[key] = value
    write_json(path("settings.json"), saved)
    return settings()


def state() -> dict:
    return read_json(path("state.json"), {}) or {}


def save_state(data: dict) -> None:
    write_json(path("state.json"), data)


def event(kind: str, text: str, **extra) -> dict:
    record = {"at": time.time(), "kind": kind, "text": text, **extra}
    file = path("events.jsonl")
    file.parent.mkdir(parents=True, exist_ok=True)
    with open(file, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record) + "\n")
    return record


def events(limit: int = 100) -> list[dict]:
    try:
        with open(path("events.jsonl"), "rb") as fh:
            fh.seek(0, os.SEEK_END)
            fh.seek(max(0, fh.tell() - 200_000))
            raw = fh.read().decode("utf-8", "replace").splitlines()
    except OSError:
        return []
    out = []
    for line in raw[-limit:]:
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


def secret(name: str) -> str:
    try:
        return path("secrets", name).read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def save_secret(name: str, value: str) -> None:
    ensure()
    file = path("secrets", name)
    fd = os.open(file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(value.strip())
    file.chmod(0o600)


def poke() -> None:
    file = path("poke")
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(str(time.time()))
