"""Deciding, before any model runs, how to handle a message.

1. **Fast path.** Short, unambiguous commands -- "open firefox", "pause",
   "close this window", "volume 40", "next song" -- are what small models
   fumble most and what people say most. They are matched here and run
   directly, in milliseconds, with no model at all. Anything not clearly one
   of these goes to a model; a fast-path miss costs nothing.
2. **Toolsets.** Each tool module declares the words that suggest it
   (TOOLSET_KEYWORDS). The best-scoring toolsets are offered to the model,
   plus the ones the conversation already used, so a follow-up keeps its
   tools and the prompt prefix stays the same.
3. **Tier.** Chat goes to the tiny model, actions to the small one, code,
   vision and long documents to the medium one. Escalation to the next tier
   happens later, in the agent, when a model fails.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field

from . import registry

MAX_TOOLSETS = {"tiny": 2, "small": 2, "medium": 3, "large": 5}
ALWAYS_WITH = {
    "docs": ["screen"],
    "screen": ["docs"],
    "terminal": ["shell"],
    "ui": ["windows"],
    # Anything done inside an app can fall back to its buttons and keys.
    "apps": ["ui"],
}

CHAT_PATTERNS = re.compile(
    r"^(hi|hey|hello|yo|sup|thanks|thank you|thx|good (morning|night|evening)|how are you|"
    r"who are you|what are you|tell me a joke|lol|ok|okay|cool|nice|bye|gn|love you)\b",
    re.I,
)
CODE_WORDS = re.compile(
    r"\b(code|coding|bug|debug|refactor|script|compile|traceback|exception|def|"
    r"python|javascript|typescript|rust|sql|regex|unit test|pytest|\.py|\.js|\.ts|\.rs)\b",
    re.I,
)
VISION_WORDS = re.compile(
    r"\b(screen|look at|see|picture|image|photo|frame|screenshot|showing)\b", re.I
)
CREATIVE = re.compile(
    r"^(please |can you |could you )?(write|tell|make up|give)( me)? (a |an |another |some |me a )?"
    r"(short |funny |cute |cozy |new |little )*(story|stories|poem|joke|haiku|limerick|riddle|fun fact)\b",
    re.I,
)
MODEL_QUESTION = re.compile(
    r"\b(what|which)('?s| is| are)?( the)? (model|llm|ai model|language model)\b"
    r"|\b(what|which) (model|llm)( are you| is this| is running| do you use| are you on| am i talking to)"
    r"|\b(what|which) (llm|model) are you\b|\bwhat are you running on\b",
    re.I,
)
HARD_WORDS = re.compile(
    r"\b(step by step|in detail|prove|derive|architecture|design a|plan a|explain why)\b",
    re.I,
)


def asks_model(text: str) -> bool:
    """A question about which model is answering (answered from settings,
    never by a model, which would guess)."""
    return bool(MODEL_QUESTION.search(text)) and not re.search(
        r"\b(open|folder|file|download)\b", text, re.I
    )


def is_chat(text: str, scores: dict[str, float] | None = None) -> bool:
    """Greetings, stories, jokes and plain questions with no action words:
    answered without tools."""
    stripped = text.strip()
    if CREATIVE.match(stripped):
        return True
    scores = score_toolsets(text) if scores is None else scores
    if scores:
        return False
    if CHAT_PATTERNS.match(stripped) and len(stripped.split()) <= 8:
        return True
    # A question that names nothing Acchan acts on ("why is the sky blue?").
    return bool(
        re.match(
            r"^(what|who|why|how|when|where|which|is|are|do|does|can|could)\b",
            stripped,
            re.I,
        )
        and not re.search(r"\b(my|this|that|these|open|here)\b", stripped, re.I)
    )


def is_small_talk(text: str) -> bool:
    """A greeting, thanks or goodbye with nothing to do: answered with one
    light model call (agent.Agent._small_talk)."""
    stripped = text.strip()
    return (
        bool(CHAT_PATTERNS.match(stripped))
        and len(stripped.split()) <= 6
        and not score_toolsets(text)
    )


@dataclass
class Plan:
    tier: str
    toolsets: list[str] = field(default_factory=list)


READ_WORDS = re.compile(
    r"\b(read|summari[sz]e|summary|tell me|what does|what's on|says?|title|text|screenshot|picture)\b"
)


def score_toolsets(text: str) -> dict[str, float]:
    lowered = " " + text.lower() + " "
    scores: dict[str, float] = {}
    for name, words in registry.KEYWORDS.items():
        score = 0.0
        for word in words:
            w = word.lower()
            if re.search(r"(?<![a-z])" + re.escape(w) + r"(?![a-z])", lowered):
                score += 1.0 + 0.2 * w.count(" ")
        if score:
            scores[name] = score
    if re.search(r"https?://|file://|www\.|\.(com|org|net|io|au)\b", lowered):
        scores["browser"] = scores.get("browser", 0) + 2
        # Reading an address is page work, done in the headless browser.
        if READ_WORDS.search(lowered):
            scores["pages"] = scores.get("pages", 0) + 3
    # A message that names a tool ("use page_read") wants that tool's toolset.
    for word in re.findall(r"[a-z]+(?:_[a-z]+)+", lowered):
        named = registry.TOOLS.get(word)
        if named is not None:
            scores[named.toolset] = scores.get(named.toolset, 0) + 3
    if re.search(r"(youtube\.com|youtu\.be)", lowered):
        scores["media"] = scores.get("media", 0) + 2
    if re.search(r"\d\s*[-+*/x×÷^%]\s*\d|\d+\s*%\s*of\b", lowered):
        scores["system"] = scores.get("system", 0) + 3  # arithmetic: the calculator
    if re.search(r"[~/][\w./-]+\.(pdf|docx?|pptx?|epub|odt)\b", lowered):
        scores["docs"] = scores.get("docs", 0) + 3
    return scores


def plan(
    text: str, used: list[str] | None = None, forced_tier: str | None = None
) -> Plan:
    used = list(used or [])
    words = len(text.split())
    scores = score_toolsets(text)
    chat = is_chat(text, scores)
    if forced_tier in ("tiny", "small", "medium", "large"):
        tier = forced_tier
    elif chat and not used:
        tier = "tiny"
    elif (
        CODE_WORDS.search(text) or VISION_WORDS.search(text) or HARD_WORDS.search(text)
    ):
        tier = "medium"
    elif "docs" in scores and words > 12:
        tier = "medium"
    else:
        tier = "small"
    if chat:
        return Plan(tier, [])
    limit = MAX_TOOLSETS[tier]
    ranked = [name for name, _ in sorted(scores.items(), key=lambda kv: -kv[1])][:limit]
    if not ranked and not used:
        # A task with no keyword hits: open things, and work any app by hand
        # (its buttons, fields and keys), the way a person would.
        ranked = ["apps", "ui", "files"] if words > 2 else []
    if tier == "tiny":
        # The 0.8B picks well from a handful of tools only: this message's
        # toolsets first, then at most one carried over from earlier.
        chosen = list(dict.fromkeys(ranked + used))[: max(2, len(ranked))]
    else:
        chosen = list(dict.fromkeys(used + ranked))
    for name in list(chosen):
        for extra in ALWAYS_WITH.get(name, []):
            if extra not in chosen and extra in registry.TOOLSETS:
                chosen.append(extra)
    if CODE_WORDS.search(text):
        for extra in ("files", "shell"):
            if extra not in chosen:
                chosen.append(extra)
    return Plan(tier, chosen)


# ------------------------------------------------------ tools for the 0.8B

# The 0.8B picks the right tool reliably from about eight; from twenty it
# guesses. So it sees the tools whose names, descriptions and examples share
# the most words with the message, not whole toolsets.
TINY_TOOLS = 8
STOP_WORDS = frozenset(
    "a an the to of in on at for and or is are be it this that my me i you "
    "your with from as by what which can could please do does have has any "
    "all some one up out into about how now then just".split()
)
# Words people say for what a tool's name calls something else.
SYNONYMS = {
    "dir": "folder directory inside contents",
    "web": "tab page site internet firefox browser window",
    "tabs": "tab firefox browser",
    "window": "windows app",
    "path": "file folder",
    "media": "music song video",
    "clipboard": "copy paste copied",
    "list": "which what show check open got many",
}


def _stem(word: str) -> str:
    for end in ("ing", "ed", "es", "s"):
        if len(word) > len(end) + 2 and word.endswith(end):
            return word[: -len(end)]
    return word


def _words(text: str) -> set[str]:
    return {
        _stem(w)
        for w in re.findall(r"[a-z]+", text.lower())
        if w not in STOP_WORDS and len(w) > 1
    }


def rank_tools(text: str, toolsets: list[str], limit: int = TINY_TOOLS) -> list[str]:
    """The `limit` tools from these toolsets (and their companions) that
    best fit the message, best first."""
    said = _words(text)
    extra = {n for ts in toolsets for n in registry.COMPANIONS.get(ts, ())}
    examples: dict[str, str] = {}
    for ts in toolsets:
        for phrase, name, _args in registry.EXAMPLES.get(ts, []):
            examples[name] = examples.get(name, "") + " " + phrase
    scored = []
    for order, t in enumerate(registry.TOOLS.values()):
        if t.toolset not in toolsets and t.name not in extra:
            continue
        parts = t.name.split("_")
        name_words = _words(" ".join(parts + [SYNONYMS.get(p, "") for p in parts]))
        desc = _words(t.description)
        params = _words(
            " ".join(f"{k} {v.get('description', '')}" for k, v in t.properties.items())
        )
        score = (
            3 * len(said & name_words)
            + len(said & desc)
            + 0.5 * len(said & params)
            + 2 * len(said & _words(examples.get(t.name, "")))
        )
        scored.append((-score, order, t.name))
    return [name for _s, _o, name in sorted(scored)[:limit]]


# ----------------------------------------------------------------- fast path


@dataclass
class FastCall:
    tool: str
    args: dict
    reply: str  # what to say after it works; {result} is the tool's output


SITES = {
    "youtube": "youtube.com",
    "google": "google.com",
    "gmail": "mail.google.com",
    "reddit": "reddit.com",
    "github": "github.com",
    "netflix": "netflix.com",
    "crunchyroll": "crunchyroll.com",
    "chatgpt": "chatgpt.com",
    "claude": "claude.ai",
    "qobuz web": "play.qobuz.com",
    "wikipedia": "wikipedia.org",
    "twitch": "twitch.tv",
    "amazon": "amazon.com.au",
    "oasis": "oasis.curtin.edu.au",
    "blackboard": "lms.curtin.edu.au",
}
POLITE = r"(?:please\s+|can you\s+|could you\s+|pls\s+|acchan,?\s+|hey acchan,?\s+)*"
TAIL = r"(?:\s+(?:please|pls|for me|now|thanks))*[.!?]*$"


VERB = re.compile(
    r"^(?:please |can you |could you )*(open|launch|start|close|pause|play|switch to)\b",
    re.I,
)


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip())


def fast_path(text: str) -> list[FastCall] | None:
    """Tool calls for a plain command, or None to let a model handle it.
    'open firefox and pause the music' becomes two calls; any part that is
    not a plain command sends the whole message to the model."""
    message = _clean(text)
    if not message or len(message.split()) > 14:
        return None
    headless = _headless(message)
    if headless:
        return [headless]
    if "?" in message:
        # Only a few questions are really commands: "what tabs do I have
        # open?", "what is 12*7?". Everything else needs a model.
        question = re.sub(r"\?+$", "", message)
        if "?" in question:
            return None
        return _question(spelling_free(question))
    parts = re.split(
        r"\s*(?:,\s*then|\bthen\b|\band then\b|\band\b|;)\s*", message, flags=re.I
    )
    calls = []
    verb = ""
    for part in parts:
        if not part:
            continue
        # "open firefox and a tab": the second part borrows the first's verb.
        m = VERB.match(part)
        if m:
            verb = m.group(1)
        elif verb and len(part.split()) <= 4:
            part = f"{verb} {part}"
        found = _many(part)
        if found is None:
            return None
        calls.extend(found)
    return calls or None


def _headless(message: str) -> FastCall | None:
    """Background shells and the headless browser. Checked on the whole
    message first: a command like "make and test" must not be split."""
    t = spelling_free(message)
    m = re.fullmatch(
        r"run (?:`([^`]+)`|\"([^\"]+)\"|'([^']+)'|(.+?)) (?:in the background|in background|headless(?:ly)?|in a background shell)",
        t,
        re.I,
    )
    if m:
        command = next(g for g in m.groups() if g).strip()
        # Its own shell, named after the program, so a second job never
        # types into one that is still running; 5 s, then it keeps going.
        shell = "bg-" + re.sub(r"\W+", "", command.split()[0])[:20]
        return FastCall(
            "shell_run", {"command": command, "shell": shell, "timeout": 5}, "{result}"
        )
    low = t.lower()
    if re.fullmatch(
        r"show (?:me )?(?:the |my )?(?:background |headless )?(?:terminal|shell)", low
    ):
        return FastCall("shell_show", {}, "{result}")
    if re.fullmatch(
        r"close (?:all )?(?:the |my )?(?:background|headless) (?:terminals|shells)|close all (?:the )?shells",
        low,
    ):
        return FastCall("shell_close", {"shell": "all"}, "{result}")
    if re.fullmatch(r"close (?:the )?headless (?:browser|firefox)", low):
        return FastCall("close_headless_browser", {}, "{result}")
    return None


def spelling_free(text: str) -> str:
    """The command words of a message, without politeness or trailing fluff."""
    t = re.sub("^" + POLITE, "", text.strip(), flags=re.I)
    return re.sub(TAIL, "", t, flags=re.I).strip()


def _many(text: str) -> list[FastCall] | None:
    t = spelling_free(text)
    found = _browser(t.lower())
    if found:
        return found
    for handler in (_sum, _tab_list, _text_doc):
        call = handler(t)
        if call:
            return [call]
    call = _one(text)
    return [call] if call else None


def _question(t: str) -> list[FastCall] | None:
    for handler in (_sum, _tab_list):
        call = handler(t)
        if call:
            return [call]
    if re.fullmatch(
        r"what('?s| is) (playing|this song)|what song is (this|playing)", t.lower()
    ):
        return [FastCall("now_playing", {}, "{result}")]
    return None


# ------------------------------------------------------- browser commands

NUMBERS = {"two": 2, "three": 3, "four": 4, "five": 5}
DOMAIN = re.compile(
    r"^(https?://|www\.)\S+$|^[\w-]+(\.[\w-]+)*\.(com|org|net|io|au|tv|ai|dev|app|edu)(/\S*)?$"
)
NEW = r"(?:a |an |the |one )?(?:new |another |fresh |blank |empty |more |extra )*"
OPENING = (
    r"(?:(?:open|make|create|start|launch|get|give|pop|bring|load)(?: up| open| me)* )?"
)


def _site(target: str, strict: bool) -> str | None:
    """The address for a site someone named, or None when it is not one
    (strict) / the words themselves, for a search (not strict)."""
    t = re.sub(r"^(?:a|an|the|my)\s+", "", target.strip()).strip()
    if t in ("", "empty", "blank", "new"):
        return "about:newtab"
    if t in SITES:
        return SITES[t]
    if DOMAIN.match(t):
        return t
    close = difflib.get_close_matches(t, SITES, n=1, cutoff=0.8)
    if close:
        return SITES[close[0]]
    return None if strict else target.strip()


def _open_web(address: str, kind: str) -> FastCall:
    if kind == "window":
        return FastCall(
            "open_web",
            {"address": address, "new_window": True},
            "New Firefox window open.",
        )
    if address == "about:newtab":
        return FastCall("open_web", {"address": address}, "New tab open.")
    return FastCall("open_web", {"address": address}, "Opened it in a new tab.")


def _browser(low: str) -> list[FastCall] | None:
    """New tabs and windows (with or without a site), private windows,
    and switching to or closing a named tab."""
    if re.fullmatch(
        r"(?:open |start |launch |make |give me )?(?:me )?"
        + NEW
        + r"(?:firefox |browser )?(?:private|incognito)(?: browsing)?(?: firefox| browser)?(?: window| tab| mode)?(?: in firefox)?",
        low,
    ):
        return [
            FastCall(
                "open_web", {"address": "", "private": True}, "Private window open."
            )
        ]
    m = re.fullmatch(
        r"(?:switch|go|change|jump|flip)(?: over| back)? to (?:the |my |that )?tab (\d{1,3})",
        low,
    )
    m = m or re.fullmatch(
        r"(?:switch|go|change|jump|flip|take me)(?: over| back)? to (?:the |my |that )?(.{2,40}?) tab",
        low,
    )
    if m:
        return [FastCall("switch_tab", {"tab": m.group(1)}, "Switched to it.")]
    m = re.fullmatch(r"close (?:the |my |that )?(.{2,40}?) tab", low)
    if m and m.group(1) not in ("this", "current", "the", "front", "active"):
        return [FastCall("close_tab", {"tab": m.group(1)}, "Closed that tab.")]
    if not re.search(r"\b(tabs?|window)\b", low) or re.search(
        r"\b(terminal|close|switch)\b", low
    ):
        return None
    x = re.sub(
        r"\b(?:in|on|using|inside|from) (?:a |the )?(?:firefox|web browser|browser)\b",
        " ",
        low,
    )
    x = re.sub(r"\b(firefox|web browser|browser)\b", " ", x)
    x = re.sub(r"\s+", " ", x).strip()
    m = re.fullmatch(
        r"(?:open|make|create) (\d|two|three|four|five) (?:new |more |empty |extra )?tabs",
        x,
    )
    if m:
        n = NUMBERS.get(m.group(1)) or int(m.group(1))
        return [_open_web("about:newtab", "tab") for _ in range(max(1, min(n, 9)))]
    m = re.fullmatch(
        OPENING + NEW + r"(tab|window)(?: (?:for|with|to|of|at|showing) (.+))?", x
    )
    if m:
        address = _site(m.group(2) or "", strict=False) or "about:newtab"
        return [_open_web(address, m.group(1))]
    m = re.fullmatch(
        r"(?:open|launch|load|go to|pull up|bring up|put)(?: up)? (.+?) (?:in|on|into) "
        r"(?:a |an |another )?(?:new )?(tab|window)",
        x,
    )
    if m:
        address = _site(m.group(1), strict=False)
        return [_open_web(address or "about:newtab", m.group(2))]
    m = re.fullmatch(OPENING + NEW + r"(.+?) (tab|window)", x)
    if m:
        address = _site(m.group(1), strict=True)
        if address:
            return [_open_web(address, m.group(2))]
    return None


def _tab_list(t: str) -> FastCall | None:
    low = t.lower()
    if (
        re.search(r"\btabs\b", low)
        and re.match(
            r"^(list|show|tell|give|what|which|see|how many|display|name|check)\b", low
        )
        and not re.search(r"\b(why|should|mean|close|switch)\b", low)
    ):
        return FastCall("browser_tabs", {}, "{result}")
    return None


def _sum(t: str) -> FastCall | None:
    """Arithmetic, always through the calculator (models get it wrong)."""
    x = re.sub(
        r"^(?:what(?:'s| is| it| are)?|whats|calculate|calc|compute|work out|how much is|solve)\s+",
        "",
        t.strip().lower(),
    )
    x = re.sub(r"\s*[=?.!]+$", "", x)
    x = re.sub(r"\s*\b(?:times|multiplied by)\b\s*|(?<=\d)\s*x\s*(?=\d)", " * ", x)
    x = re.sub(r"\s*\bplus\b\s*", " + ", x)
    x = re.sub(r"\s*\bminus\b\s*", " - ", x)
    x = re.sub(r"\s*\bdivided by\b\s*", " / ", x)
    x = re.sub(r"\s+", " ", x).strip()
    if re.fullmatch(r"[\d\s.+\-*/^()%×÷]+", x) and re.search(
        r"\d\s*[-+*/^×÷]\s*[\d(]", x
    ):
        return FastCall("calculate", {"expression": x}, "{result}")
    if re.fullmatch(r"\d+(?:\.\d+)?\s*% of \d+(?:\.\d+)?", x):
        return FastCall("calculate", {"expression": x}, "{result}")
    return None


def _text_doc(t: str) -> FastCall | None:
    if re.fullmatch(
        r"(?:open|make|create|start)(?: up)?(?: me)? (?:a |an )?(?:new |blank |empty )*"
        r"(?:text )?(?:doc|document|text file|note|txt)",
        t.lower(),
    ) and re.search(r"\b(new|blank|empty|text)\b", t.lower()):
        return FastCall(
            "launch_app", {"name": "text editor"}, "Opened the Text Editor."
        )
    return None


def _one(text: str) -> FastCall | None:
    t = re.sub("^" + POLITE, "", text.strip(), flags=re.I)
    t = re.sub(TAIL, "", t, flags=re.I).strip()
    low = t.lower()

    # media
    m = re.fullmatch(
        r"(pause|resume|unpause|play|stop|skip|next|previous|prev)(?: the| this)?(?: (music|song|track|video|it|this|qobuz|spotify|youtube|mpv))?(?: song| track| video)?(?: (?:on|in) (qobuz|spotify|youtube|mpv|firefox))?",
        low,
    )
    if m:
        action = {
            "resume": "play",
            "unpause": "play",
            "skip": "next",
            "prev": "previous",
        }.get(m.group(1), m.group(1))
        named = m.group(3) or m.group(2)
        player = (
            named if named in ("qobuz", "spotify", "youtube", "mpv", "firefox") else ""
        )
        return FastCall(
            "media_control",
            {"action": action, "player": player},
            {"play": "Playing.", "pause": "Paused.", "stop": "Stopped."}.get(
                action, "Done."
            ),
        )
    if re.fullmatch(
        r"(next|skip)( to the next)? (song|track)|play (the )?next (song|track)", low
    ):
        return FastCall("media_control", {"action": "next"}, "Skipped!")
    if re.fullmatch(r"(previous|last|go back a) (song|track)", low):
        return FastCall("media_control", {"action": "previous"}, "Back one track.")
    m = re.fullmatch(
        r"(?:set )?(?:the )?volume(?: to)? (\d{1,3})\s*%?|volume (\d{1,3})", low
    )
    if m:
        level = int(m.group(1) or m.group(2))
        return FastCall("set_volume", {"percent": level}, f"Volume set to {level}%.")
    if re.fullmatch(r"(mute|mute the (sound|volume|audio))", low):
        return FastCall("set_volume", {"percent": 0}, "Muted.")
    if re.fullmatch(
        r"what('?s| is) (playing|this song)|what song is (this|playing)", low
    ):
        return FastCall("now_playing", {}, "{result}")

    # memory and reminders: the 0.8B missed both in the eval
    m = re.fullmatch(r"(?:remember|don'?t forget|note) that (.{3,200})", t, flags=re.I)
    if m:
        return FastCall("remember", {"fact": m.group(1)}, "Got it, I'll remember that.")
    m = re.fullmatch(
        r"remind me in (\d{1,4}) ?(minutes?|mins?|hours?|hrs?) (?:to )?(.{2,150})", low
    )
    if m:
        minutes = int(m.group(1)) * (60 if m.group(2).startswith("h") else 1)
        return FastCall(
            "remind_me", {"minutes": minutes, "message": m.group(3)}, "{result}"
        )

    # windows
    m = re.fullmatch(r"close (?:this|the current|the) (window|app)", low)
    if m or low in ("close this", "close it"):
        return FastCall("close_window", {"window": "this"}, "Closed it.")
    m = re.fullmatch(r"close (?:this |the current |the )?tab", low)
    if m:
        return FastCall("close_tab", {"tab": ""}, "Tab closed.")
    m = re.fullmatch(
        r"(?:switch to|go to|focus|bring up|show me) (?:the )?([\w .-]{2,30}?)(?: window| app)?",
        low,
    )
    if m and not re.search(r"\b(tab|workspace|page|folder|file)\b", low):
        target = m.group(1)
        if target in SITES or re.match(
            r"^[\w-]+\.(com|org|net|io|au|tv|ai|dev|app)(/\S*)?$", target
        ):
            return FastCall(
                "open_web",
                {"address": SITES.get(target, target)},
                "Opened it in Firefox.",
            )
        return FastCall("focus_window", {"window": target}, "Here you go!")
    m = re.fullmatch(r"(?:switch to |go to )?workspace (\d{1,2})", low)
    if m:
        return FastCall(
            "switch_workspace", {"workspace": m.group(1)}, f"Workspace {m.group(1)}."
        )
    if re.fullmatch(
        r"(make (this|it) )?full ?screen( this| it)?|toggle full ?screen", low
    ):
        return FastCall("fullscreen_window", {"window": "this"}, "Fullscreen toggled.")
    if re.fullmatch(r"(take a )?screenshot", low):
        return FastCall("take_screenshot", {}, "{result}")

    # open things
    m = re.fullmatch(
        r"(?:open|launch|start|run|fire up|load up|bring up)(?: up)? (?:the |my |a |an )?(.{2,60})",
        t,
        flags=re.I,
    )
    if m:
        target = m.group(1).strip().strip("'\"")
        tl = target.lower()
        tl = re.sub(r"\s+(app|application|program|website|site|web ?page)$", "", tl)
        if re.match(
            r"^(https?://|www\.)|^[\w-]+\.(com|org|net|io|au|tv|ai|dev|app)(/\S*)?$", tl
        ):
            return FastCall("open_web", {"address": target}, "Opened it in Firefox.")
        if tl in SITES:
            return FastCall(
                "open_web", {"address": SITES[tl]}, f"Opened {tl.capitalize()}."
            )
        if re.match(r"^[~/]", target):
            return FastCall("open_item", {"target": target}, "Opened it.")
        m2 = re.fullmatch(
            r"(?:new )?(?:(?:firefox|browser) )?window", tl
        ) or re.fullmatch(r"(?:new )?(firefox|browser|web browser)(?: window)?", tl)
        if m2 and (tl.startswith("new") or tl.endswith("window")):
            return FastCall(
                "open_web",
                {"address": "about:newtab", "new_window": True},
                "New Firefox window open!",
            )
        m2 = re.fullmatch(r"(?:new )?tab(?: (?:for|with|to) (.+))?", tl)
        if m2:
            return FastCall(
                "open_web", {"address": m2.group(1) or "about:newtab"}, "New tab open."
            )
        if re.fullmatch(r"(new )?terminal( window)?", tl):
            return FastCall("open_terminal", {}, "Terminal's up!")
        m2 = re.fullmatch(r"(?:new )?terminal(?: window)? (?:in|at|inside) (.+)", tl)
        if m2:
            return FastCall("open_terminal", {"folder": m2.group(1)}, "Terminal's up!")
        if re.fullmatch(r"(new )?terminal tab", tl):
            return FastCall("terminal_new_tab", {}, "New terminal tab.")
        # Anything else is an app name; the tool's own matching decides.
        # Words that mean "a thing inside an app" go to the model instead.
        if re.search(
            r"\b(folder|file|document|pdf|song|video|playlist|email|message|the last|my recent|that)\b",
            tl,
        ) and tl not in ("file explorer", "file manager", "files"):
            return None
        from .tools.apps import find_app

        app = find_app(tl, strict=True)
        if app is None:
            return None  # not clearly an app: let a model work out what was meant
        # A Forge app's reply says whether Forge switched or needs a restart.
        reply = "{result}" if app.get("forge") else f"Opening {app['name']}!"
        return FastCall("launch_app", {"name": tl}, reply)
    m = re.fullmatch(
        r"(?:search|google|look up)(?: the web)?(?: for)? (.{2,80})", t, flags=re.I
    )
    if m and not re.search(r"\b(file|folder|my )\b", m.group(1).lower()):
        return FastCall("open_web", {"address": m.group(1)}, "Searched it in Firefox.")
    m = re.fullmatch(r"(?:play|put on) (.+?) on youtube", low)
    if m:
        return FastCall(
            "open_web",
            {
                "address": "https://www.youtube.com/results?search_query="
                + m.group(1).replace(" ", "+")
            },
            "Found it on YouTube.",
        )
    return None
