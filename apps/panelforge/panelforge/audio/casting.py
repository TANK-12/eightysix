"""Casting: a voice for every character, chosen from what they look like.

The model (with its vision head) looks at a character's card pictures and
answers `gender | age | timbre`; `assign_voices` turns that into a distinct
Kokoro voice per character, leads first, so no two main characters share a
voice and nobody falls back to the one preview voice. A voice a person chose
by hand (no `source`, or `source: "user"`) is never touched; a voice this
module chose carries `source: "model"` and is re-chosen on the next run.
"""

from __future__ import annotations

import base64
import io
import re
from pathlib import Path
from typing import Any, Callable

from . import voices as voices_mod

GENDERS = ("male", "female")
AGES = ("child", "teen", "adult", "old")
TIMBRES = ("bright", "dark", "soft", "plain")

CAST_SYSTEM = (
    "You see one or more pictures of the same comic character's head. "
    "Answer with one line and nothing else, three fields separated by |:\n"
    "gender | age | timbre\n"
    "gender: male or female. age: child, teen, adult or old. timbre: how "
    "their voice would sound -- bright (light, lively), dark (deep, heavy), "
    "soft (gentle, quiet) or plain. Example:\nmale | adult | dark"
)

# which voices suit a timbre, per Kokoro prefix (language + gender)
TIMBRE_VOICES: dict[str, dict[str, list[str]]] = {
    "af": {
        "bright": ["af_bella", "af_sky", "af_jessica"],
        "dark": ["af_kore", "af_sarah", "af_alloy"],
        "soft": ["af_nicole", "af_river", "af_aoede"],
        "plain": ["af_heart", "af_nova", "af_alloy"],
    },
    "am": {
        "bright": ["am_puck", "am_adam", "am_michael"],
        "dark": ["am_onyx", "am_fenrir", "am_santa"],
        "soft": ["am_echo", "am_liam"],
        "plain": ["am_michael", "am_eric", "am_adam"],
    },
    "bf": {
        "bright": ["bf_lily", "bf_emma"],
        "dark": ["bf_isabella"],
        "soft": ["bf_alice"],
        "plain": ["bf_emma"],
    },
    "bm": {
        "bright": ["bm_lewis"],
        "dark": ["bm_george", "bm_daniel"],
        "soft": ["bm_fable"],
        "plain": ["bm_george"],
    },
}
# when every distinct voice of a gender is taken, the next characters share
# one, told apart by a pitch and speed offset (the model file has nine
# American men; Bad Born Blood has eighteen)
REUSE_OFFSETS: list[tuple[float, float]] = [
    (0.0, 1.0),
    (-0.8, 0.97),
    (0.8, 1.03),
    (-1.5, 1.0),
    (1.5, 0.98),
]
# a child speaks higher and a little quicker, an old character lower and slower
AGE_KNOBS: dict[str, dict[str, float]] = {
    "child": {"pitch": 2.0, "speed": 1.05},
    "teen": {"pitch": 1.0, "speed": 1.0},
    "adult": {"pitch": 0.0, "speed": 1.0},
    "old": {"pitch": -1.0, "speed": 0.93},
}


def picture_url(series_dir: Path, rel_paths: list[str], side: int = 320) -> str | None:
    """Up to three card pictures side by side as a JPEG data URL."""
    from PIL import Image

    tiles = []
    for rel in rel_paths[:3]:
        path = Path(series_dir) / rel
        if path.exists():
            im = Image.open(path).convert("RGB")
            im.thumbnail((side, side))
            tiles.append(im)
    if not tiles:
        return None
    w = sum(t.width for t in tiles) + 8 * (len(tiles) - 1)
    h = max(t.height for t in tiles)
    sheet = Image.new("RGB", (w, h), "white")
    x = 0
    for t in tiles:
        sheet.paste(t, (x, 0))
        x += t.width + 8
    buf = io.BytesIO()
    sheet.save(buf, "JPEG", quality=85)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def parse_look(answer: str) -> dict[str, str] | None:
    """'male | adult | dark' -> {gender, age, timbre}; None when unusable."""
    for line in answer.splitlines():
        cells = [c.strip().lower() for c in line.strip().strip("|").split("|")]
        if len(cells) < 2:
            continue
        words = [set(re.findall(r"[a-z]+", c)) for c in cells]
        gender = next((g for g in GENDERS if g in words[0]), None)
        age = next((a for a in AGES if a in words[1]), None)
        timbre = next((t for t in TIMBRES if len(words) > 2 and t in words[2]), "plain")
        if gender and age:
            return {"gender": gender, "age": age, "timbre": timbre}
    return None


def is_hand_chosen(entry: dict) -> bool:
    v = entry.get("voice") or {}
    return bool(v.get("kokoro")) and v.get("source") != "model"


def describe_cast(
    cast_doc: dict,
    series_dir: Path,
    chat_image: Callable[[str, str, str], str],
    log=None,
    check: Callable[[], None] | None = None,
    only: set[str] | None = None,
) -> dict[str, dict]:
    """Ask the model what each cast member (without a hand-chosen voice)
    looks like. Returns {cast id: {gender, age, timbre}}."""
    looks: dict[str, dict] = {}
    for entry in cast_doc.get("cast", []):
        cid = entry["id"]
        if only is not None and cid not in only:
            continue
        if is_hand_chosen(entry):
            continue
        if check:
            check()
        url = picture_url(series_dir, entry.get("samples") or [])
        if url is None:
            if log:
                log(f"{cid}: no card picture, skipped")
            continue
        try:
            raw = chat_image(CAST_SYSTEM, f"Character {entry.get('name') or cid}.", url)
        except Exception as e:
            if log:
                log(f"{cid}: model request failed: {type(e).__name__}: {e}")
            continue
        look = parse_look(raw)
        if look is None:
            if log:
                log(f"{cid}: unusable answer {raw[:60]!r}")
            continue
        looks[cid] = look
        if log:
            log(
                f"{cid} ({entry.get('name') or cid}): {look['gender']}, {look['age']}, {look['timbre']}"
            )
    return looks


def _prefix(gender: str, accent: str) -> str:
    return accent[0] + ("f" if gender == "female" else "m")


def assign_voices(
    cast_doc: dict,
    looks: dict[str, dict],
    available: list[str],
    accent: str = "a",
) -> int:
    """Give every described cast member a distinct voice (in place). Leads
    (most panels) choose first. Returns how many voices were set."""
    have = set(available)
    taken = {
        (e.get("voice") or {}).get("kokoro")
        for e in cast_doc.get("cast", [])
        if is_hand_chosen(e)
    }
    narrator = ((cast_doc.get("narrator") or {}).get("voice") or {}).get("kokoro")
    taken.add(narrator)
    order = sorted(
        (e for e in cast_doc.get("cast", []) if e["id"] in looks),
        key=lambda e: -len(e.get("panels") or []),
    )
    uses: dict[str, int] = {v: 1 for v in taken if v}
    n = 0
    for entry in order:
        look = looks[entry["id"]]
        prefix = _prefix(look["gender"], accent)
        other = _prefix(look["gender"], "b" if accent == "a" else "a")
        table = TIMBRE_VOICES.get(prefix, {})
        ranked = list(table.get(look["timbre"], [])) + [
            v for t in TIMBRES for v in table.get(t, [])
        ]
        # every voice of the right gender is a candidate after the fitting
        # ones: the rest of this accent, then the other English accent
        ranked += sorted(v for v in have if v.startswith(prefix + "_"))
        other_table = TIMBRE_VOICES.get(other, {})
        ranked += list(other_table.get(look["timbre"], [])) + [
            v for t in TIMBRES for v in other_table.get(t, [])
        ]
        ranked += sorted(v for v in have if v.startswith(other + "_"))
        seen: list[str] = []
        for v in ranked:
            # the narrator's voice is nobody's, not even shared
            if v in have and v not in seen and v != narrator:
                seen.append(v)
        if not seen:
            continue
        # a voice nobody has yet, else the fitting voice with the fewest users
        pick = next((v for v in seen if v not in uses), None)
        if pick is None:
            pick = min(seen, key=lambda v: (uses.get(v, 0), seen.index(v)))
        reuse = uses.get(pick, 0)
        uses[pick] = reuse + 1
        pitch_off, speed_mul = REUSE_OFFSETS[min(reuse, len(REUSE_OFFSETS) - 1)]
        knobs = AGE_KNOBS.get(look["age"], AGE_KNOBS["adult"])
        why = f"{look['gender']}, {look['age']}, {look['timbre']} voice"
        if reuse:
            why += f" (shared, pitched {pitch_off:+.1f})"
        entry["voice"] = {
            "kokoro": pick,
            "speed": round(knobs["speed"] * speed_mul, 3),
            "pitch": round(knobs["pitch"] + pitch_off, 2),
            "gain_db": 0.0,
            "source": "model",
            "why": why,
        }
        n += 1
    return n


def cast_voices(
    cast_doc: dict,
    series_dir: Path,
    chat_image: Callable[[str, str, str], str],
    available: list[str],
    log=None,
    check: Callable[[], None] | None = None,
    only: set[str] | None = None,
) -> dict[str, Any]:
    looks = describe_cast(cast_doc, series_dir, chat_image, log, check, only)
    n = assign_voices(cast_doc, looks, available)
    if log:
        log(f"casting: {n} voices chosen for {len(looks)} described characters")
    return {"described": len(looks), "voices": n, "looks": looks}
