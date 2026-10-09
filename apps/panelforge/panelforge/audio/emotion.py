"""Cue -> delivery rules (CONTRACTS.md script.json `emotion` and "Expression
cues for voice acting"), plus the DSP that renders them. Kept separate from
kokoro_engine so the rules can be unit-tested without loading the model.

Two layers, both pure:

1. Punctuation and bubble-kind rules (Emerson, 2026-09-17), unchanged:
   "!" or a shout bubble is faster and louder; "..." slower with a longer
   pause; "?" a slight lift; whisper quieter; thought bubbles softer with an
   inner-voice treatment; ALL-CAPS lettering is read normally but counts as
   a shout.
2. Page cues (added the same day): the speaker's face expression, the balloon
   outline, the lettering (size, weight, wavy, trembling, bold words), the
   scene mood and action, and the panel acoustics. Each cue that fires is
   named in `cues` in plain words so the editor can show why a line sounds
   the way it does, and every knob is a number Emerson can override.

`rules_for(text, kind)` with no context returns exactly what layer 1 alone
produced (plus the new keys at their neutral values), and `apply` on such a
dict is the identity, so a line with no cues sounds the same as before.

Registries (one entry to extend): EXPRESSIONS, OUTLINES, MOODS, SPACES.
"""

from __future__ import annotations

import re

_WORD = re.compile(r"[A-Za-z]")

# Face expression -> knob deltas at intensity 1 (scaled linearly by the
# detected intensity). speed is a multiplier delta (0.10 = 10% faster), gain
# in dB, pitch in semitones, pause in seconds; tremolo/grit/breath 0..1;
# blend names the tone of the partner voice mixed in (see voices.BLEND_PARTNERS).
EXPRESSIONS: dict[str, dict] = {
    "neutral": {},
    "angry": {"speed": 0.10, "gain": 3.0, "pitch": -1.0, "grit": 0.5, "blend": "dark"},
    "happy": {"speed": 0.05, "gain": 1.0, "pitch": 1.5, "blend": "bright"},
    "sad": {
        "speed": -0.12,
        "gain": -2.0,
        "pitch": -1.5,
        "breath": 0.25,
        "pause": 0.2,
        "blend": "soft",
    },
    "scared": {
        "speed": 0.08,
        "gain": -1.0,
        "pitch": 2.0,
        "tremolo": 0.5,
        "breath": 0.3,
        "blend": "soft",
    },
    "surprised": {"speed": 0.05, "gain": 2.0, "pitch": 2.5, "blend": "bright"},
    "smug": {"speed": -0.08, "pitch": -0.5, "blend": "dark"},
    "pained": {
        "speed": -0.10,
        "gain": 1.0,
        "pitch": -1.0,
        "grit": 0.3,
        "tremolo": 0.3,
        "breath": 0.2,
    },
    "determined": {
        "speed": -0.03,
        "gain": 2.0,
        "pitch": -0.5,
        "grit": 0.15,
        "blend": "dark",
    },
}
BLEND_TONES = ("bright", "dark", "soft")
MAX_BLEND_WEIGHT = 0.25  # the chosen voice always stays at least 75%
MIN_FACE_CONF = 0.35

# Balloon outline -> deltas (not intensity scaled; the outline is binary).
OUTLINES: dict[str, dict] = {
    "smooth": {},
    "rect": {},
    "none": {},
    "jagged": {"speed": 0.05, "gain": 2.0, "grit": 0.3},
    "wobbly": {"gain": -1.0, "tremolo": 0.3, "breath": 0.15},
    "dashed": {"gain": -4.0, "breath": 0.3, "speed": -0.03},
    "cloud": {"inner": True},
}

# Scene mood -> small deltas; `action` (0..1) adds up to 5% speed on top.
MOODS: dict[str, dict] = {
    "tense": {"speed": 0.03, "pause": 0.1},
    "calm": {"speed": -0.03},
    "action": {"speed": 0.06, "gain": 1.0},
    "sad": {"speed": -0.05, "gain": -1.0},
    "comic": {"speed": 0.03, "pitch": 0.5},
    "mystery": {"speed": -0.05, "gain": -1.0, "reverb": 0.1},
}

# Panel acoustics -> room (dsp.ROOMS key), base reverb amount (scaled by
# 0.4 + 0.6 * size) and an optional EQ treatment.
SPACES: dict[str, dict] = {
    "small-room": {"room": "small-room", "reverb": 0.5},
    "hall": {"room": "hall", "reverb": 0.9},
    "outdoor": {"room": "outdoor", "reverb": 0.3},
    "vehicle": {"room": "vehicle", "reverb": 0.6, "eq": "vehicle"},
    "comms": {"room": "comms", "reverb": 0.0, "eq": "radio", "grit": 0.1},
    "void": {"room": "void", "reverb": 0.8, "eq": "void"},
}

# What the words say -> an expression, used when the face gives nothing
# (the face classifier says "neutral" for most panels). One entry per
# feeling: the words that signal it and how much each adds; punctuation and
# capitals raise the intensity. Named in `cues` as e.g. "angry words: kill".
WORDS: dict[str, tuple[str, ...]] = {
    "angry": (
        "kill",
        "die",
        "damn",
        "bastard",
        "shut up",
        "get out",
        "idiot",
        "fool",
        "hate",
        "enough",
        "how dare",
        "you dare",
        "scum",
        "trash",
        "worthless",
        "curse",
        "hell",
        "bloody",
        "stupid",
        "pathetic",
        "traitor",
        "liar",
    ),
    "scared": (
        "please",
        "help",
        "don't",
        "no no",
        "run",
        "scared",
        "afraid",
        "stop",
        "can't",
        "what is that",
        "what was that",
        "behind you",
        "get away",
        "monster",
        "it's coming",
        "we're dead",
        "going to die",
    ),
    "sad": (
        "sorry",
        "gone",
        "dead",
        "lost",
        "miss you",
        "cry",
        "tears",
        "alone",
        "forgive",
        "goodbye",
        "never again",
        "why did",
        "if only",
        "too late",
        "forgot",
        "mourn",
        "grave",
        "funeral",
    ),
    "happy": (
        "haha",
        "hehe",
        "great",
        "wonderful",
        "thank",
        "love",
        "finally",
        "amazing",
        "delicious",
        "welcome",
        "glad",
        "fun",
        "nice",
        "yay",
        "brilliant",
        "perfect",
        "congratulations",
    ),
    "determined": (
        "i will",
        "we will",
        "let's go",
        "move",
        "now",
        "attack",
        "charge",
        "ready",
        "follow me",
        "do it",
        "no matter what",
        "never give up",
        "on me",
        "hold the line",
        "fire",
    ),
    "surprised": (
        "what?",
        "what!",
        "how?",
        "impossible",
        "no way",
        "you're",
        "can't be",
        "really?",
        "wait",
        "huh?",
        "eh?",
        "seriously",
        "what the",
    ),
    "smug": (
        "of course",
        "as expected",
        "told you",
        "pathetic",
        "too easy",
        "heh",
        "hmph",
        "naturally",
        "obviously",
        "is that all",
    ),
    "pained": (
        "argh",
        "ugh",
        "gah",
        "hurts",
        "pain",
        "my leg",
        "my arm",
        "bleeding",
        "can't breathe",
        "it burns",
        "ow",
        "agh",
        "urgh",
    ),
}
WORDS_MAX_INTENSITY = 0.7  # words alone never hit the face's full strength

THOUGHT_REVERB = 0.35
BOLD_SPEED_MUL = 0.85
BOLD_GAIN_DB = 2.5

_LIMITS = {
    "speed": (0.6, 1.8),
    "gain_db": (-14.0, 8.0),
    "pause_after": (0.0, 2.0),
    "reverb": (0.0, 1.0),
    "pitch": (-4.0, 4.0),
    "tremolo": (0.0, 0.75),  # full depth dips to silence; stacked fear cues stop here
    "grit": (0.0, 0.7),
    "breath": (0.0, 1.0),
}


def is_shouty_caps(text: str) -> bool:
    letters = _WORD.findall(text)
    if len(letters) < 3:
        return False
    upper = sum(1 for c in letters if c.isupper())
    return upper / len(letters) > 0.8


def normalize_text(text: str) -> str:
    """Comic lettering is often ALL CAPS regardless of tone; TTS engines read
    that as robotic or letter-by-letter. Convert to normal sentence case so
    Kokoro speaks it naturally -- the shout itself is carried by the emotion
    params (speed/gain), not by shouting text at the model."""
    if is_shouty_caps(text):
        s = text.strip()
        if s:
            s = s[0].upper() + s[1:].lower()
        return s
    return text


def _clampf(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def words_expression(
    text: str, mood: str | None = None
) -> tuple[str | None, float, list[str]]:
    """(expression label, intensity, matched words) from the words, with the
    scene mood as the only context; see the corroboration rule inside."""
    low = " " + re.sub(r"\s+", " ", re.sub(r"[^a-z?!' ]", " ", text.lower())) + " "
    plain = " " + re.sub(r"\s+", " ", re.sub(r"[^a-z' ]", " ", text.lower())) + " "
    best: tuple[str | None, list[str]] = (None, [])
    for label, words in WORDS.items():
        hits = [
            w
            for w in words
            if (w in low if w.endswith(("?", "!")) else (" " + w + " ") in plain)
        ]
        if len(hits) > len(best[1]):
            best = (label, hits)
    label, hits = best
    if not label:
        return None, 0.0, []
    bangs = text.count("!")
    caps = is_shouty_caps(text)
    # one cue word on its own is not evidence: "run" can be said flatly. It
    # takes a second cue word, or punctuation or capitals that show force,
    # or (via `mood`) a tense or action scene, before the words set a tone.
    if len(hits) < 2 and not bangs and not caps and mood not in ("tense", "action"):
        return None, 0.0, hits
    intensity = 0.3 + 0.15 * (len(hits) - 1)
    if bangs:
        intensity += 0.1 * min(3, bangs)
    if caps:
        intensity += 0.1
    if mood in ("tense", "action"):
        intensity += 0.05
    return label, min(WORDS_MAX_INTENSITY, intensity), hits


def rules_for(text: str, kind: str, ctx: dict | None = None) -> dict:
    """-> emotion dict. `kind` is the bubble kind (speech/thought/caption/
    shout/sfx/whisper). `ctx` carries the page cues for this line, all
    optional: {style: bubbles.json style, expression: {label, intensity,
    conf}, mood, action, acoustics: {space, size}, balloon_scale}.
    Output: speed, gain_db, pause_after, reverb (the original four), plus
    expression, intensity, room, cues[], pitch, tremolo, grit, breath, eq,
    blend, emphasis[], lift and source."""
    ctx = ctx or {}
    style = ctx.get("style") or {}
    cues: list[str] = []
    # accumulators; speed is multiplicative, the rest additive
    speed, gain_db, pause_after, reverb = 1.0, 0.0, 0.2, 0.0
    pitch = tremolo = grit = breath = 0.0
    room: str | None = None
    eq: str | None = None
    inner = kind == "thought"

    # -- layer 1: punctuation and kind (unchanged rules) --
    shout_bubble = kind == "shout"
    caps = is_shouty_caps(text)
    shout = shout_bubble or "!" in text or caps
    ellipsis = "..." in text or text.rstrip().endswith("…")
    question = "?" in text

    if shout:
        speed *= 1.15
        gain_db += 4.0
        pause_after = max(pause_after, 0.15)
        if shout_bubble:
            cues.append("shout bubble")
        if "!" in text:
            cues.append("exclamation mark")
        if caps:
            cues.append("all-caps lettering")
    if ellipsis:
        speed *= 0.85
        pause_after = max(pause_after, 0.55)
        cues.append("trailing dots")
    if question and not shout:
        gain_db += 0.5
        cues.append("question mark")
    if kind == "whisper":
        gain_db -= 6.0
        speed *= 0.95
        cues.append("whisper bubble")
    if kind == "thought":
        gain_db -= 3.0
        reverb = THOUGHT_REVERB
        cues.append("thought bubble")

    # -- layer 2: the speaker's face --
    expression = "neutral"
    intensity = 0.0
    blend = None
    face = ctx.get("expression") or {}
    label = face.get("label")
    if label and label != "neutral" and label in EXPRESSIONS:
        conf = float(face.get("conf", 1.0))
        i = _clampf(float(face.get("intensity", 0.0)), 0.0, 1.0)
        if conf < MIN_FACE_CONF:
            cues.append(f"{label} face ignored: low confidence")
        elif i > 0:
            expression, intensity = label, i
            t = EXPRESSIONS[label]
            speed *= 1.0 + t.get("speed", 0.0) * i
            gain_db += t.get("gain", 0.0) * i
            pitch += t.get("pitch", 0.0) * i
            tremolo += t.get("tremolo", 0.0) * i
            grit += t.get("grit", 0.0) * i
            breath += t.get("breath", 0.0) * i
            pause_after += t.get("pause", 0.0) * i
            if t.get("blend"):
                blend = {"tone": t["blend"], "weight": round(MAX_BLEND_WEIGHT * i, 3)}
            cues.append(f"{label} face")
    # -- layer 3: the words themselves, when the face gave nothing --
    if expression == "neutral" and kind != "sfx":
        wlabel, wi, hits = words_expression(text, ctx.get("mood"))
        if wlabel and wlabel in EXPRESSIONS and wi > 0:
            expression, intensity = wlabel, wi
            t = EXPRESSIONS[wlabel]
            speed *= 1.0 + t.get("speed", 0.0) * wi
            gain_db += t.get("gain", 0.0) * wi
            pitch += t.get("pitch", 0.0) * wi
            tremolo += t.get("tremolo", 0.0) * wi
            grit += t.get("grit", 0.0) * wi
            breath += t.get("breath", 0.0) * wi
            pause_after += t.get("pause", 0.0) * wi
            if t.get("blend"):
                blend = {"tone": t["blend"], "weight": round(MAX_BLEND_WEIGHT * wi, 3)}
            cues.append(f"{wlabel} words: {', '.join(hits[:3])}")

    # -- balloon outline --
    outline = style.get("outline")
    if outline in OUTLINES and OUTLINES[outline]:
        t = OUTLINES[outline]
        speed *= 1.0 + t.get("speed", 0.0)
        gain_db += t.get("gain", 0.0)
        tremolo += t.get("tremolo", 0.0)
        grit += t.get("grit", 0.0)
        breath += t.get("breath", 0.0)
        if t.get("inner"):
            inner = True
        cues.append(f"{outline} outline")

    # -- lettering --
    text_scale = float(style.get("text_scale", 1.0) or 1.0)
    stroke = float(style.get("stroke_weight", 1.0) or 1.0)
    balloon_scale = float(ctx.get("balloon_scale", 1.0) or 1.0)
    if text_scale >= 1.3 and stroke >= 1.2:
        gain_db += min(4.0, 2.0 * (text_scale - 1.0) + 1.0)
        grit += 0.15
        cues.append("large heavy lettering")
    elif text_scale >= 1.3:
        gain_db += 1.5
        cues.append("large lettering")
    elif text_scale <= 0.75 and balloon_scale >= 1.2:
        gain_db -= 4.0
        speed *= 0.95
        breath += 0.2
        cues.append("small text in big balloon")
    elif text_scale <= 0.75:
        gain_db -= 2.0
        cues.append("small lettering")
    if style.get("wavy"):
        tremolo += 0.35
        gain_db -= 1.0
        cues.append("wavy lettering")
    if style.get("trembling"):
        tremolo += 0.5
        pitch += 0.5
        breath += 0.15
        cues.append("trembling lettering")
    if style.get("italic"):
        speed *= 0.97
        cues.append("italic lettering")
    emphasis = sorted({w.lower() for w in (style.get("bold_words") or []) if w})
    if emphasis:
        cues.append("bold words: " + ", ".join(emphasis))

    # -- scene mood and action --
    mood = ctx.get("mood")
    if mood in MOODS:
        t = MOODS[mood]
        speed *= 1.0 + t.get("speed", 0.0)
        gain_db += t.get("gain", 0.0)
        pitch += t.get("pitch", 0.0)
        pause_after += t.get("pause", 0.0)
        reverb += t.get("reverb", 0.0)
        cues.append(f"{mood} mood")
    action = float(ctx.get("action") or 0.0)
    if action > 0:
        speed *= 1.0 + 0.05 * _clampf(action, 0.0, 1.0)
        if action >= 0.5:
            cues.append("fast action panel")

    # -- acoustics --
    ac = ctx.get("acoustics") or {}
    space = ac.get("space")
    if space in SPACES:
        t = SPACES[space]
        size = _clampf(float(ac.get("size", 0.5) or 0.0), 0.0, 1.0)
        room = t["room"]
        reverb += t["reverb"] * (0.4 + 0.6 * size)
        grit += t.get("grit", 0.0)
        eq = t.get("eq")
        cues.append(f"{space} acoustics")
    if inner:
        # inner voice: not in the panel's space at all
        room, eq = "void", "void"
        reverb = max(reverb, THOUGHT_REVERB)

    out = {
        "speed": round(_clampf(speed, *_LIMITS["speed"]), 3),
        "gain_db": round(_clampf(gain_db, *_LIMITS["gain_db"]), 2),
        "pause_after": round(_clampf(pause_after, *_LIMITS["pause_after"]), 3),
        "reverb": round(_clampf(reverb, *_LIMITS["reverb"]), 3),
        "lift": question and not shout,
        "expression": expression,
        "intensity": round(intensity, 3),
        "room": room,
        "cues": cues,
        "pitch": round(_clampf(pitch, *_LIMITS["pitch"]), 2),
        "tremolo": round(_clampf(tremolo, *_LIMITS["tremolo"]), 3),
        "grit": round(_clampf(grit, *_LIMITS["grit"]), 3),
        "breath": round(_clampf(breath, *_LIMITS["breath"]), 3),
        "eq": eq,
        "blend": blend,
        "emphasis": emphasis,
        "source": "auto",
    }
    return out


def segments_for(text: str, emphasis: list[str]) -> list[dict]:
    """Split a line at bold words so each can be synthesised with its own
    speed and gain. Returns [{text, speed_mul, gain_db}]; a line with no
    bold word present is one segment, so normal lines stay one synthesis
    call. Adjacent bold words merge; punctuation stays with its word."""
    words = text.split()
    wanted = {w.lower() for w in emphasis if w}
    if not words or not wanted:
        return [{"text": text, "speed_mul": 1.0, "gain_db": 0.0}]

    def is_bold(w: str) -> bool:
        return re.sub(r"[^\w']+", "", w).lower() in wanted

    flags = [is_bold(w) for w in words]
    if not any(flags):
        return [{"text": text, "speed_mul": 1.0, "gain_db": 0.0}]
    segs: list[dict] = []
    cur: list[str] = []
    cur_bold = flags[0]
    for w, b in zip(words, flags):
        if b != cur_bold:
            segs.append((cur_bold, " ".join(cur)))  # type: ignore[arg-type]
            cur, cur_bold = [], b
        cur.append(w)
    segs.append((cur_bold, " ".join(cur)))  # type: ignore[arg-type]

    def spoken(b: bool, t: str, first: bool) -> str:
        # a bold word lettered in caps is read as a normal word; the
        # emphasis is carried by the segment's speed and gain
        if not b:
            return t
        words_out = [w.lower() if w.isupper() else w for w in t.split()]
        out = " ".join(words_out)
        return out[0].upper() + out[1:] if first and out else out

    return [
        {
            "text": spoken(b, t, k == 0),
            "speed_mul": BOLD_SPEED_MUL if b else 1.0,
            "gain_db": BOLD_GAIN_DB if b else 0.0,
        }
        for k, (b, t) in enumerate(segs)  # type: ignore[misc]
    ]


def apply(samples, sr: int, emotion: dict):
    """Apply the non-Kokoro part of an emotion (Kokoro already handled speed
    and voice blending at synthesis time): pitch, grit, tremolo, breath, the
    '?' brightness lift, room or inner-voice treatment, EQ, then gain.
    A dict from the original punctuation-only rules (no `room` key) takes
    the original thought-bubble echo path, unchanged."""
    from . import dsp

    out = samples
    if emotion.get("pitch"):
        out = dsp.pitch_shift(out, sr, float(emotion["pitch"]))
    if emotion.get("grit"):
        out = dsp.grit(out, float(emotion["grit"]))
    if emotion.get("tremolo"):
        out = dsp.tremolo(out, sr, float(emotion["tremolo"]))
    if emotion.get("breath"):
        out = dsp.breath(out, sr, float(emotion["breath"]))
    if emotion.get("lift"):
        out = dsp.pre_emphasis_lift(out, amount=0.2)
    eq = emotion.get("eq")
    reverb = float(emotion.get("reverb") or 0.0)
    if eq == "radio":
        out = dsp.radio_eq(out, sr, 1.0)
    elif eq == "vehicle":
        out = dsp.lowpass(out, sr, cutoff_hz=4000)
    if eq == "void":
        out = dsp.void_voice(out, sr, reverb)
    elif "room" in emotion:
        if reverb and emotion.get("room") in dsp.ROOMS:
            out = dsp.room_reverb(out, sr, emotion["room"], reverb)
    elif reverb:
        out = dsp.echo(out, sr, delay_s=0.07, decay=0.3 * reverb / 0.35, taps=3)
        out = dsp.lowpass(out, sr, cutoff_hz=3200)
    gain = emotion.get("gain_db", 0.0)
    if gain:
        out = dsp.gain_db(out, gain)
    return out
