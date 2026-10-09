"""
Tolerant parsing of whatever a small local model actually returns.

Tiny quantised models (0.6B-4B) rarely obey "return strict JSON". They wrap
answers in <think> blocks, add prose before/after, use markdown fences, single
quotes, trailing commas, unquoted keys, or return a *list* where a dict was
asked for (or vice-versa). This module turns all of that into the shapes the
rest of NovelForge expects, and never raises -- callers get a best-effort
result or an empty container.

Public helpers
--------------
    strip_reasoning(text)          -> text with <think>/<thinking>/channel junk removed
    extract_json(text)             -> dict | list | None
    as_text_list(x)                -> list[str]        (bullets/numbers stripped)
    as_entry_dict(x)               -> dict[str, dict]  ({"Name": {...}})
    coerce_world(obj_or_text)      -> normalised world dict
    coerce_codex_update(obj_text)  -> normalised codex-delta dict
    parse_outline(text, target)    -> list[str]  (one chapter goal per item)
    parse_beats(text, want)        -> list[str]  (scene beats for one chapter)
"""

import re
import ast
import json


# --------------------------------------------------------------------------
# 1. Cleaning
# --------------------------------------------------------------------------
_REASONING_BLOCKS = [
    r"<think>.*?</think>",
    r"<thinking>.*?</thinking>",
    r"<reason(?:ing)?>.*?</reason(?:ing)?>",
    r"◁think▷.*?◁/think▷",
    r"<\|thinking\|>.*?<\|/thinking\|>",
    r"<\|channel\|>analysis.*?<\|channel\|>final",
]


def strip_reasoning(text):
    """Remove chain-of-thought / analysis channels that reasoning-tuned models
    (VibeThinker, Qwen3 'thinking', GLM, gpt-oss channels) emit before the
    real answer. Also strips an unterminated leading <think> ... with no close.
    """
    if not text:
        return ""
    t = text
    for pat in _REASONING_BLOCKS:
        t = re.sub(pat, " ", t, flags=re.DOTALL | re.IGNORECASE)
    # Unterminated opener: "<think> blah blah" with the close eaten by a token cap.
    t = re.sub(r"<think(?:ing)?>.*$", " ", t, flags=re.DOTALL | re.IGNORECASE)
    # Leftover lone tags.
    t = re.sub(r"</?(think|thinking|reason|reasoning|analysis|final|channel)[^>]*>", " ", t,
               flags=re.IGNORECASE)
    return t.strip()


def _strip_fences(text):
    t = text.strip()
    # ```json ... ```  or  ``` ... ```
    m = re.search(r"```(?:json|JSON)?\s*(.*?)```", t, flags=re.DOTALL)
    if m:
        return m.group(1).strip()
    t = re.sub(r"^```(?:json|JSON)?", "", t).strip()
    t = re.sub(r"```$", "", t).strip()
    return t


_SMART = {
    "“": '"', "”": '"', "‘": "'", "’": "'",
    "–": "-", "—": "-", " ": " ", "﻿": "",
}


def _desmart(text):
    for a, b in _SMART.items():
        text = text.replace(a, b)
    return text


# --------------------------------------------------------------------------
# 2. Balanced-bracket scanning (regex can't match nested braces)
# --------------------------------------------------------------------------
def _find_balanced(text, open_ch, close_ch):
    """Yield every top-level balanced (start,end) slice for the given brackets,
    respecting strings so a '}' inside "..." doesn't close the object."""
    spans = []
    depth = 0
    start = None
    in_str = False
    esc = False
    quote = ""
    for i, ch in enumerate(text):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == quote:
                in_str = False
            continue
        if ch in ('"', "'"):
            in_str = True
            quote = ch
            continue
        if ch == open_ch:
            if depth == 0:
                start = i
            depth += 1
        elif ch == close_ch and depth:
            depth -= 1
            if depth == 0 and start is not None:
                spans.append((start, i + 1))
                start = None
    return spans


def _light_repairs(chunk):
    """A few forgiving fixes tiny models routinely need."""
    c = chunk
    c = re.sub(r",\s*([}\]])", r"\1", c)                       # trailing commas
    c = re.sub(r"(?<![\\\"])'([^'\"]*?)'(\s*[:,}\]])", r'"\1"\2', c)  # 'val' -> "val"
    c = re.sub(r"([{,]\s*)([A-Za-z_][A-Za-z0-9_ \-]*?)(\s*):", r'\1"\2"\3:', c)  # bare keys
    c = re.sub(r":\s*(True|False|None)\b",
               lambda m: ": " + {"True": "true", "False": "false", "None": "null"}[m.group(1)], c)
    c = re.sub(r"\bNaN\b", "null", c)
    return c


def _try_load(chunk):
    for candidate in (chunk, _light_repairs(chunk)):
        try:
            return json.loads(candidate)
        except Exception:
            pass
    try:
        val = ast.literal_eval(chunk)
        if isinstance(val, (dict, list)):
            return val
    except Exception:
        pass
    return None


def extract_json(text):
    """Return the most plausible dict/list embedded in `text`, or None."""
    if not text:
        return None
    t = _desmart(strip_reasoning(text))
    t = _strip_fences(t)

    direct = _try_load(t.strip())
    if isinstance(direct, (dict, list)):
        return direct

    candidates = []
    for oc, cc in (("{", "}"), ("[", "]")):
        for a, b in _find_balanced(t, oc, cc):
            candidates.append(t[a:b])
    # Prefer the longest well-formed candidate (usually the real payload).
    candidates.sort(key=len, reverse=True)
    for chunk in candidates:
        val = _try_load(chunk)
        if isinstance(val, (dict, list)):
            return val
    return None


# --------------------------------------------------------------------------
# 3. Shape coercion
# --------------------------------------------------------------------------
_BULLET = re.compile(r"^\s*(?:[-*••]|\d+[.)]|\(\d+\)|[a-z][.)])\s+", re.IGNORECASE)


def as_text_list(x):
    """Anything -> list of clean strings."""
    out = []
    if x is None:
        return out
    if isinstance(x, str):
        parts = re.split(r"[\r\n]+|(?<=[.;])\s{2,}", x)
        for p in parts:
            p = _BULLET.sub("", p).strip(" -\t")
            if p:
                out.append(p)
        return out
    if isinstance(x, dict):
        for k, v in x.items():
            if isinstance(v, str) and v.strip():
                out.append(f"{k}: {v.strip()}")
            else:
                out.append(str(k))
        return out
    if isinstance(x, (list, tuple, set)):
        for item in x:
            if isinstance(item, str):
                s = _BULLET.sub("", item).strip()
                if s:
                    out.append(s)
            elif isinstance(item, dict):
                s = (item.get("text") or item.get("fact") or item.get("rule")
                     or item.get("description") or item.get("desc")
                     or item.get("name") or item.get("title"))
                if s:
                    out.append(str(s).strip())
                else:
                    out.append("; ".join(f"{k}: {v}" for k, v in item.items()))
            elif item is not None:
                out.append(str(item))
    return out


_NAME_KEYS = ("name", "title", "id", "label", "character", "who")
_DESC_KEYS = ("desc", "description", "summary", "bio", "about", "detail", "details", "profile")
_TRAIT_KEYS = ("traits", "personality", "characteristics", "qualities", "tags")
_REL_KEYS = ("relationships", "relations", "connections", "ties")
_STATUS_KEYS = ("status", "state", "condition", "arc")


def _first(d, keys, default=""):
    for k in keys:
        if k in d and d[k] not in (None, "", [], {}):
            return d[k]
    return default


def _norm_traits(v):
    if isinstance(v, str):
        parts = re.split(r"[,;\n]+", v) if "," in v or ";" in v else as_text_list(v)
        return [p.strip() for p in parts if p.strip()]
    if isinstance(v, (list, tuple, set)):
        out = []
        for s in v:
            for p in re.split(r"[,;]+", str(s)):
                p = p.strip()
                if p:
                    out.append(p)
        return out
    if isinstance(v, dict):
        return [f"{k}: {val}" for k, val in v.items()]
    return []


def _norm_rels(v):
    out = {}
    if isinstance(v, dict):
        for k, val in v.items():
            if isinstance(val, dict):
                val = _first(val, ("relation", "relationship", "type", "desc", "description")) or \
                      "; ".join(f"{a}={b}" for a, b in val.items())
            if k and val:
                out[str(k).strip()] = str(val).strip()
    elif isinstance(v, (list, tuple)):
        for item in v:
            if isinstance(item, dict):
                who = _first(item, ("with", "name", "who", "target", "other", "person"))
                rel = _first(item, ("relation", "relationship", "type", "desc", "description", "note"))
                if who and rel:
                    out[str(who).strip()] = str(rel).strip()
            elif isinstance(item, str) and ":" in item:
                who, rel = item.split(":", 1)
                out[who.strip()] = rel.strip()
    elif isinstance(v, str):
        for line in as_text_list(v):
            if ":" in line:
                who, rel = line.split(":", 1)
                out[who.strip()] = rel.strip()
    return out


def _norm_entry(v):
    """Normalise one character/location/faction record."""
    if isinstance(v, str):
        return {"desc": v.strip(), "traits": [], "relationships": {}, "status": ""}
    if not isinstance(v, dict):
        return {"desc": str(v), "traits": [], "relationships": {}, "status": ""}
    return {
        "desc": str(_first(v, _DESC_KEYS)).strip(),
        "traits": _norm_traits(_first(v, _TRAIT_KEYS, [])),
        "relationships": _norm_rels(_first(v, _REL_KEYS, {})),
        "status": str(_first(v, _STATUS_KEYS)).strip(),
    }


def as_entry_dict(x):
    """dict|list|str -> {"Name": {desc, traits, relationships, status}}."""
    out = {}
    if not x:
        return out
    if isinstance(x, dict):
        # Could be {"Name": {...}} already, or a single flat record.
        looks_flat = any(k in x for k in _NAME_KEYS) and any(
            k in x for k in _DESC_KEYS + _TRAIT_KEYS)
        if looks_flat:
            name = str(_first(x, _NAME_KEYS, "Unknown")).strip()
            out[name] = _norm_entry(x)
            return out
        for k, v in x.items():
            name = str(k).strip()
            if name:
                out[name] = _norm_entry(v)
        return out
    if isinstance(x, (list, tuple)):
        for item in x:
            if isinstance(item, dict):
                name = str(_first(item, _NAME_KEYS, "")).strip()
                if not name:
                    continue
                out[name] = _norm_entry(item)
            elif isinstance(item, str):
                s = item.strip()
                if not s:
                    continue
                if " - " in s or ": " in s:
                    sep = " - " if " - " in s else ": "
                    name, desc = s.split(sep, 1)
                    out[name.strip()] = {"desc": desc.strip(), "traits": [],
                                         "relationships": {}, "status": ""}
                else:
                    out[s] = {"desc": "", "traits": [], "relationships": {}, "status": ""}
    return out


# Key aliases the models invent for the top-level world dict.
_ALIAS = {
    "characters": ("characters", "cast", "people", "protagonists", "dramatis_personae", "chars"),
    "locations": ("locations", "places", "settings", "locales", "geography"),
    "factions": ("factions", "organizations", "organisations", "groups", "guilds", "orders"),
    "facts": ("facts", "rules", "lore", "worldbuilding", "world_rules", "world_facts",
              "pinned_facts", "canon", "magic_system", "notes"),
    "genre": ("genre", "theme", "category"),
    "protagonist": ("protagonist", "hero", "main_character", "mc", "lead"),
    "plot": ("plot", "premise", "conflict", "synopsis", "logline", "story"),
}


def _alias_get(d, canonical):
    for k in _ALIAS[canonical]:
        if k in d and d[k] not in (None, "", [], {}):
            return d[k]
    # case-insensitive fallback
    low = {str(k).lower(): v for k, v in d.items()}
    for k in _ALIAS[canonical]:
        if k in low and low[k] not in (None, "", [], {}):
            return low[k]
    return None


def coerce_world(obj_or_text):
    """Normalise a Free-Rein world response into the canonical shape.

    Returns keys: genre, protagonist, plot, pinned_facts (str),
    characters/locations/factions (dict-of-entries), facts (list[str]).
    """
    data = obj_or_text if isinstance(obj_or_text, dict) else extract_json(obj_or_text)
    if not isinstance(data, dict):
        # Last resort: try to scrape "CHARACTER: ..." style loose text.
        data = _loose_world_from_text(obj_or_text if isinstance(obj_or_text, str) else "")

    facts_raw = _alias_get(data, "facts")
    facts = as_text_list(facts_raw)

    world = {
        "genre": str(_alias_get(data, "genre") or "").strip(),
        "protagonist": _stringify(_alias_get(data, "protagonist")),
        "plot": _stringify(_alias_get(data, "plot")),
        "pinned_facts": "\n".join(f"- {x}" for x in facts) if facts else "",
        "characters": as_entry_dict(_alias_get(data, "characters")),
        "locations": as_entry_dict(_alias_get(data, "locations")),
        "factions": as_entry_dict(_alias_get(data, "factions")),
        "facts": facts,
    }
    return world


def coerce_codex_update(obj_or_text):
    data = obj_or_text if isinstance(obj_or_text, dict) else extract_json(obj_or_text)
    if not isinstance(data, dict):
        return {}
    return {
        "characters": as_entry_dict(_alias_get(data, "characters")),
        "locations": as_entry_dict(_alias_get(data, "locations")),
        "factions": as_entry_dict(_alias_get(data, "factions")),
        "facts": as_text_list(_alias_get(data, "facts")),
    }


def _stringify(v):
    if v is None:
        return ""
    if isinstance(v, str):
        return v.strip()
    if isinstance(v, dict):
        return "; ".join(f"{k}: {val}" for k, val in v.items())
    if isinstance(v, (list, tuple)):
        return " ".join(str(x) for x in v)
    return str(v)


def _loose_world_from_text(text):
    """Parse 'KEY: value' / 'CHARACTER: name | desc | traits' loose fallbacks."""
    if not text:
        return {}
    text = strip_reasoning(text)
    out = {"characters": {}, "locations": {}, "factions": {}, "facts": []}
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        m = re.match(r"(?i)^(genre|protagonist|plot|premise|conflict)\s*[:\-]\s*(.+)$", line)
        if m:
            key = m.group(1).lower()
            key = {"premise": "plot", "conflict": "plot"}.get(key, key)
            out[key] = m.group(2).strip()
            continue
        m = re.match(r"(?i)^(character|hero|npc|ally|antagonist|villain)\s*[:\-]\s*(.+)$", line)
        if m:
            parts = [p.strip() for p in re.split(r"\s*[|;]\s*", m.group(2))]
            name = parts[0]
            desc = parts[1] if len(parts) > 1 else ""
            traits = as_text_list(parts[2]) if len(parts) > 2 else []
            if name:
                out["characters"][name] = {"desc": desc, "traits": traits,
                                           "relationships": {}, "status": ""}
            continue
        m = re.match(r"(?i)^(location|place|setting)\s*[:\-]\s*(.+)$", line)
        if m:
            parts = [p.strip() for p in re.split(r"\s*[|;]\s*", m.group(2))]
            out["locations"][parts[0]] = {"desc": parts[1] if len(parts) > 1 else ""}
            continue
        m = re.match(r"(?i)^(faction|org(?:anization)?|group|guild)\s*[:\-]\s*(.+)$", line)
        if m:
            parts = [p.strip() for p in re.split(r"\s*[|;]\s*", m.group(2))]
            out["factions"][parts[0]] = {"desc": parts[1] if len(parts) > 1 else ""}
            continue
        m = re.match(r"(?i)^(fact|rule|lore)\s*[:\-]\s*(.+)$", line)
        if m:
            out["facts"].append(m.group(2).strip())
    return out


# --------------------------------------------------------------------------
# 4. Outlines and scene beats
# --------------------------------------------------------------------------
_CH_LINE = re.compile(
    r"^\s*(?:#+\s*)?(?:\*\*\s*)?(?:chapter|ch\.?|part|episode|ep\.?)\s*\d+\b",
    re.IGNORECASE)
_NUM_LINE = re.compile(r"^\s*(\d+)\s*[.):\-—]\s+(.*\S)")


def _outline_from_json(data):
    items = []
    if isinstance(data, dict):
        for key in ("chapters", "outline", "chapter_list", "beats", "plan"):
            if isinstance(data.get(key), list):
                data = data[key]
                break
        else:
            # dict keyed by chapter number/name
            data = list(data.values())
    if isinstance(data, list):
        for it in data:
            if isinstance(it, str) and it.strip():
                items.append(it.strip())
            elif isinstance(it, dict):
                title = _first(it, ("title", "name", "heading"))
                summary = _first(it, ("summary", "goal", "desc", "description", "event", "synopsis"))
                beats = it.get("beats") or it.get("scenes")
                piece = " -- ".join(p for p in (str(title).strip(), str(summary).strip()) if p)
                if isinstance(beats, list) and beats:
                    piece += " | beats: " + "; ".join(str(b) for b in beats)
                if piece.strip():
                    items.append(piece.strip())
    return items


def parse_outline(text, target=0):
    """Return a list of one-line chapter goals, however the model formatted it."""
    if not text:
        return []
    data = extract_json(text)
    items = _outline_from_json(data) if data is not None else []

    if not items:
        cleaned = strip_reasoning(text)
        lines = [ln.rstrip() for ln in cleaned.splitlines()]
        buf = []
        cur = None
        for ln in lines:
            s = ln.strip()
            if not s:
                continue
            if _CH_LINE.match(s) or _NUM_LINE.match(s) or _BULLET.match(s):
                if cur:
                    buf.append(cur.strip())
                cur = _BULLET.sub("", s)
                cur = re.sub(r"^\s*(?:#+\s*)?(?:\*\*\s*)?", "", cur)
                cur = re.sub(r"\*\*", "", cur)
            elif cur is not None:
                cur += " " + s            # continuation of a wrapped line
        if cur:
            buf.append(cur.strip())
        items = [b for b in buf if len(b) > 3]

    if not items:
        # absolute fallback: sentence split
        items = [s.strip() for s in re.split(r"(?<=[.!?])\s+", strip_reasoning(text)) if len(s.strip()) > 20]

    # Strip a leading "Chapter N:" / "**Beat N:**" / "Scene N -" label.
    out = []
    for it in items:
        it = re.sub(r"^\s*\*{0,2}\s*(?:chapter|ch\.?|part|episode|ep\.?|scene|beat)\s*\d+"
                    r"\s*\*{0,2}\s*[:.\-—)]*\s*\*{0,2}\s*", "", it, flags=re.IGNORECASE).strip()
        it = re.sub(r"^\s*\*{0,2}\s*\d+\s*[:.\-—)]\s*", "", it).strip()
        it = it.strip("*").strip()
        if it:
            out.append(it)

    if target and len(out) > target:
        out = out[:target]
    return out


def parse_beats(text, want=4):
    """Scene beats for a single chapter. Same tolerance as parse_outline but
    guarantees at least `want` items by synthesising generic beats if short."""
    beats = parse_outline(text, target=0)
    beats = [b for b in beats if len(b) > 3][:max(want * 2, 8)]
    if len(beats) < want:
        skeleton = [
            "Open the chapter in motion: re-establish where things stand and land the reader in a concrete scene.",
            "Escalate: the chapter's central problem sharpens and forces the protagonist to act.",
            "Turn: a choice, revelation or reversal changes what the protagonist wants or believes.",
            "Fallout and hook: show the cost of the turn and end on a pull into the next chapter.",
        ]
        i = 0
        while len(beats) < want:
            beats.append(skeleton[i % len(skeleton)])
            i += 1
    return beats[:want]
