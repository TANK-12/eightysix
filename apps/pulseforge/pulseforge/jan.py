"""
Talking to Jan, the local text model server.

This replaces the old AI Studio backdrop button, which asked a service for a
generated *image*. There is no image generator on this machine -- only small
text models served by Jan -- so that button could never work. What a small local
model is genuinely reliable at is language work and **choosing from a list you
hand it**, so that is all this asks of it:

* draft the title, description and tags for an upload, from the tracklist;
* pick a look from the app's own registries when you describe one in words.

Two rules run through this module. Everything the model returns is **validated
against what actually exists** and anything unrecognised is dropped rather than
trusted -- a small model will happily invent an effect called `rainstorm`. And
every call fails *fast and legibly*: Jan not running is the normal case, not an
error worth hanging thirty seconds over.

Stdlib urllib only, like the rest of this app's outbound calls.
"""

import json
import os
import re
import urllib.error
import urllib.request

BASE = os.environ.get("JAN_BASE_URL", "http://127.0.0.1:1337/v1")
MODEL = os.environ.get("JAN_MODEL", "")
CONNECT_TIMEOUT = 3.0
REPLY_TIMEOUT = 90.0

_model_cache = {"name": MODEL, "checked": 0.0}


class JanUnavailable(RuntimeError):
    """Jan is not reachable. Expected often enough to be its own type."""


def _get(path, timeout):
    req = urllib.request.Request(f"{BASE}{path}", method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _post(path, payload, timeout):
    req = urllib.request.Request(
        f"{BASE}{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def model_name():
    """Whichever model Jan currently has loaded, cached for a minute.

    Jan's model id changes whenever you swap models in its UI, so hardcoding one
    guarantees a 404 the first time you switch.
    """
    import time

    if MODEL:
        return MODEL
    now = time.time()
    if _model_cache["name"] and now - _model_cache["checked"] < 60:
        return _model_cache["name"]
    data = (_get("/models", CONNECT_TIMEOUT) or {}).get("data") or []
    if not data:
        raise JanUnavailable("Jan is running but has no model loaded.")
    _model_cache["name"] = data[0].get("id")
    _model_cache["checked"] = now
    return _model_cache["name"]


def status():
    """Is Jan there, and with what loaded? Never raises."""
    try:
        return {"running": True, "model": model_name(), "detail": ""}
    except JanUnavailable as e:
        return {"running": True, "model": None, "detail": str(e)}
    except Exception as e:
        return {
            "running": False,
            "model": None,
            "detail": f"No local model server at {BASE} ({type(e).__name__}).",
        }


def chat(prompt, system="", max_tokens=700, temperature=0.7):
    """One completion. Raises `JanUnavailable` rather than hanging."""
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    try:
        name = model_name()
        body = {
            "model": name,
            "messages": messages,
            "max_tokens": int(max_tokens),
            "temperature": float(temperature),
            "stream": False,
        }
        data = _post("/chat/completions", body, REPLY_TIMEOUT)
    except JanUnavailable:
        raise
    except (urllib.error.URLError, OSError) as e:
        raise JanUnavailable(
            f"Could not reach the local model at {BASE}. Is Jan running? ({e})"
        )
    except Exception as e:  # pragma: no cover - malformed reply
        raise JanUnavailable(f"The local model returned something unusable: {e}")
    choices = data.get("choices") or []
    if not choices:
        raise JanUnavailable("The local model returned no reply.")
    return (choices[0].get("message") or {}).get("content") or ""


# --------------------------------------------------------------------------
# parsing what comes back
# --------------------------------------------------------------------------
def extract_json(text):
    """The first JSON object in a reply, or None.

    Small models wrap JSON in prose, fence it in markdown, or add a trailing
    sentence. Rather than demanding they behave, find the first balanced object
    and parse that.
    """
    if not text:
        return None
    fenced = re.search(r"```(?:json)?\s*(.+?)```", text, re.S)
    if fenced:
        text = fenced.group(1)
    start = text.find("{")
    while start != -1:
        depth = 0
        for i in range(start, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start : i + 1])
                    except ValueError:
                        break
        start = text.find("{", start + 1)
    return None


# --------------------------------------------------------------------------
# 1. the text you paste under the video
# --------------------------------------------------------------------------
UPLOAD_SYSTEM = (
    "You write titles and descriptions for background-music videos on YouTube: "
    "lofi, chillhop, ambient study mixes. You are concise and never breathless. "
    "You do not use exclamation marks, emoji, or phrases like 'dive in'. "
    "Reply with JSON only."
)


def write_upload_text(tracks, minutes, mood="", ambience="", extra=""):
    """Draft a title, a short blurb and some tags for a finished mix."""
    listing = "\n".join(f"- {t}" for t in (tracks or [])[:25]) or "- (untitled)"
    prompt = (
        f"A {minutes:.0f} minute background music mix.\n"
        f"Tracks:\n{listing}\n"
        + (f"Visual mood: {mood}\n" if mood else "")
        + (f"Ambient sound under the music: {ambience}\n" if ambience else "")
        + (f"Other notes: {extra}\n" if extra else "")
        + "\nReply with JSON only, exactly these keys:\n"
        '{"title": "...", "blurb": "two or three sentences", '
        '"tags": ["...", "..."]}\n'
        "The title is under 70 characters. Give 8 to 12 tags, lowercase, "
        "no hash symbols."
    )
    raw = chat(prompt, system=UPLOAD_SYSTEM, max_tokens=600, temperature=0.8)
    data = extract_json(raw) or {}
    tags = data.get("tags") or []
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",")]
    return {
        "title": str(data.get("title") or "").strip()[:120],
        "blurb": str(data.get("blurb") or "").strip(),
        "tags": [str(t).strip().lstrip("#").lower() for t in tags if str(t).strip()][
            :15
        ],
        "raw": raw if not data else "",
    }


# --------------------------------------------------------------------------
# 2. describe a look, get a shot
# --------------------------------------------------------------------------
LOOK_SYSTEM = (
    "You configure a visual scene by choosing from lists you are given. "
    "You only ever use names from those lists. Reply with JSON only."
)


def choose_look(description, effects, emitters, presets):
    """Turn a phrase into a shot configuration, chosen from what exists.

    The model is given the real registry names and asked to pick. Everything it
    returns is then checked against those same lists, because a small model will
    cheerfully invent an effect called `rainstorm` and mean it.
    """
    prompt = (
        f'Someone wants a scene that looks like: "{description}"\n\n'
        f"Available presets: {', '.join(presets)}\n"
        f"Available region effects: {', '.join(effects)}\n"
        f"Available particle emitters: {', '.join(emitters)}\n\n"
        "Reply with JSON only:\n"
        '{"preset": "one preset name or null",\n'
        ' "emitters": ["up to three emitter names"],\n'
        ' "look": {"warmth": -1..1, "saturation": 0..2, "vignette": 0..1,\n'
        '          "bloom": 0..1, "grain": 0..1, "scanlines": 0..1,\n'
        '          "haze": 0..1},\n'
        ' "why": "one short sentence"}\n'
        "Use only names from the lists above."
    )
    raw = chat(prompt, system=LOOK_SYSTEM, max_tokens=500, temperature=0.5)
    return validate_look(extract_json(raw) or {}, effects, emitters, presets, raw)


LOOK_RANGES = {
    "warmth": (-1.0, 1.0),
    "saturation": (0.0, 2.0),
    "vignette": (0.0, 1.0),
    "bloom": (0.0, 1.0),
    "grain": (0.0, 1.0),
    "scanlines": (0.0, 1.0),
    "haze": (0.0, 1.0),
    "fringing": (0.0, 1.0),
    "letterbox": (0.0, 0.3),
    "leak": (0.0, 1.0),
}


def validate_look(data, effects, emitters, presets, raw=""):
    """Keep what exists, drop what does not, and say what was dropped."""
    out = {"preset": None, "emitters": [], "look": {}, "why": "", "dropped": []}
    preset = data.get("preset")
    if isinstance(preset, str) and preset in presets:
        out["preset"] = preset
    elif preset:
        out["dropped"].append(f"preset '{preset}'")

    for name in data.get("emitters") or []:
        if isinstance(name, str) and name in emitters:
            if name not in out["emitters"]:
                out["emitters"].append(name)
        elif name:
            out["dropped"].append(f"emitter '{name}'")
    out["emitters"] = out["emitters"][:4]

    for key, value in (data.get("look") or {}).items():
        rng = LOOK_RANGES.get(key)
        if not rng or not isinstance(value, (int, float)):
            if key:
                out["dropped"].append(f"look '{key}'")
            continue
        out["look"][key] = max(rng[0], min(rng[1], float(value)))

    why = data.get("why")
    out["why"] = str(why).strip()[:200] if isinstance(why, str) else ""
    if not data and raw:
        out["dropped"].append("the whole reply -- it was not JSON")
    return out
