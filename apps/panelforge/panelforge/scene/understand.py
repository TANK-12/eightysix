"""Rules that read a panel: mood, action, character expression, acoustics.

No model does this yet, so every value comes from plain rules over what
detect and scene measured (speed lines, edges, colour, balloon kinds, the
lettering style, punctuation). Each result carries `why`/`conf` so the
editor can show the reasoning and Emerson can overrule it. When a face
expression model earns its place it slots in here.
"""

from __future__ import annotations

MOODS = ("tense", "calm", "action", "sad", "comic", "mystery")
EXPRESSIONS = (
    "neutral",
    "angry",
    "happy",
    "sad",
    "scared",
    "surprised",
    "smug",
    "pained",
    "determined",
)
SPACES = ("small-room", "hall", "outdoor", "vehicle", "comms", "void")


def _kinds(bubbles: list[dict]) -> dict[str, int]:
    out: dict[str, int] = {}
    for b in bubbles:
        out[b.get("kind", "speech")] = out.get(b.get("kind", "speech"), 0) + 1
    return out


def action_level(rec: dict, bubbles: list[dict]) -> float:
    """0..1: how much motion the panel implies."""
    score = 0.0
    sl = rec.get("speed_lines") or {}
    if sl.get("present"):
        score += 0.45 * min(1.0, float(sl.get("strength", 1.0)))
    edges = float((rec.get("stats") or {}).get("edges", 0.0))
    score += min(0.3, edges * 2.0)
    kinds = _kinds(bubbles)
    score += 0.15 * min(2, kinds.get("shout", 0)) + 0.1 * min(2, kinds.get("sfx", 0))
    for c in rec.get("characters") or []:
        if c.get("area_frac", 0) > 0.45:
            score += 0.05
    return round(min(1.0, score), 3)


def mood(rec: dict, bubbles: list[dict], action: float) -> tuple[str, list[str]]:
    st = rec.get("stats") or {}
    light = float(st.get("lightness", 0.5))
    warmth = float(st.get("warmth", 0.0))
    red = float(st.get("red", 0.0))
    kinds = _kinds(bubbles)
    texts = " ".join(b.get("text", "") for b in bubbles)
    why: list[str] = []
    if action >= 0.55 or kinds.get("shout", 0) >= 2:
        why.append("speed lines or shouting")
        return "action", why
    if kinds.get("shout", 0) == 1 and light < 0.5:
        why.append("a shout in a dark panel")
        return "tense", why
    if "..." in texts and light < 0.55:
        why.append("trailing dots in a dark panel")
        return "sad", why
    if kinds.get("thought", 0) or (light < 0.3 and not bubbles):
        why.append("thought bubble or very dark panel")
        return "mystery", why
    if "!" in texts and "?" in texts or texts.count("!") >= 3 and light > 0.6:
        why.append("many exclamation marks in a bright panel")
        return "comic", why
    if red > 0.15 or (light < 0.42 and warmth < 0):
        why.append("red or cold dark colours")
        return "tense", why
    why.append("even light, no strong cues")
    return "calm", why


def expression(char: dict, spoken: list[dict], panel_mood: str, action: float) -> dict:
    """Expression of one character from what they say and the panel mood.

    `spoken` are this character's bubbles in the panel. Confidence stays
    low (0.35 to 0.6) because no face model is involved yet."""
    label, intensity, conf, why = "neutral", 0.2, 0.35, []
    kinds = _kinds(spoken)
    text = " ".join(b.get("text", "") for b in spoken)
    styles = [b.get("style") or {} for b in spoken]
    loud = any(
        s.get("stroke_weight", 1.0) >= 1.4 or s.get("text_scale", 1.0) >= 1.4
        for s in styles
    )
    shaky = any(s.get("wavy") or s.get("trembling") for s in styles)
    if kinds.get("shout"):
        label, intensity, conf = "angry", 0.75, 0.55
        why.append("shout balloon")
        if "?" in text:
            label = "surprised"
            why.append("question in a shout")
    elif kinds.get("whisper") or shaky:
        label, intensity, conf = "scared", 0.6, 0.5
        why.append("whisper balloon or shaky lettering")
    elif "!" in text and "?" in text:
        label, intensity, conf = "surprised", 0.6, 0.5
        why.append("'!?' in the line")
    elif text.count("!") >= 1 and loud:
        label, intensity, conf = "angry", 0.6, 0.5
        why.append("heavy lettering with an exclamation")
    elif "..." in text and panel_mood in ("sad", "mystery"):
        label, intensity, conf = "sad", 0.5, 0.45
        why.append("trailing dots in a sad panel")
    elif any(w in text.lower() for w in ("haha", "heh", "hah")):
        label, intensity, conf = "happy", 0.6, 0.55
        why.append("laughter in the line")
    elif panel_mood == "action" and action >= 0.5:
        label, intensity, conf = "determined", 0.5, 0.4
        why.append("action panel")
    elif panel_mood == "tense":
        label, intensity, conf = "determined", 0.35, 0.35
        why.append("tense panel")
    if loud and label != "neutral":
        intensity = min(1.0, intensity + 0.15)
        why.append("large or heavy lettering")
    return {"label": label, "intensity": round(intensity, 2), "conf": conf, "why": why}


def acoustics(rec: dict, bubbles: list[dict], panel: dict) -> dict:
    """Where the voices sound like they are: room, hall, outdoors, comms, void."""
    st = rec.get("stats") or {}
    light = float(st.get("lightness", 0.5))
    chars = rec.get("characters") or []
    biggest = max([c.get("area_frac", 0.0) for c in chars] + [0.0])
    styles = [b.get("style") or {} for b in bubbles]
    why: list[str] = []
    if any(
        s.get("outline") == "rect" and b.get("kind") in ("speech", "shout")
        for s, b in zip(styles, bubbles)
    ):
        why.append("square-edged speech balloon")
        return {"space": "comms", "size": 0.2, "why": why}
    if rec.get("background") is None and light < 0.2:
        why.append("black background")
        return {"space": "void", "size": 0.9, "why": why}
    top = float(st.get("top_lightness", light))
    if light > 0.62 and top >= light and biggest < 0.5:
        why.append("bright open scene")
        return {"space": "outdoor", "size": 0.8, "why": why}
    if panel.get("kind") == "splash" and biggest < 0.2:
        why.append("wide shot with small figures")
        return {"space": "hall", "size": 0.7, "why": why}
    why.append("close framing")
    return {
        "space": "small-room",
        "size": round(max(0.1, 0.5 - biggest * 0.4), 2),
        "why": why,
    }
