"""Turning a mail (or a line typed in the terminal) into one Relay command.

The first line decides. A fixed set of short commands:

    status | queue | pause | resume | digest | help
    stop <task number> | retry <task number>
    goal: <title>            (the lines below it describe the goal)
    task: [<goal>] <text>    (adds a task, to that goal when it names one)
    new: <text>              (the WhatsApp work task: one open at a time)

From WhatsApp, anything that is not a command goes to the chat session, and
"boss <question>" goes to the boss line (bossline.py).

Anything else, one word or three pages, is a new task: the whole text is the
request and a fresh session works on it. Option lines at the top (before the
request) tune it:

    folder: ~/Forge/apps/cosmos     priority: important (or just "important")
    effort: max                     account: second
    model: opus                     done when: <how to tell it is finished>

Mail text is never run as a shell command. It only ever becomes a task or goal
file that a session reads. `check:` (a goal's shell check) is taken from the
page and the terminal only, never from mail.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from html.parser import HTMLParser

import quick

SIMPLE = {
    "status": "status",
    "queue": "status",
    "list": "status",
    "pause": "pause",
    "resume": "resume",
    "unpause": "resume",
    "digest": "digest",
    "help": "help",
    "commands": "help",
    "?": "help",
    "progress": "progress",
    "report": "progress",
    "usage": "usage",
}
REMOTE = ("mail", "whatsapp")  # never allowed a shell `check:` line
NUMBERED = re.compile(
    r"^(stop|retry|cancel|progress|report)\s*(?:task\s*)?#?(\d+)?\s*[.!]?$", re.I
)
TELL = re.compile(r"^tell\s+(?:task\s*)?#?(\d+)\s*[:,-]?\s*(.*)$", re.I | re.S)
NOTIFY = re.compile(r"^notify\s+(quiet|mine|all)\s*[.!]?$", re.I)
SAY = re.compile(r"^say\s+(?:@(\S+)\s+)?(.+)$", re.I | re.S)
# WhatsApp "boss <question>": straight to Relay's boss (bossline.py).
# "boss:", "boss,", "@boss" always; a bare "boss " only before a word that
# opens a question or an order, so "boss fight is too hard" stays the chat.
BOSS = re.compile(
    r"^\s*(?:@boss\b[\s:,\-]*|boss\s*[:,\-]\s*|boss\s+(?=(?:what|whats|what's|how"
    r"|hows|how's|when|where|who|which|why|any|anything|stop|kill|cancel|pause"
    r"|resume|retry|tell|pass|queue|start|status|eta|usage|can|could|should|will"
    r"|would|give|show|list|please|check|hey|hi|hello|ok|okay|yo|mate|you|u)\b))"
    r"(\S.*)$",
    re.I | re.S,
)
PREFIXED = re.compile(r"^(goal|task|new|work)\s*:\s*(.*)$", re.I)
OPTION = re.compile(
    r"^(folder|dir|priority|effort|account|model|done when|done-when|check)\s*:\s*(.+)$",
    re.I,
)
IMPORTANT_WORDS = {"important", "!important", "urgent", "priority", "!!"}
REPLY_PREFIX = re.compile(r"^\s*((re|fw|fwd|aw)\s*:\s*)+", re.I)
# Where the new text ends: signatures and quoted earlier mail.
CUT = re.compile(
    r"^(--\s*|sent from .*|get outlook for .*|_{5,}\s*|-{3,}\s*original message\s*-{3,}.*"
    r"|on .{3,200} wrote:\s*|from:\s.*@.*)$",
    re.I,
)
EFFORTS = ("low", "medium", "high", "xhigh", "max")
MODELS = ("haiku", "sonnet", "opus")


def _clear_option(line: str) -> bool:
    """An option line that cannot be the start of a sentence: a known effort
    or model, a path, important. Only these are taken from beside a command
    (above it, or right after its colon); "new: Check: why ..." stays the
    request."""
    line = line.strip()
    if line.lower().rstrip(".!") in IMPORTANT_WORDS:
        return True
    match = OPTION.match(line)
    if not match:
        return False
    key, value = match.group(1).lower(), match.group(2).strip().lower()
    return (
        (key == "effort" and value in EFFORTS)
        or (key == "model" and value in MODELS)
        or (key in ("folder", "dir") and value[0] in "~/" and " " not in value)
        or (key == "priority" and value in ("important", "normal"))
    )


@dataclass
class Command:
    kind: str  # status pause resume digest help stop retry tell goal task
    #            progress usage notify say work (the WhatsApp work task)
    #            chat (a plain WhatsApp message, for the chat session)
    #            quick (quick.py: title is its name, options["args"])
    #            boss (WhatsApp "boss <text>": the boss line, bossline.py)
    number: int | None = None
    title: str = ""
    text: str = ""
    goal: str = ""
    options: dict = field(default_factory=dict)


class _Text(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("style", "script", "head"):
            self.skip += 1
        if tag in ("br", "p", "div", "li", "tr", "h1", "h2", "h3"):
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("style", "script", "head") and self.skip:
            self.skip -= 1

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def html_to_text(html: str) -> str:
    parser = _Text()
    parser.feed(html)
    text = "".join(parser.parts).replace("\xa0", " ")
    return re.sub(r"\n\s*\n\s*\n+", "\n\n", text)


def clean(text: str) -> str:
    """The new part of a mail: no signature, no quoted earlier mail."""
    kept = []
    for line in text.replace("\r\n", "\n").split("\n"):
        if CUT.match(line.strip()):
            break
        if line.lstrip().startswith(">"):
            continue
        kept.append(line.rstrip())
    return "\n".join(kept).strip()


def bare_subject(subject: str) -> str:
    return REPLY_PREFIX.sub("", subject or "").strip()


def _options(lines: list[str], allow_check: bool) -> tuple[dict, list[str]]:
    options: dict = {}
    rest = list(lines)
    while rest:
        line = rest[0].strip()
        if not line:
            rest.pop(0)
            continue
        if line.lower().rstrip(".!") in IMPORTANT_WORDS:
            options["priority"] = "important"
            rest.pop(0)
            continue
        match = OPTION.match(line)
        if not match:
            break
        key = match.group(1).lower().replace("-", " ")
        value = match.group(2).strip()
        key = {"dir": "folder", "done when": "done_when"}.get(key, key)
        if key == "check" and not allow_check:
            rest.pop(0)
            continue
        if key == "priority":
            value = "important" if value.lower() in IMPORTANT_WORDS else "normal"
        if key == "effort" and value.lower() not in EFFORTS:
            rest.pop(0)
            continue
        options[key] = value.lower() if key in ("effort", "account") else value
        rest.pop(0)
    return options, rest


def _title(subject: str, text: str) -> str:
    subject = bare_subject(subject)
    if subject:
        return subject
    first = next((line.strip() for line in text.splitlines() if line.strip()), "")
    if len(first) <= 80:
        return first
    # Cut at a word, without an ellipsis: the whole text is in the request.
    return first[:80].rsplit(" ", 1)[0].rstrip(" ,.;:-") or first[:80]


def parse(
    subject: str, body: str, goal_slugs: tuple[str, ...] = (), source: str = "mail"
) -> Command:
    allow_check = source not in REMOTE
    text = clean(body)
    subject_only = bare_subject(subject)
    lines = text.splitlines()
    first = next((line.strip() for line in lines if line.strip()), "")
    # A quick command (quick.py) is the whole message: answered without a model.
    said = [line for line in lines if line.strip()]
    found = quick.match(said[0]) if len(said) == 1 else None
    if found is None and not said and subject_only:
        found = quick.match(subject_only)
    if found:
        return Command("quick", title=found[0], options={"args": found[1]})
    boss = BOSS.match(text) if source == "whatsapp" else None
    if boss:
        return Command("boss", text=boss.group(1).strip())
    # A command may sit in the subject with nothing (or a sign-off) below.
    for line in ([first] if first else []) + ([subject_only] if subject_only else []):
        word = line.lower().rstrip(".!").lstrip("-/")
        if word in SIMPLE and (line == first or len(text) < 40):
            return Command(SIMPLE[word])
        numbered = NUMBERED.match(line)
        if numbered and (line == first or len(text) < 40):
            kind = {"cancel": "stop", "report": "progress"}.get(
                numbered.group(1).lower(), numbered.group(1)
            )
            number = int(numbered.group(2)) if numbered.group(2) else None
            return Command(kind.lower(), number=number)
        if line == first:
            break
    notify = NOTIFY.match(first)
    if notify:
        return Command("notify", text=notify.group(1).lower())
    said = SAY.match(text.strip()) if first.lower().startswith("say ") else None
    if said:
        return Command("say", title=said.group(1) or "", text=said.group(2).strip())
    told = TELL.match(text.strip()) if first.lower().startswith("tell") else None
    if told and told.group(2).strip():
        return Command("tell", number=int(told.group(1)), text=told.group(2).strip())
    # Clear option lines may also sit above the command ("effort: high" then
    # "new: ..."): a chat session writes it both ways (Relay task 99).
    lead: dict = {}
    said = [ln.strip() for ln in lines if ln.strip()]
    above = 0
    while above < len(said) and _clear_option(said[above]):
        above += 1
    if 0 < above < len(said) and PREFIXED.match(said[above]):
        lead, _ = _options(said[:above], allow_check)
        first = said[above]
        lines = lines[[ln.strip() for ln in lines].index(first) :]
    prefixed = PREFIXED.match(first) if first else None
    body_lines: list[str] = []
    if prefixed:
        body_lines = lines[[ln.strip() for ln in lines].index(first) + 1 :]
    elif subject_only and PREFIXED.match(subject_only):
        prefixed = PREFIXED.match(subject_only)
        body_lines = lines
    if prefixed:
        kind = prefixed.group(1).lower()
        head = prefixed.group(2).strip()
        if _clear_option(head) and any(ln.strip() for ln in body_lines):
            body_lines, head = [head, *body_lines], ""  # "new: effort: high"
        options, rest = _options(body_lines, allow_check)
        options = {**lead, **options}
        described = "\n".join(rest).strip()
        if kind in ("new", "work"):
            return Command(
                "work",
                title=_title("", head or described),
                text="\n\n".join(p for p in (head, described) if p),
                options=options,
            )
        if kind == "goal":
            return Command(
                "goal",
                title=head or _title(subject, described),
                text=described or head,
                options=options,
            )
        goal = ""
        words = head.split(None, 1)
        if words and words[0].lower() in goal_slugs:
            goal = words[0].lower()
            head = words[1] if len(words) > 1 else ""
        request = "\n\n".join(p for p in (head, described) if p)
        return Command(
            "task",
            title=_title("", head) if head else _title(subject, request),
            text=request,
            goal=goal,
            options=options,
        )
    if source == "whatsapp" and text.strip():
        return Command("chat", text=text.strip())
    options, rest = _options(lines, allow_check)
    request = "\n".join(rest).strip()
    is_reply = bool(REPLY_PREFIX.match(subject or ""))
    if (
        subject_only
        and not is_reply
        and subject_only.lower() not in request.lower()[:200]
    ):
        request = f"{subject_only}\n\n{request}".strip()
    if not request:
        return Command("help")
    return Command(
        "task", title=_title(subject, request), text=request, options=options
    )
