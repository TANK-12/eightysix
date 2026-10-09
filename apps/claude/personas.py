"""Personas: who speaks, and which avatar shows, for each kind of task.

Emerson picked mood-based switching on 2026-09-24 (the full personality and
his answers are in ~/.claude/self/PERSONALITY.md). Each persona is one file
in personas/<id>.json: name, the moods it owns, its avatar (a Live2D model
or a generated puppet in shared/avatars), a Kokoro voice, which motions it
plays for each status, and a short prompt fragment.

The mood is picked from the user's message (``pick_mood``). The roster goes
into the system prompt once, and each message carries a one-line tag naming
the persona for that reply. Swapping the system prompt per message would
throw away Claude Code's prompt cache and cost tokens every turn.

Emerson's own choices (a pinned persona, avatar and voice swaps, whether the
downtime persona is Yui, Ren or alternates) live in <data>/personas.json,
over the registry files.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

APP = Path(__file__).resolve().parent
REGISTRY = APP / "personas"

MOODS = ("default", "plan", "build", "fix", "status", "downtime", "check")

# First match wins, so the order matters: a bug report that says "make" is a fix.
MOOD_RULES: list[tuple[str, re.Pattern]] = [
    (
        "fix",
        re.compile(
            r"not working|doesn'?t work|dont work|isn'?t working|broke|broken|\bbug|"
            r"\berror|traceback|exception|crash|fail|\bfix|bloody|stuck|won'?t|cant open|"
            r"white on white",
            re.I,
        ),
    ),
    (
        "status",
        re.compile(
            r"tl;?dr|how'?s it going|hows it|how is it going|is (it|everything|that) done|are you done|"
            r"what have you (done|made)|status|progress|how much (longer|power)|"
            r"how long|what'?s using|whats usin",
            re.I,
        ),
    ),
    (
        "build",
        re.compile(
            r"\bmake\b|\bbuild|\badd\b|more and more|\bnew app|feature|create|"
            r"tons of tokens|sessions? worth|go (do|build)|\bimprove",
            re.I,
        ),
    ),
    (
        "downtime",
        re.compile(
            r"\bbored|\bchill|\blol\b|haha|good ?night|how are you|\bflirt|\bcute\b|"
            r"just chat|talk to me|^(hi|hey|hello|yo)\b",
            re.I,
        ),
    ),
    (
        "check",
        re.compile(
            r"are you sure|\b(you|u) sure\b|"
            r"is (that|it|this) (true|right|correct|accurate)|thats (true|right)|"
            r"double.?check|fact.?check|\b(confirm|verify) (that|this|it)\b|"
            r"\b(your|any|cite|with|give me|what are the|got) sources?\b(?![/._-])|"
            r"look (it )?up|\bresearch(ing)?\b|how do you know|prove it|citation",
            re.I,
        ),
    ),
    (
        "plan",
        re.compile(r"\bplan\b|should i|what do you think|idea|which (is|one)", re.I),
    ),
]


def pick_mood(text: str) -> str:
    for mood, pattern in MOOD_RULES:
        if pattern.search(text or ""):
            return mood
    return "default"


def load(registry: Path = REGISTRY) -> dict[str, dict]:
    personas: dict[str, dict] = {}
    for path in sorted(registry.glob("*.json")):
        try:
            data = json.loads(path.read_text())
        except ValueError:
            continue
        data.setdefault("id", path.stem)
        personas[data["id"]] = data
    return personas


class Personas:
    """The registry plus Emerson's overrides, kept in one JSON file."""

    def __init__(self, data_dir: Path, registry: Path = REGISTRY):
        self.path = Path(data_dir) / "personas.json"
        self.registry = registry
        self._turn = 0

    def prefs(self) -> dict:
        try:
            data = json.loads(self.path.read_text())
        except (OSError, ValueError):
            data = {}
        data.setdefault("pinned", "auto")  # "auto" or a persona id
        data.setdefault("downtime", "alternate")  # a persona id or "alternate"
        data.setdefault("speak", False)
        data.setdefault("overrides", {})  # id -> {avatar, voice}
        data.setdefault("enabled", True)
        data.setdefault("avatar", False)  # the animated stage; off until turned on
        return data

    def save_prefs(self, changes: dict) -> dict:
        prefs = self.prefs()
        everyone = self.all()
        if "pinned" in changes:
            pinned = str(changes["pinned"])
            if pinned != "auto" and pinned not in everyone:
                raise ValueError("No such persona")
            prefs["pinned"] = pinned
        if "downtime" in changes:
            downtime = str(changes["downtime"])
            if downtime != "alternate" and downtime not in everyone:
                raise ValueError("No such persona")
            prefs["downtime"] = downtime
        for flag in ("speak", "enabled", "avatar"):
            if flag in changes:
                prefs[flag] = bool(changes[flag])
        for pid, override in (changes.get("overrides") or {}).items():
            if pid not in everyone or not isinstance(override, dict):
                raise ValueError("No such persona")
            clean = prefs["overrides"].setdefault(pid, {})
            avatar = override.get("avatar")
            if avatar is not None:
                if avatar.get("kind") not in ("live2d", "puppet") or not re.match(
                    r"^[a-z0-9_\-]{1,48}$", str(avatar.get("id", ""))
                ):
                    raise ValueError("An avatar is {kind: live2d|puppet, id}")
                clean["avatar"] = {"kind": avatar["kind"], "id": avatar["id"]}
            if override.get("voice") is not None:
                clean["voice"] = re.sub(r"[^a-z_]", "", str(override["voice"]))[:24]
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(prefs, indent=1))
        return prefs

    def all(self) -> dict[str, dict]:
        """Registry personas with Emerson's avatar and voice swaps applied."""
        personas = load(self.registry)
        try:
            overrides = json.loads(self.path.read_text()).get("overrides", {})
        except (OSError, ValueError):
            overrides = {}
        for pid, override in overrides.items():
            if pid in personas:
                personas[pid] = {**personas[pid], **override}
        return personas

    def for_message(self, text: str) -> tuple[dict, str]:
        """(persona, mood) for this message."""
        personas = self.all()
        prefs = self.prefs()
        mood = pick_mood(text)
        if prefs["pinned"] != "auto" and prefs["pinned"] in personas:
            return personas[prefs["pinned"]], mood
        owners = [p for p in personas.values() if mood in p.get("moods", [])]
        if mood == "downtime" and prefs["downtime"] in personas:
            owners = [personas[prefs["downtime"]]]
        if not owners:
            owners = [p for p in personas.values() if "default" in p.get("moods", [])]
        if not owners:
            owners = list(personas.values())
        if not owners:
            return {}, mood
        self._turn += 1
        return owners[self._turn % len(owners)], mood

    def roster_prompt(self) -> str:
        """The once-per-process system prompt part: who everyone is."""
        personas = self.all()
        if not personas:
            return ""
        lines = [
            "Personas (Emerson asked for these; the full personality is in "
            "~/.claude/self/PERSONALITY.md). Each user message may start with a line "
            "like [persona: Kira | mood: build]. Speak as that persona for the "
            "reply: tone, humour and flavour only. The work, facts, numbers and what "
            "is verified stay exactly as they would be. Never mention the tag.",
        ]
        for p in personas.values():
            lines.append(f"- {p.get('prompt') or p.get('name')}")
        return "\n".join(lines)

    @staticmethod
    def tag(persona: dict, mood: str) -> str:
        if not persona:
            return ""
        return f"[persona: {persona.get('name', persona.get('id'))} | mood: {mood}]\n"
