"""Forge voice: the shared client, text helpers and hotkey CLI (stdlib only).

Every app talks to the Voice app (apps/voice, http://127.0.0.1:8467), the one
process that loads speech models, through this file; the global hotkey runs it
as a command:

    python3 ~/Forge/shared/forge_voice.py tap        # GNOME: press = tap
    python3 ~/Forge/shared/forge_voice.py down|up    # Hyprland: hold to talk
    python3 ~/Forge/shared/forge_voice.py hush|status|say "text"
    python3 ~/Forge/shared/forge_voice.py say --model breeze-tts-2 \
        --voice 86-lena-en "[worried] Can everyone hear me?"
    python3 ~/Forge/shared/forge_voice.py clip "text" --out note.ogg \
        [--model M --voice V]    # a file, not the speakers (relay send-file it)
    python3 ~/Forge/shared/forge_voice.py install-hotkey [--dry-run]

Text helpers shared by the Voice app and the apps that speak:

- speech_text(markdown): what a voice should say (no code, links, tables).
- clean_heard(transcript): drops whisper noise tags, known hallucinations,
  leading fillers, and turns number words into digits where a command needs
  them ("volume forty" -> "volume 40").
- split_target(text): a leading wake name picks who answers ("Claude, ..." or
  "Jan, ..."); the names and their mishearings live in voice_registry.json.
- is_control(text): stop / cancel / repeat, handled by the Voice app itself.

Model rows, defaults and wake names: shared/voice_registry.json.
"""

from __future__ import annotations

import argparse
import ast
import fcntl
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable

HERE = Path(__file__).resolve().parent
FORGE = HERE.parent
REGISTRY = HERE / "voice_registry.json"
APP_DIR = FORGE / "apps" / "voice"
HEADERS = {"X-Forge": "1"}

# ----------------------------------------------------------------- registry


def load_registry(path: Path = REGISTRY) -> dict[str, Any]:
    """The voice registry, or an empty one when the file is missing."""
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {"models": [], "defaults": {}, "wake": {}}


def models_home() -> Path:
    """The shared model home (FORGE_MODELS_DIR, default ~/Forge/models)."""
    return Path(os.environ.get("FORGE_MODELS_DIR") or FORGE / "models")


def model_row(model_id: str, registry: dict[str, Any] | None = None) -> dict | None:
    reg = registry if registry is not None else load_registry()
    return next((m for m in reg.get("models", []) if m.get("id") == model_id), None)


# ------------------------------------------------------------- speech text

_CODE_BLOCK = re.compile(r"```.*?(?:```|\Z)", re.S)
_INLINE_CODE = re.compile(r"`([^`\n]*)`")
_IMAGE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_LINK = re.compile(r"\[([^\]]+)\]\([^)]*\)")
_URL = re.compile(r"https?://([^/\s)]+)\S*")
_HTML = re.compile(r"</?[a-zA-Z][^>]*>")
_TABLE_ROW = re.compile(r"^\s*\|.*\|\s*$|^\s*:?-{3,}:?(\s*\|\s*:?-{3,}:?)+\s*$")
_HEADING = re.compile(r"^\s{0,3}#{1,6}\s*")
_BULLET = re.compile(r"^\s*(?:[-*+•]|\d{1,3}[.)])\s+")
_EMPHASIS = re.compile(r"(\*\*|__|~~|\*|_)(?=\S)(.+?)(?<=\S)\1")
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


def speech_text(text: str, max_sentences: int = 0, max_chars: int = 1500) -> str:
    """Markdown in, plain sentences out: what a voice should actually say.

    Code blocks become one "The code is on screen." note, tables are dropped,
    links keep their words, bare URLs become "a link to <site>", list items
    become sentences. max_sentences 0 means no sentence limit; max_chars cuts
    at the last sentence end before the limit.
    """
    if not text:
        return ""
    had_code = bool(_CODE_BLOCK.search(text))
    text = _CODE_BLOCK.sub("\n", text)
    lines = []
    for line in text.splitlines():
        if _TABLE_ROW.match(line):
            continue
        line = _HEADING.sub("", line)
        line = _BULLET.sub("", line)
        line = _IMAGE.sub("", line)
        line = _LINK.sub(r"\1", line)
        line = _URL.sub(lambda m: "a link to " + m.group(1).removeprefix("www."), line)
        line = _INLINE_CODE.sub(r"\1", line)
        line = _HTML.sub("", line)
        for _ in range(2):
            line = _EMPHASIS.sub(r"\2", line)
        line = line.strip()
        if not line:
            continue
        if line[-1] not in ".!?:;,":
            line += "."
        lines.append(line)
    out = re.sub(r"\s+", " ", " ".join(lines)).strip()
    out = re.sub(r"\s+([.,!?;:])", r"\1", out)
    out = re.sub(r"([.!?])\.+", r"\1", out)
    if had_code:
        out = (out + " The code is on screen.").strip()
    if max_sentences > 0:
        out = " ".join(_SENTENCE_END.split(out)[:max_sentences])
    if max_chars and len(out) > max_chars:
        cut = out[:max_chars]
        end = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "))
        out = cut[: end + 1] if end > max_chars // 3 else cut.rsplit(" ", 1)[0] + "..."
    return out


# ------------------------------------------------------------- heard text

_NOISE = re.compile(
    r"\[[^\]]*\]|\((?:[^)]*?)(?:music|applause|laugh|noise|silence|blank|inaudible|sigh)[^)]*\)|\*[^*]{1,30}\*",
    re.I,
)
_FILLER = re.compile(r"^(?:(?:um+|uh+|uhm+|erm*|hmm+|mm+|ah+|oh)\b[\s,.]*)+", re.I)
_INNER_FILLER = re.compile(r"(?<=[\s,])(?:um+|uh+|uhm+|erm+)[,.]?\s+", re.I)
# Whole transcripts whisper invents from silence or noise.
HALLUCINATIONS = {
    "you",
    "thank you",
    "thanks",
    "thanks for watching",
    "thank you for watching",
    "thank you so much for watching",
    "please subscribe",
    "bye",
    "subtitles by the amara org community",
    "",
}
_UNITS = "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen".split()
_TENS = "twenty thirty forty fifty sixty seventy eighty ninety".split()
_NUMBER_WORDS = re.compile(
    r"\b(?:(?P<tens>"
    + "|".join(_TENS)
    + r")(?:[\s-](?P<unit>"
    + "|".join(_UNITS[1:10])
    + r"))?"
    r"|(?P<teen>" + "|".join(_UNITS[10:]) + r")"
    r"|(?P<hundred>(?:a|one) hundred))\b",
    re.I,
)
# Small numbers (zero to nine) only become digits next to a word that wants one.
_SMALL_NUMBER = re.compile(
    r"\b(?P<before>volume|brightness|level|to|at|by|workspace|tab|number|desktop)\s+(?P<n>"
    + "|".join(_UNITS[:10])
    + r")\b|\b(?P<n2>"
    + "|".join(_UNITS[:10])
    + r")\s+(?P<after>percent|minutes?|seconds?|hours?)\b",
    re.I,
)


def words_to_numbers(text: str) -> str:
    """'volume forty five' -> 'volume 45'; 'a hundred percent' -> '100 percent'.

    Tens, teens and a hundred always convert; zero to nine only next to a word
    that takes a number (so 'open one note' stays as it is).
    """

    def big(m: re.Match) -> str:
        if m.group("hundred"):
            return "100"
        if m.group("teen"):
            return str(_UNITS.index(m.group("teen").lower()))
        value = (_TENS.index(m.group("tens").lower()) + 2) * 10
        if m.group("unit"):
            value += _UNITS.index(m.group("unit").lower())
        return str(value)

    def small(m: re.Match) -> str:
        if m.group("n"):
            return f"{m.group('before')} {_UNITS.index(m.group('n').lower())}"
        return f"{_UNITS.index(m.group('n2').lower())} {m.group('after')}"

    return _SMALL_NUMBER.sub(small, _NUMBER_WORDS.sub(big, text))


def _norm(text: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9 ]+", " ", text.lower().replace("'", "")).split())


def clean_heard(text: str) -> str:
    """A transcript made ready for routing; '' when it was only noise."""
    text = _NOISE.sub(" ", text or "")
    text = re.sub(r"\s+", " ", text).strip()
    sentences = [p for p in re.split(r"(?<=[.!?])\s+", text) if _norm(p)]
    if all(_norm(p) in HALLUCINATIONS for p in sentences):
        return ""  # also "Thank you. Thank you." from a silent recording
    text = _FILLER.sub("", text)
    text = _INNER_FILLER.sub("", text)
    text = words_to_numbers(text).strip(" ,")
    return text[:1].upper() + text[1:] if text else ""


def split_target(
    text: str, wake: dict[str, list[str]] | None = None
) -> tuple[str, str]:
    """('claude' | 'jan' | '', rest): a leading wake name picks who answers.

    'Hey Claude, what's on my calendar' -> ('claude', "what's on my calendar").
    No wake name -> ('', text): the caller picks commands or the default brain.
    """
    wake_map = wake if wake is not None else (load_registry().get("wake") or {})
    stripped = text.strip()
    low = stripped.lower()
    greet = re.match(r"(?:hey|hi|hello|okay|ok|yo|oi)\b[\s,.!]*", low)
    start = greet.end() if greet else 0
    names = sorted(
        (
            (name.lower(), target)
            for target, names in wake_map.items()
            for name in names
        ),
        key=lambda pair: -len(pair[0]),
    )
    for name, target in names:
        end = start + len(name)
        if low.startswith(name, start) and (end == len(low) or not low[end].isalnum()):
            return target, stripped[end:].lstrip(" ,.:;!?-")
    return "", stripped


_CONTROLS = {
    "stop": {
        "stop",
        "stop it",
        "stop talking",
        "quiet",
        "be quiet",
        "hush",
        "shush",
        "shut up",
        "silence",
        "enough",
        "thats enough",
        "ok stop",
        "okay stop",
    },
    "cancel": {
        "cancel",
        "never mind",
        "nevermind",
        "forget it",
        "forget that",
        "ignore that",
    },
    "repeat": {
        "say that again",
        "say it again",
        "repeat",
        "repeat that",
        "what did you say",
        "come again",
        "again",
        "pardon",
    },
}


def is_control(text: str) -> str | None:
    """'stop' | 'cancel' | 'repeat' when the whole utterance is a control word."""
    said = _norm(text)
    return next((kind for kind, words in _CONTROLS.items() if said in words), None)


# ------------------------------------------------------------------ client


def base_url() -> str:
    return os.environ.get("FORGE_VOICE_URL", "http://127.0.0.1:8467").rstrip("/")


def _request(
    method: str,
    path: str,
    body: Any = None,
    content_type: str = "application/json",
    timeout: float = 5.0,
) -> tuple[int, bytes, dict[str, str]]:
    """(status, body, headers in lower case) from the Voice app; status 0 when
    it is not reachable."""
    data = body
    if isinstance(body, (dict, list)):
        data = json.dumps(body).encode()
    headers = dict(HEADERS)
    if data is not None:
        headers["Content-Type"] = content_type
    req = urllib.request.Request(
        base_url() + path, data=data, method=method, headers=headers
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            head = {k.lower(): v for k, v in resp.headers.items()}
            return resp.status, resp.read(), head
    except urllib.error.HTTPError as err:
        return err.code, err.read(), {}
    except (urllib.error.URLError, OSError, TimeoutError):
        return 0, b"", {}


def _call(
    method: str,
    path: str,
    body: Any = None,
    content_type: str = "application/json",
    timeout: float = 5.0,
) -> tuple[int, bytes]:
    """(status, body) from the Voice app; status 0 when it is not reachable."""
    code, raw, _ = _request(method, path, body, content_type, timeout)
    return code, raw


def _json(raw: bytes) -> dict:
    try:
        value = json.loads(raw or b"{}")
    except ValueError:
        return {}
    return value if isinstance(value, dict) else {}


def status() -> dict | None:
    """The Voice app's status, or None when it is not running."""
    code, raw = _call("GET", "/api/status", timeout=1.5)
    return _json(raw) if code == 200 else None


def _why(code: int, answer: dict) -> str:
    if code == 0:
        return "the Voice app did not answer in time, or is not running"
    return str(answer.get("detail") or answer.get("error") or f"HTTP {code}")


def say_report(
    text: str, app: str = "anywhere", timeout: float = 600.0, **options: Any
) -> dict:
    """Speak on the laptop's speakers (queued) and say how it went: {"ok":
    True, "model", "voice", "fell_back"} (fell_back: why another voice speaks
    it) or {"ok": False, "error"}. The line is made before it is queued, which
    takes minutes when a cloning voice has to load first."""
    body = {"text": text, "app": app, **options}
    code, raw = _call("POST", "/api/say", body, timeout=timeout)
    answer = _json(raw)
    if code == 200:
        return dict(answer, ok=True)
    return {"ok": False, "error": _why(code, answer)}


def say(
    text: str, app: str = "anywhere", timeout: float = 60.0, **options: Any
) -> bool:
    """Speak on the laptop's speakers (queued); True when accepted."""
    return say_report(text, app, timeout, **options)["ok"]


def not_asked(asked: dict, got: dict) -> str | None:
    """Why a line did not come from the asked model and voice, or None."""
    if got.get("fell_back"):
        return f"{got.get('model')} ({got.get('voice')}) speaks it instead: {got['fell_back']}"
    want = [(k, str(asked[k])) for k in ("model", "voice") if asked.get(k)]
    if any(v != got.get(k) for k, v in want):
        names = " ".join(v for _, v in want)
        return f"{got.get('model')} ({got.get('voice')}) spoke it, not {names}"
    return None


def clip(
    text: str,
    out: Path | str,
    app: str | None = None,
    timeout: float = 600.0,
    overwrite: bool = False,
    any_voice: bool = False,
    **options: Any,
) -> dict:
    """Save the line as a sound file instead of playing it: .wav as made, any
    other suffix through ffmpeg (.ogg is Opus, what WhatsApp voice notes use).
    {"ok": True, "path", "seconds", "model", "voice", "fell_back"} or {"ok":
    False, "error"}. A file already there is kept unless overwrite, and a line
    another model or voice made (a fall-back) is not saved unless any_voice:
    a note sent as Lena must be Lena."""
    path = Path(out).expanduser()
    if path.exists() and not overwrite:
        return {"ok": False, "error": f"{path} already exists"}
    body = {"text": text, **({"app": app} if app else {}), **options}
    code, raw, head = _request("POST", "/api/tts", body, timeout=timeout)
    if code != 200:
        return {"ok": False, "error": _why(code, _json(raw))}
    got = {
        k: head.get(f"x-voice-{k.replace('_', '-')}")
        for k in ("model", "voice", "fell_back")
    }
    why = not_asked(options, got)
    if why and not any_voice:
        return {"ok": False, "error": f"{why}; nothing saved (--any-voice keeps it)"}
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix.lower() == ".wav":
        path.write_bytes(raw)
    else:
        opus = path.suffix.lower() in (".ogg", ".opus")
        codec = ["-c:a", "libopus", "-b:a", "32k"] if opus else []
        cmd = ["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", "pipe:0", *codec]
        try:
            subprocess.run(
                [*cmd, str(path)],
                input=raw,
                check=True,
                capture_output=True,
                timeout=120,
            )
        except (OSError, subprocess.SubprocessError) as err:
            return {"ok": False, "error": f"ffmpeg could not write {path.name}: {err}"}
    return {
        "ok": True,
        "path": str(path),
        "seconds": float(head.get("x-voice-seconds") or 0),
        "model": head.get("x-voice-model"),
        "voice": head.get("x-voice-voice"),
        "fell_back": head.get("x-voice-fell-back"),
    }


def tts(
    text: str, app: str | None = None, timeout: float = 60.0, **options: Any
) -> bytes | None:
    """WAV bytes for the text, or None."""
    body = {"text": text, **({"app": app} if app else {}), **options}
    code, raw = _call("POST", "/api/tts", body, timeout=timeout)
    return raw if code == 200 else None


def transcribe(
    audio: bytes, app: str | None = None, timeout: float = 60.0
) -> str | None:
    """Text heard in the audio (any format ffmpeg reads), or None."""
    path = "/api/stt" + (f"?app={app}" if app else "")
    code, raw = _call("POST", path, audio, "application/octet-stream", timeout)
    return _json(raw).get("text") if code == 200 else None


def ptt(action: str, target: str = "auto") -> dict | None:
    """Push-to-talk: action is down, up, tap or cancel."""
    code, raw = _call("POST", f"/api/ptt/{action}?target={target}", b"")
    return _json(raw) if code == 200 else None


def ptt_up(target: str = "auto", wait: float = 0.3) -> dict | None:
    """Let go. Hyprland runs press and release as two processes, so on a quick
    tap the release can land before its own press: send it once more then."""
    result = ptt("up", target)
    if result and result.get("state") == "idle":
        time.sleep(wait)
        result = ptt("up", target)
    return result


def hush() -> bool:
    return _call("POST", "/api/hush", b"")[0] == 200


def ensure_running(timeout: float = 25.0) -> bool:
    """Start the Voice app when it is not running (as Forge would); True when up."""
    if status() is not None:
        return True
    try:
        manifest = json.loads((APP_DIR / "forge_app.json").read_text())
    except (OSError, ValueError):
        return False
    python = APP_DIR / ".venv" / "bin" / "python"
    if not python.exists():
        return False
    lock_path = (
        Path(os.environ.get("XDG_RUNTIME_DIR", "/tmp")) / "forge-voice-start.lock"
    )
    with open(lock_path, "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if status() is None:
            log_dir = FORGE / "outputs"
            log_dir.mkdir(exist_ok=True)
            port = str(manifest.get("port", 8467))
            cmd = [str(python), "-m", "uvicorn", manifest.get("module", "web_app:app")]
            cmd += ["--host", "127.0.0.1", "--port", port]
            env = dict(os.environ, FORGE_SHARED_DIR=str(HERE))
            with open(log_dir / "voice.log", "ab") as log:
                subprocess.Popen(
                    cmd,
                    cwd=APP_DIR / manifest.get("src_dir", "."),
                    env=env,
                    stdin=subprocess.DEVNULL,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                )
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if status() is not None:
                return True
            time.sleep(0.25)
    return False


def notify(title: str, body: str = "") -> None:
    if shutil.which("notify-send"):
        subprocess.run(
            ["notify-send", "-a", "Forge Voice", "-t", "4000", title, body],
            check=False,
            capture_output=True,
        )


# ------------------------------------------------------------------ hotkey

GNOME_SCHEMA = "org.gnome.settings-daemon.plugins.media-keys"
GNOME_PATH = (
    "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/forge-voice/"
)
GNOME_KEY = "<Super>z"
HYPR_KEY = "SUPER + ALT + Z"
HYPR_BEGIN = (
    "-- forge-voice begin (written by ~/Forge/shared/forge_voice.py install-hotkey)"
)
HYPR_END = "-- forge-voice end"


def _gsettings(*args: str) -> str:
    done = subprocess.run(
        ["gsettings", *args], capture_output=True, text=True, check=True
    )
    return done.stdout.strip()


def _gvariant_list(value: str) -> list[str]:
    value = value.removeprefix("@as").strip()
    return list(ast.literal_eval(value)) if value else []


def install_gnome(dry_run: bool = False, run: Callable[..., str] = _gsettings) -> str:
    """Super+Z runs `forge_voice.py tap` (GNOME fires on press only)."""
    try:
        paths = _gvariant_list(run("get", GNOME_SCHEMA, "custom-keybindings"))
    except (OSError, subprocess.CalledProcessError, ValueError, SyntaxError):
        return "GNOME: gsettings not available, skipped"
    relocatable = f"{GNOME_SCHEMA}.custom-keybinding:"
    for path in paths:
        if path == GNOME_PATH:
            continue
        if (
            run("get", relocatable + path, "binding").strip("'").lower()
            == GNOME_KEY.lower()
        ):
            return f"GNOME: {GNOME_KEY} is already used by {path}, skipped"
    for schema in (
        "org.gnome.desktop.wm.keybindings",
        "org.gnome.shell.keybindings",
        "org.gnome.mutter.keybindings",
    ):
        try:
            if f"'{GNOME_KEY.lower()}'" in run("list-recursively", schema).lower():
                return f"GNOME: {GNOME_KEY} is already used in {schema}, skipped"
        except subprocess.CalledProcessError:
            continue
    command = f"{sys.executable} {HERE / 'forge_voice.py'} tap"
    if dry_run:
        return f"GNOME: would bind {GNOME_KEY} to: {command}"
    backup = Path.home() / ".config" / "forge" / "backups"
    backup.mkdir(parents=True, exist_ok=True)
    (backup / f"gnome-custom-keybindings-{int(time.time())}.txt").write_text(
        repr(paths) + "\n"
    )
    if GNOME_PATH not in paths:
        run("set", GNOME_SCHEMA, "custom-keybindings", repr(paths + [GNOME_PATH]))
    run("set", relocatable + GNOME_PATH, "name", "Forge voice (tap to talk)")
    run("set", relocatable + GNOME_PATH, "command", command)
    run("set", relocatable + GNOME_PATH, "binding", GNOME_KEY)
    return f"GNOME: {GNOME_KEY} now runs: {command}"


def _hypr_block() -> str:
    cli = "python3 ~/Forge/shared/forge_voice.py"
    return "\n".join(
        [
            HYPR_BEGIN,
            f'hl.bind("{HYPR_KEY}", hl.dsp.exec_cmd("{cli} down"), {{description = "Forge voice: hold to talk"}})',
            f'hl.bind("{HYPR_KEY}", hl.dsp.exec_cmd("{cli} up"), {{release = true, description = "Forge voice: let go to send"}})',
            HYPR_END,
        ]
    )


def install_hyprland(dry_run: bool = False, config_dir: Path | None = None) -> str:
    """Hold Super+Alt+Z to talk: press runs `down`, release runs `up`."""
    hypr = config_dir or Path.home() / ".config" / "hypr"
    target = hypr / "custom" / "keybinds.lua"
    if not target.exists():
        return "Hyprland: no custom/keybinds.lua, skipped"
    text = target.read_text()
    wanted = HYPR_KEY.replace(" ", "").lower()
    for lua in hypr.rglob("*.lua"):
        body = lua.read_text(errors="replace")
        if lua == target and HYPR_BEGIN in body:
            body = body.split(HYPR_BEGIN)[0] + body.split(HYPR_END, 1)[-1]
        if f'"{wanted}"' in body.replace(" ", "").lower():
            return f"Hyprland: {HYPR_KEY} is already used in {lua.name}, skipped"
    block = _hypr_block()
    if HYPR_BEGIN in text:
        before, rest = text.split(HYPR_BEGIN, 1)
        new = before + block + rest.split(HYPR_END, 1)[-1]
    else:
        new = text.rstrip("\n") + "\n\n" + block + "\n"
    if new == text:
        return f"Hyprland: {HYPR_KEY} already set"
    if dry_run:
        return f"Hyprland: would add hold-to-talk on {HYPR_KEY} to {target}"
    shutil.copy2(target, target.with_name(f"keybinds.lua.bak-{int(time.time())}"))
    target.write_text(new)
    return f"Hyprland: {HYPR_KEY} hold-to-talk written to {target} (backup beside it)"


# --------------------------------------------------------------------- CLI


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="forge_voice", description="Forge voice hotkey and client"
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name in ("tap", "down", "up", "cancel"):
        p = sub.add_parser(name, help=f"push-to-talk {name}")
        p.add_argument(
            "--target", default="auto", choices=["auto", "jan", "claude", "text"]
        )
    sub.add_parser("hush", help="stop speaking now")
    sub.add_parser("status", help="print the Voice app's status")
    p = sub.add_parser("say", help="speak a line on the laptop")
    p.add_argument("text", nargs="+")
    p.add_argument("--app", default="anywhere")
    p.add_argument("--model", help="a voice model id from the registry")
    p.add_argument("--voice", help="a voice of that model (cloning models: a profile)")
    p = sub.add_parser("clip", help="save a line as a sound file, not the speakers")
    p.add_argument("text", nargs="+")
    p.add_argument("--out", required=True, help=".wav, .ogg (a voice note) or .mp3")
    p.add_argument("--app")
    p.add_argument("--model", help="a voice model id from the registry")
    p.add_argument("--voice", help="a voice of that model (cloning models: a profile)")
    p.add_argument("--force", action="store_true", help="replace a file already there")
    p.add_argument(
        "--any-voice",
        action="store_true",
        help="keep the line even when another model or voice made it",
    )
    p = sub.add_parser(
        "install-hotkey", help="Super+Z on GNOME, hold Super+Alt+Z on Hyprland"
    )
    p.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    if args.cmd == "install-hotkey":
        print(install_gnome(args.dry_run))
        print(install_hyprland(args.dry_run))
        return 0
    if args.cmd in ("tap", "down", "say", "clip"):
        if not ensure_running():
            notify(
                "Voice is not running", "Start Forge, or see ~/Forge/outputs/voice.log"
            )
            return 1
    if args.cmd in ("tap", "down", "up", "cancel"):
        if args.cmd == "up":
            result = ptt_up(args.target)
        else:
            result = ptt(args.cmd, args.target)
        print(json.dumps(result) if result else "voice app not answering")
        return 0 if result else 1
    if args.cmd == "hush":
        return 0 if hush() else 1
    if args.cmd in ("say", "clip"):
        opts = {k: v for k, v in (("model", args.model), ("voice", args.voice)) if v}
        text = " ".join(args.text)
        if args.cmd == "say":
            r = say_report(text, args.app, **opts)
        else:
            r = clip(
                text,
                args.out,
                args.app,
                overwrite=args.force,
                any_voice=args.any_voice,
                **opts,
            )
        if not r["ok"]:
            print(f"not made: {r['error']}", file=sys.stderr)
            return 1
        if args.cmd == "clip":
            print(f"saved {r['path']} ({r['seconds']} s, {r['model']}, {r['voice']})")
        why = not_asked(opts, r)
        if why:
            print(why)
        return 0
    current = status()
    print(json.dumps(current, indent=1) if current else "voice app not running")
    return 0 if current else 1


if __name__ == "__main__":
    sys.exit(main())
