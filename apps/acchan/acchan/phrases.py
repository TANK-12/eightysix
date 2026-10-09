"""Natural phrasing for spoken commands, read from the one tool registry.

Tools declare `phrases=[...]` on their own `@tool(...)`: examples like
"turn it down to {percent}" where a `{slot}` is a parameter name, or a
`(phrase, fixed_args)` pair such as `("skip this song", {"action": "next"})`.
`match(text)` turns an utterance into `(tool, args, confidence)` or None.

Stdlib only. An utterance is normalised (lower case, contractions opened,
fillers like "um", "please", "could you", "hey acchan" and articles dropped)
and then tried against every phrase: an exact pattern match scores 1.0, a
close spelling of a slot-free phrase scores its difflib ratio. Anything under
THRESHOLD is not a command; chit-chat and questions fall through to the model.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass

from . import registry

THRESHOLD = 0.85
MAX_SLOT_WORDS = 5

CONTRACTIONS = {
    "what's": "what is",
    "whats": "what is",
    "how's": "how is",
    "it's": "it is",
    "i'm": "i am",
    "who's": "who is",
    "that's": "that is",
    "let's": "let us",
    "gonna": "going to",
    "wanna": "want to",
}
# Said before or after a command without changing it. Longest first.
LEAD_FILLERS = [
    "hey acchan",
    "ok acchan",
    "okay acchan",
    "acchan",
    "hey jan",
    "jan",
    "um",
    "uh",
    "erm",
    "hmm",
    "so",
    "okay",
    "ok",
    "hey",
    "please",
    "could you please",
    "can you please",
    "would you please",
    "could you",
    "can you",
    "would you",
    "will you",
    "i want you to",
    "i need you to",
    "i'd like you to",
    "id like you to",
    "go ahead and",
    "just",
    "quickly",
]
TAIL_FILLERS = ["please", "for me", "thanks", "thank you", "now", "right now", "acchan"]
ARTICLES = {"the", "a", "an", "my", "some"}
# A slot that starts with one of these is talk, not a name ("open up to me").
BAD_SLOT_START = {
    "your",
    "you",
    "me",
    "up",
    "about",
    "to",
    "it",
    "that",
    "this",
    "with",
    "on",
    "if",
    "why",
    "how",
    "what",
    "i",
    "we",
    "they",
}


@dataclass
class Phrase:
    tool: str
    text: str  # normalised template
    fixed: dict
    pattern: re.Pattern
    slots: list[str]
    literal_words: int


def normalize(text: str) -> str:
    """Lower case, contractions opened, punctuation (but +, -, %, digits and
    dots inside words) dropped, fillers and articles removed."""
    t = text.lower().replace("’", "'")
    for short, full in CONTRACTIONS.items():
        t = re.sub(rf"(?<![\w']){re.escape(short)}(?![\w'])", full, t)
    t = re.sub(r"[^\w\s+\-%.'{}]", " ", t)
    t = re.sub(r"(?<!\w)[.'](?!\w)|[.'](?=\s|$)", " ", t)
    words = t.split()
    changed = True
    while changed and words:
        changed = False
        for filler in sorted(LEAD_FILLERS, key=len, reverse=True):
            parts = filler.split()
            if words[: len(parts)] == parts and len(words) > len(parts):
                words = words[len(parts) :]
                changed = True
                break
        for filler in sorted(TAIL_FILLERS, key=len, reverse=True):
            parts = filler.split()
            if words[-len(parts) :] == parts and len(words) > len(parts):
                words = words[: -len(parts)]
                changed = True
                break
    return " ".join(w for w in words if w not in ARTICLES)


def _compile(tool: str, entry) -> Phrase | None:
    if isinstance(entry, (tuple, list)) and len(entry) == 2:
        text, fixed = str(entry[0]), dict(entry[1])
    elif isinstance(entry, str):
        text, fixed = entry, {}
    else:
        return None
    norm = normalize(text)
    slots = re.findall(r"\{(\w+)\}", norm)
    regex = ""
    for piece in re.split(r"(\{\w+\})", norm):
        if re.fullmatch(r"\{\w+\}", piece):
            regex += rf"(?P<{piece[1:-1]}>.+?)"
        else:
            regex += re.escape(piece)
    literal = len(re.sub(r"\{\w+\}", " ", norm).split())
    return Phrase(tool, norm, fixed, re.compile(rf"^{regex}$"), slots, literal)


def phrases() -> list[Phrase]:
    """Every declared phrase, most specific (most literal words) first."""
    found = []
    for name, entry in registry.TOOLS.items():
        if entry.risky:
            continue
        for raw in entry.phrases:
            compiled = _compile(name, raw)
            if compiled:
                found.append(compiled)
    found.sort(key=lambda p: (-p.literal_words, len(p.slots)))
    return found


def _slot_value(tool: str, slot: str, value: str):
    """A cleaned slot value, or None when it does not fit the parameter."""
    value = value.strip(" .,!?")
    words = value.split()
    if not words or len(words) > MAX_SLOT_WORDS or words[0] in BAD_SLOT_START:
        return None
    kind = registry.TOOLS[tool].properties.get(slot, {}).get("type", "string")
    if kind in ("integer", "number") or slot in ("percent", "workspace"):
        number = re.sub(r"\s*(%|percent|per cent)$", "", value)
        if not re.fullmatch(r"[+-]?\d{1,3}", number):
            return None
        return int(number) if kind == "integer" else number
    return value


def match(text: str) -> tuple[str, dict, float] | None:
    """(tool, args, confidence) for a spoken command, or None."""
    said = normalize(text)
    if not said or len(said.split()) > 12:
        return None
    best: tuple[str, dict, float] | None = None
    for phrase in phrases():
        if phrase.tool not in registry.TOOLS:
            continue
        found = phrase.pattern.match(said)
        if found:
            args = dict(phrase.fixed)
            ok = True
            for slot in phrase.slots:
                value = _slot_value(phrase.tool, slot, found.group(slot))
                if value is None:
                    ok = False
                    break
                args[slot] = value
            if ok:
                return phrase.tool, args, 1.0
            continue
        if phrase.slots:
            continue
        ratio = difflib.SequenceMatcher(None, said, phrase.text).ratio()
        if ratio >= THRESHOLD and (best is None or ratio > best[2]):
            best = (phrase.tool, dict(phrase.fixed), round(ratio, 3))
    return best
