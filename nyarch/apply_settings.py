#!/usr/bin/env python3
"""Point Nyarch Assistant at Jan, Kokoro, AI Studio and a working wake word.

Everything this configures already exists on the machine; nothing is downloaded.
The settings live in the Flatpak's GSettings keyfile, so this reads the current
values, merges its changes into them and writes them back through the sandbox's
own `gsettings`, which keeps the GVariant quoting correct.

Run it with the assistant closed.  It is safe to run more than once.
"""

import configparser
import json
import os
import shlex
import subprocess
import sys

import gi

gi.require_version("GLib", "2.0")
from gi.repository import GLib  # type: ignore  # noqa: E402

APP_ID = "moe.nyarchlinux.assistant"
SCHEMA = "moe.nyarchlinux.assistant"
KEYFILE = os.path.expanduser(f"~/.var/app/{APP_ID}/config/glib-2.0/settings/keyfile")
HOME = os.path.expanduser("~")

JAN_ENDPOINT = "http://127.0.0.1:1337/v1"
# Acchan (Forge app apps/acchan, an always-on user service) speaks the OpenAI
# API and runs the whole agent behind it: tools for apps, windows, tabs, files,
# documents and media, an instant path for plain commands, and prompts tuned
# for these small models. Nyarch's own prompts asked the 2B for bash blocks,
# which is where the empty replies and "does nothing" came from (2026-09-22).
ACCHAN_ENDPOINT = "http://127.0.0.1:8451/v1"
ACCHAN_MODEL = "acchan"
# Jan's local server ignores the key, but the OpenAI client refuses to send a
# request without one.
JAN_KEY = "jan-local"
FAST_MODEL = "qwen35-0_8b-spectralquant-calib360-q4_k_m"
SMART_VISION_MODEL = "Qwen3_5-4B-IQ4_XS"

TTS_COMMAND = (
    f"FORGE_TTS_VOICE=am_michael "
    f"{HOME}/Forge/apps/novelforge/.venv/bin/python "
    f"{HOME}/Forge/nyarch/forge_tts.py {{0}} {{1}}"
)
AI_STUDIO_MODELS = f"{HOME}/Forge/apps/ai-studio/models/sd/catalog"

# Plain values, written as-is.
SIMPLE_SETTINGS = {
    # Fast little model answers ordinary chat; see the secondary below.
    "language-model": "openai",
    # The 4B with vision handles anything containing a picture, which is what
    # every screenshot becomes.
    "secondary-language-model": "openai",
    "secondary-llm-on": "true",
    "secondary-llm-vision": "true",
    # Speak replies with the Kokoro voices NovelForge already has.
    "tts-on": "true",
    "tts": "custom_command",
    # The wake word failed because it was in "openwakeword" mode, which only
    # knows four fixed phrases and had no model installed. Secondary-STT mode
    # listens with Whisper and matches any phrase we like.
    "wakeword-on": "true",
    "wakeword-mode": "secondary-stt",
    "wakeword": "hey arch, hey acchan, acchan, arch chan, hey computer",
    "wakeword-energy-threshold": "300",
    "wakeword-silence-duration": "1.0",
    "wakeword-pre-buffer-duration": "0.8",
    "secondary-stt-on": "true",
    "secondary-stt-engine": "whispercpp",
    "automatic-stt": "true",
    "stt-engine": "whispercpp",
    "image-generator": "stablediffusioncpp",
}

# Nested JSON blobs, merged key by key so nothing already there is lost.
JSON_SETTINGS = {
    "llm-settings": {
        "openai": {
            "endpoint": ACCHAN_ENDPOINT,
            "api": JAN_KEY,
            "model": ACCHAN_MODEL,
            "custom_model": True,
            "streaming": True,
            "advanced_params": False,
            "max-tokens": 2048,
            # Qwen3.5 thinks before answering unless told not to, which turned a
            # 0.3 second reply into a 4 second one with an empty answer. The
            # assistant's own "thinking" toggle only affects how it parses the
            # reply, so the flag has to go in the request body itself.
            "thinking": False,
            "custom_body": '{"chat_template_kwargs": {"enable_thinking": false}}',
        }
    },
    "llm-secondary-settings": {
        "openai": {
            "endpoint": JAN_ENDPOINT,
            "api": JAN_KEY,
            "model": SMART_VISION_MODEL,
            "streaming": True,
            "advanced_params": True,
            "max-tokens": 4096,
            # Without this the 4B spends its whole reply thinking and returns
            # an empty answer (found 2026-09-22: it was missing here).
            "thinking": False,
            "custom_body": '{"chat_template_kwargs": {"enable_thinking": false}}',
        }
    },
    "tts-voice": {"custom_command": {"command": TTS_COMMAND}},
    "stt-settings": {
        "whispercpp": {
            "model": "tiny.en",
            "language": "en",
            "gpu_acceleration": True,
        }
    },
    "stt-secondary-settings": {
        "whispercpp": {
            "model": "tiny.en",
            "language": "en",
            "gpu_acceleration": True,
        }
    },
    "image-generator-settings": {
        "stablediffusioncpp": {"custom_models_dir": AI_STUDIO_MODELS}
    },
}


def read_current() -> dict:
    """Return the assistant's current settings from its GSettings keyfile."""
    parser = configparser.RawConfigParser()
    # Keys are case-sensitive GSettings names, so keep them verbatim.
    parser.optionxform = lambda option: option  # type: ignore[assignment]
    parser.read(KEYFILE)
    section = "moe/nyarchlinux/assistant"
    if section not in parser:
        return {}
    return dict(parser[section])


def parse_variant_string(raw: str):
    """Turn a keyfile GVariant literal back into the Python value it holds."""
    try:
        return GLib.Variant.parse(GLib.VariantType("s"), raw, None, None).unpack()
    except GLib.Error:
        return None


def merge(existing: dict, updates: dict) -> dict:
    """Merge per-handler settings without discarding unrelated handlers."""
    merged = dict(existing)
    for handler, values in updates.items():
        current = dict(merged.get(handler) or {})
        current.update(values)
        merged[handler] = current
    return merged


def build_commands() -> list[str]:
    current = read_current()
    commands = []

    for key, value in SIMPLE_SETTINGS.items():
        commands.append(f"gsettings set {SCHEMA} {key} {shlex.quote(value)}")

    for key, updates in JSON_SETTINGS.items():
        existing = {}
        if key in current:
            parsed = parse_variant_string(current[key])
            if parsed:
                try:
                    existing = json.loads(parsed)
                except json.JSONDecodeError:
                    existing = {}
        blob = json.dumps(merge(existing, updates))
        literal = GLib.Variant("s", blob).print_(False)
        commands.append(f"gsettings set {SCHEMA} {key} {shlex.quote(literal)}")

    return commands


def main() -> int:
    if not os.path.exists(KEYFILE):
        print(f"No settings file at {KEYFILE}", file=sys.stderr)
        return 1

    commands = build_commands()
    script = "set -e\n" + "\n".join(commands) + "\necho APPLIED\n"
    finished = subprocess.run(
        ["flatpak", "run", "--command=bash", APP_ID, "-c", script],
        capture_output=True,
        text=True,
        timeout=180,
    )
    output = (finished.stdout or "").strip()
    if finished.returncode != 0 or "APPLIED" not in output:
        print(finished.stderr.strip() or output, file=sys.stderr)
        return 1

    print(f"Applied {len(commands)} settings.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
