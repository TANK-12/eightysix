"""A local language model reads the page: who speaks, how, and what the
words really are.

Emerson (2026-09-19): "make the voice and tone change depending on content
and context, it's too disconnected from what it's saying"; "it really has no
idea who is speaking and in what way"; and Jan may do a dictionary check of
the read lines. The geometry rules (`scene/speakers.py`) and the cue rules
(`audio/emotion.py`) stay; this pass runs after them and only fills what
they left weak, with every change recorded on the line under `llm` so the
editor can show it and undo it:

- speaker: taken when the geometry guess was unsure (conf below
  `SPEAKER_TAKEOVER`) and the model names a character who is in the panel
  or the one before it;
- expression and intensity: taken when the face and the words gave
  "neutral";
- text: a correction is taken only when it is a small edit of the OCR text
  (so the model cannot rewrite the dialogue).

The model is the app's Jan setting for role "script" (shared/forge_jan.py:
loaded on the first request, released when idle). Batches are one scene at
a time with the previous few lines as context, JSON in and out.
"""

from __future__ import annotations

import difflib
import json
import re
import time
from pathlib import Path
from typing import Any, Callable

from . import emotion

ROLE = "script"
DEFAULT_MODEL = "Qwen3_5-4B-IQ4_XS"
SPEAKER_TAKEOVER = 0.7  # geometry guesses below this may be overruled
MAX_TEXT_CHANGE = 0.35  # of the characters; more than this is a rewrite
BATCH = 14
CONTEXT_LINES = 4
LABELS = tuple(k for k in emotion.EXPRESSIONS if k != "neutral")

# How a line is said, as words the model can pick instead of four numbers:
# a name costs two tokens where the numbers cost thirty, and at 6 tokens/s
# on this laptop that is the difference between 40 s and 4 min per batch.
DELIVERY_WORDS: dict[str, dict[str, float]] = {
    "fast": {"speed": 1.2},
    "slow": {"speed": 0.85},
    "quiet": {"gain_db": -4.0},
    "loud": {"gain_db": 4.0},
    "whisper": {"speed": 0.9, "gain_db": -6.0},
    "shout": {"speed": 1.1, "gain_db": 5.0, "pitch": 1.0},
    "flat": {"speed": 1.0, "pitch": 0.0},
    "low": {"pitch": -1.5},
    "high": {"pitch": 1.5},
    "breathless": {"speed": 1.3, "pause_after": 0.1},
    "drawn out": {"speed": 0.8, "pause_after": 0.5},
    "pause": {"pause_after": 0.8},
}

SYSTEM = (
    "You annotate comic dialogue for voice acting. You get numbered lines in "
    "reading order with the panel each is in, the characters present in each "
    "panel, and the scene mood. Answer with one line per numbered line and "
    "nothing else, seven fields separated by | in this order:\n"
    "number | speaker | expression | intensity | delivery | why | fix\n"
    'speaker: an id present in that panel or the previous panel, or "narrator" '
    "for a caption box that narrates. When nobody is drawn in the panel, a "
    "balloon (especially one with a tail) is someone from the scene speaking "
    "off-panel -- pick them from the ids listed for that scene; only a box "
    "that reads as narration is the narrator. expression: one of "
    + ", ".join(LABELS)
    + " or neutral. intensity: 0.0-1.0. delivery: - or up to two of "
    + ", ".join(DELIVERY_WORDS)
    + ' ("slow, quiet"). why: at most five words. fix: - or the corrected '
    "text when the OCR text is garbled (1S -> is); a fix never rewrites.\n"
    "A caption written in the first person (I, me, my, we) is that "
    "character's own thought, not narration: give it the character in the "
    "panel (or the previous panel) and an inner-voice expression. Delivery "
    'follows the context, not the words: someone just saying "run" is -, a '
    "whispered threat is slow, quiet. Example:\n"
    "4 | c02 | angry | 0.7 | loud | shouting across the yard | -\n"
    "5 | narrator | neutral | 0.3 | - | scene caption | -"
)
DELIVERY_RANGES = {
    "speed": (0.7, 1.4),
    "pitch": (-3.0, 3.0),
    "gain_db": (-6.0, 6.0),
    "pause_after": (0.0, 1.5),
}


def _batches(lines: list[dict]) -> list[list[dict]]:
    out: list[list[dict]] = []
    cur: list[dict] = []
    scene = None
    for ln in lines:
        # a batch is up to BATCH lines; a scene change only starts a new
        # batch once the current one is half full, else 37 batches of one
        # or two lines cost 15 minutes (measured on chapter 1)
        if cur and (
            len(cur) >= BATCH
            or (ln.get("scene_id") != scene and len(cur) >= BATCH // 2)
        ):
            out.append(cur)
            cur = []
        scene = ln.get("scene_id")
        cur.append(ln)
    if cur:
        out.append(cur)
    return out


def _prompt(batch: list[dict], context: list[dict], cast_names: dict[str, str]) -> str:
    parts = []
    if context:
        parts.append("Earlier lines (context only, do not annotate):")
        for ln in context:
            parts.append(
                f'  {ln["n"]} [{ln["panel_id"]}] {ln.get("speaker") or "?"}: {ln["text"]}'
            )
    parts.append("Lines to annotate:")
    for ln in batch:
        who = (
            ", ".join(f"{c} ({cast_names.get(c, c)})" for c in ln["present"])
            or "nobody drawn"
        )
        if not ln["present"] and ln.get("scene_cast"):
            who += (
                "; in this scene: "
                + ", ".join(f"{c} ({cast_names.get(c, c)})" for c in ln["scene_cast"])
                + ("; balloon with a tail" if ln.get("tail") else "; box, no tail")
            )
        parts.append(
            f'  {ln["n"]} [{ln["panel_id"]}, present: {who}, mood: {ln.get("mood") or "?"}, '
            f'kind: {ln["kind"]}, geometry guess: {ln.get("speaker") or "?"} '
            f'({ln.get("speaker_conf", 0):.1f})] {ln["text"]}'
        )
    return "\n".join(parts)


def _parse_any(answer: str) -> dict:
    m = re.search(r"\{.*\}", answer.strip(), re.S)
    if not m:
        return {}
    text = m.group(0)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # the 4B writes {2: {...}} with bare numbers for keys (seen on
        # chapter 3) and leaves a comma after the last entry
        text = re.sub(r"(?<=[{,\s])(\d+)\s*:", r'"\1":', text)
        text = re.sub(r",\s*([}\]])", r"\1", text)
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return {}
    return data if isinstance(data, dict) else {}


FIELDS = ("speaker", "expression", "intensity", "delivery", "why", "fix")


def _parse_lines(answer: str) -> dict[str, dict]:
    """The pipe format: 'n | speaker | expression | intensity | delivery |
    why | fix'. A '-' field is empty. Lines that do not start with a number
    are skipped."""
    out: dict[str, dict] = {}
    for line in answer.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 3 or not cells[0].isdigit():
            continue
        rec: dict[str, Any] = {}
        for name, cell in zip(FIELDS, cells[1:]):
            if cell in ("", "-", "null", "none"):
                continue
            if name == "intensity":
                try:
                    rec[name] = float(cell)
                except ValueError:
                    pass
            else:
                rec[name] = cell
        out[cells[0]] = rec
    return out


def _parse(answer: str) -> dict[str, dict]:
    """Verdicts by line number: the pipe format first, JSON as a fallback
    (the model sometimes answers in JSON anyway)."""
    got = _parse_lines(answer)
    if got:
        return got
    return {str(k): v for k, v in _parse_any(answer).items() if isinstance(v, dict)}


def delivery_knobs(value) -> dict:
    """The model's delivery as knob values: words from DELIVERY_WORDS ("slow,
    quiet", or a list), or the older numbers object. Unknown words are
    ignored; None for nothing."""
    if isinstance(value, dict):
        return {k: v for k, v in value.items() if k in DELIVERY_RANGES}
    if isinstance(value, str):
        value = re.split(r"[,/;+&]|\band\b", value)
    if not isinstance(value, list):
        return {}
    out: dict[str, float] = {}
    for word in value:
        if not isinstance(word, str):
            continue
        knobs = DELIVERY_WORDS.get(word.strip().lower())
        if knobs:
            out.update(knobs)
    return out


def _small_change(old: str, new: str) -> bool:
    if not new or new.strip() == old.strip():
        return False
    ratio = difflib.SequenceMatcher(None, old.lower(), new.lower()).ratio()
    return ratio >= 1.0 - MAX_TEXT_CHANGE


CAPTION_GUESS_CONF = 0.5  # "narrator, it's a box" is a rule, not evidence


def _guess_conf(bubble: dict, guess: dict) -> float:
    """How sure the scene's guess about the speaker is. A person's own pick
    on the balloon is final. The scene gives a caption box to the narrator
    at 0.8, but that says nothing about *who* -- a box over a drawn
    character is often that character's thought (chapter 1: 16 thoughts
    read by the narrator), so the model may overrule it."""
    if bubble.get("speaker"):
        return 1.0
    conf = float(guess.get("conf") or 0.0)
    if guess.get("speaker") == "narrator" and bubble.get("kind") == "caption":
        return min(conf, CAPTION_GUESS_CONF)
    return conf


def gather(script: dict, bubbles: dict, scene: dict | None) -> list[dict]:
    """The lines as the model sees them, in reading order."""
    by_bubble = {b["id"]: b for b in bubbles.get("bubbles", [])}
    panels = (scene or {}).get("panels") or {}
    guesses = (scene or {}).get("speakers") or {}
    # everyone drawn anywhere in each scene: the options for a balloon in a
    # panel where nobody is drawn (someone speaking off-panel)
    scene_cast: dict[str, list[str]] = {}
    for p in panels.values():
        sid = p.get("scene_id")
        if sid is None:
            continue
        for c in p.get("characters", []):
            if c.get("cast_id") and c["cast_id"] not in scene_cast.setdefault(sid, []):
                scene_cast[sid].append(c["cast_id"])
    out = []
    for n, ln in enumerate(script.get("lines", []), 1):
        b = by_bubble.get(ln.get("bubble_id") or "", {})
        pid = b.get("panel_id") or ""
        panel = panels.get(pid, {})
        present = [
            c["cast_id"] for c in panel.get("characters", []) if c.get("cast_id")
        ]
        g = guesses.get(b.get("id") or "", {})
        out.append(
            {
                "n": n,
                "id": ln["id"],
                "panel_id": pid,
                "scene_id": panel.get("scene_id"),
                "mood": panel.get("mood"),
                "kind": ln.get("kind") or b.get("kind") or "speech",
                "text": ln.get("text") or "",
                "speaker": ln.get("speaker"),
                "speaker_conf": _guess_conf(b, g),
                "present": present,
                "scene_cast": [
                    c
                    for c in scene_cast.get(panel.get("scene_id"), [])
                    if c not in present
                ],
                "tail": b.get("tail") is not None,
                "edited": bool(ln.get("edited")),
            }
        )
    return out


def apply(
    script: dict, gathered: list[dict], answers: dict[str, dict], log=None
) -> dict:
    """Write the model's verdicts into the script's lines (in place) and
    return counts of what was taken."""
    by_id = {ln["id"]: ln for ln in script.get("lines", [])}
    prev_present: dict[str, list[str]] = {}
    last: list[str] = []
    for g in gathered:
        prev_present[g["id"]] = last
        last = g["present"] or last
    took = {"speaker": 0, "expression": 0, "fix": 0, "delivery": 0}
    for g in gathered:
        a = answers.get(str(g["n"]))
        ln = by_id.get(g["id"])
        if not a or ln is None or g["edited"]:
            continue
        rec: dict[str, Any] = {"model": True}
        allowed = (
            set(g["present"])
            | set(prev_present.get(g["id"], []))
            | (set(g.get("scene_cast") or []) if not g["present"] else set())
        )
        if isinstance(a.get("why"), str) and a["why"].strip():
            rec["why"] = a["why"].strip()[:120]
        spk = a.get("speaker")
        if isinstance(spk, str):
            spk = spk.strip()
            rec["speaker"] = spk
            # narrator is right for a caption box, and for any line in a
            # panel with nobody in it (a narration box the reader called a
            # balloon); a character must be in the panel or the one before
            ok = (
                spk == "narrator" and (g["kind"] == "caption" or not g["present"])
            ) or spk in allowed
            if ok and g["kind"] == "caption" and spk != "narrator":
                # a caption given to a character is read as their thought
                ln["kind"] = "thought"
                rec["kind"] = "thought"
            if ok and g["speaker_conf"] < SPEAKER_TAKEOVER and spk != ln.get("speaker"):
                ln["speaker"] = spk
                rec["speaker_taken"] = True
                took["speaker"] += 1
        expr = a.get("expression")
        try:
            inten = max(0.0, min(1.0, float(a.get("intensity") or 0.0)))
        except (TypeError, ValueError):
            inten = 0.0
        if isinstance(expr, str) and expr in emotion.EXPRESSIONS:
            rec["expression"], rec["intensity"] = expr, round(inten, 2)
            em = ln.get("emotion") or {}
            if (
                expr != "neutral"
                and inten > 0
                and em.get("expression", "neutral") == "neutral"
            ):
                if em.get("source") != "user":
                    ln["emotion"] = emotion.rules_for(
                        g["text"],
                        g["kind"],
                        {
                            "expression": {
                                "label": expr,
                                "intensity": inten,
                                "conf": 1.0,
                            }
                        },
                    )
                    ln["emotion"]["cues"].append(f"model read: {expr}")
                    ln["audio"], ln["dur"] = None, None
                    rec["expression_taken"] = True
                    took["expression"] += 1
        delivery = delivery_knobs(a.get("delivery"))
        if delivery and (ln.get("emotion") or {}).get("source") != "user":
            em = ln.setdefault("emotion", {})
            applied = {}
            for key, (lo, hi) in DELIVERY_RANGES.items():
                v = delivery.get(key)
                if isinstance(v, (int, float)):
                    applied[key] = round(max(lo, min(hi, float(v))), 3)
            if applied:
                # the model's delivery replaces the rule values for those
                # knobs; everything else the rules set (room, eq, tremolo,
                # grit, breath, blend) stays
                em.update(applied)
                why = a.get("why") if isinstance(a.get("why"), str) else ""
                em.setdefault("cues", []).append(
                    "model delivery" + (f": {why.strip()[:60]}" if why else "")
                )
                ln["audio"], ln["dur"] = None, None
                rec["delivery"] = applied
                took["delivery"] += 1
        fix = a.get("fix")
        if isinstance(fix, str) and _small_change(g["text"], fix):
            rec["fix"] = fix
            if not ln.get("text_ocr"):
                ln["text_ocr"] = ln.get("text")
            ln["text"] = emotion.normalize_text(fix)
            ln["audio"], ln["dur"] = None, None
            rec["fix_taken"] = True
            took["fix"] += 1
        ln["llm"] = rec
    if log:
        log(
            f"model pass: {took['speaker']} speakers, {took['expression']} expressions, {took['fix']} text fixes taken"
        )
    return took


RETRY_WAIT = 8.0  # seconds for the router to load the model again


def _ask_twice(chat, system: str, user: str, log=None) -> str:
    """One request, asked again once after a dropped connection: the router
    unloaded the model under a running request on 2026-09-19 (chapter 2,
    batches 8 and 9 lost) and loads it again on the next request."""
    try:
        return chat(system, user)
    except Exception as e:
        text = str(e).lower()
        if not any(w in text for w in ("connection", "proxy error", "timed out")):
            raise
        if log:
            log(f"model request dropped ({e}); asking once more in {RETRY_WAIT:.0f}s")
        time.sleep(RETRY_WAIT)
        return chat(system, user)


def run(
    script: dict,
    bubbles: dict,
    scene: dict | None,
    cast_doc: dict | None,
    chat: Callable[[str, str], str],
    log=None,
    check: Callable[[], None] | None = None,
) -> dict:
    """The whole pass: `chat(system, user) -> answer` is the model call;
    `check()` is called between batches and may raise to stop the pass
    (a cancelled job kept the model busy for half an hour otherwise)."""
    gathered = gather(script, bubbles, scene)
    names = {
        c["id"]: c.get("name") or c["id"] for c in (cast_doc or {}).get("cast", [])
    }
    answers: dict[str, dict] = {}
    batches = _batches(gathered)

    def ask(batch: list[dict], label: str) -> dict[str, dict]:
        first = gathered.index(batch[0])
        context = gathered[max(0, first - CONTEXT_LINES) : first]
        try:
            raw = _ask_twice(chat, SYSTEM, _prompt(batch, context, names), log)
        except Exception as e:  # one failed batch does not lose the others
            if log:
                log(f"model batch {label} failed: {type(e).__name__}: {e}")
            return {}
        got = _parse(raw)
        if not got and len(batch) > 3:
            # an answer too long for the model's budget comes back cut off
            # and unparseable: ask again in two halves
            if log:
                log(f"model batch {label}: no usable answer, asking in two halves")
            mid = len(batch) // 2
            return {**ask(batch[:mid], label + "a"), **ask(batch[mid:], label + "b")}
        if log:
            log(f"model batch {label}: {len(got)} of {len(batch)} lines answered")
        return got

    for i, batch in enumerate(batches):
        if check:
            check()
        answers.update(ask(batch, f"{i + 1}/{len(batches)}"))
    return apply(script, gathered, answers, log)


# ----------------------------------------------------------- with the picture --

VISION_MAX_SIDE = 640
VISION_SYSTEM = (
    "You look at one comic panel and say which drawn character says each "
    "numbered line. The characters are listed with an id and where they "
    "stand in the panel (left/centre/right, top/middle/bottom). Use the "
    "balloon tails, who faces whom, open mouths and the words themselves. "
    'Answer with JSON only: {"<line number>": "<id>"}; use "narrator" for a '
    'caption box and "?" when you cannot tell.'
)


def panel_image_url(chapter_dir, panel: dict) -> str | None:
    """The panel crop as a small JPEG data URL, or None."""
    import base64
    import io

    from PIL import Image

    rel = panel.get("image")
    if not rel:
        return None
    path = Path(chapter_dir) / rel
    if not path.exists():
        return None
    im = Image.open(path).convert("RGB")
    im.thumbnail((VISION_MAX_SIDE, VISION_MAX_SIDE))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=80)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def _where(box, pw: float, ph: float) -> str:
    x, y, w, h = (float(v) for v in box)
    cx, cy = (x + w / 2) / max(1.0, pw), (y + h / 2) / max(1.0, ph)
    col = "left" if cx < 0.38 else "right" if cx > 0.62 else "centre"
    row = "top" if cy < 0.38 else "bottom" if cy > 0.62 else "middle"
    return f"{col}, {row}"


def vision_pass(
    script: dict,
    bubbles: dict,
    scene: dict | None,
    cast_doc: dict | None,
    chapter_dir,
    panels: list[dict],
    chat_image: Callable[[str, str, str], str],
    log=None,
    check: Callable[[], None] | None = None,
    everyone: bool = False,
) -> int:
    """Ask the model, with the panel picture, who says each unsure line in
    panels where two or more characters stand -- every such line when
    `everyone` (Emerson, 2026-09-20: the speakers are wrong in every way;
    the picture verdicts matched the drawings on the chapter-1 trial).
    Returns speakers taken."""
    gathered = gather(script, bubbles, scene)
    by_id = {ln["id"]: ln for ln in script.get("lines", [])}
    names = {
        c["id"]: c.get("name") or c["id"] for c in (cast_doc or {}).get("cast", [])
    }
    pan = {p["id"]: p for p in panels}
    scene_panels = (scene or {}).get("panels") or {}
    by_panel: dict[str, list[dict]] = {}
    for g in gathered:
        if g["edited"] or g["kind"] in ("caption", "sfx"):
            continue
        if (everyone or g["speaker_conf"] < SPEAKER_TAKEOVER) and len(
            g["present"]
        ) >= 2:
            by_panel.setdefault(g["panel_id"], []).append(g)
    taken = 0
    for pid, lines in by_panel.items():
        if check:
            check()
        panel = pan.get(pid)
        if not panel:
            continue
        url = panel_image_url(chapter_dir, panel)
        if url is None:
            continue
        pw, ph = float(panel["box"][2]), float(panel["box"][3])
        chars = scene_panels.get(pid, {}).get("characters", [])
        who = [
            f'{c["cast_id"]} ({names.get(c["cast_id"], c["cast_id"])}): {_where(c["box"], pw, ph)}'
            for c in chars
            if c.get("cast_id")
        ]
        text = (
            "Characters in this panel: "
            + "; ".join(who)
            + "\nLines:\n"
            + "\n".join(f'  {g["n"]}: {g["text"]}' for g in lines)
        )
        try:
            raw = _ask_twice(
                lambda sy, us, u=url: chat_image(sy, us, u), VISION_SYSTEM, text, log
            )
        except Exception as e:
            if log:
                log(f"vision on {pid} failed: {type(e).__name__}: {e}")
            continue
        got = _parse_any(raw)
        allowed = {c["cast_id"] for c in chars if c.get("cast_id")}
        for g in lines:
            spk = got.get(str(g["n"]))
            spk = spk.get("speaker") if isinstance(spk, dict) else spk
            if not isinstance(spk, str) or spk.strip() not in allowed:
                continue
            ln = by_id[g["id"]]
            rec = ln.setdefault("llm", {"model": True})
            rec["vision_speaker"] = spk.strip()
            if ln.get("speaker") != spk.strip():
                ln["speaker"] = spk.strip()
                ln["audio"], ln["dur"] = None, None
                rec["speaker_taken"] = True
                rec["speaker"] = spk.strip()
                taken += 1
        if log:
            log(f"vision on {pid}: {len(got)} of {len(lines)} lines answered")
    if log:
        log(f"vision pass: {taken} speakers taken from the pictures")
    return taken
