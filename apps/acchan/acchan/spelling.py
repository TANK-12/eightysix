"""Fixing typos before anything reads the message.

"open a new firfox window" misses every keyword and the fast path, and a
0.8B model reads "firfox" no better. So each unknown word is matched against
the words Acchan acts on -- toolset keywords, installed app names, site
names and a short list of command words -- and replaced only when the match
is close. Known English words (the system word list) are never touched, nor
are paths, addresses, numbers or anything in quotes.
"""

from __future__ import annotations

import difflib
import functools
import re
from pathlib import Path

# Words people use to ask for things, beyond what the toolsets declare.
COMMAND_WORDS = (
    "open close launch start stop play pause resume skip next previous new "
    "window windows tab tabs firefox browser terminal folder file files write "
    "read story poem joke song music video volume screen search find show list "
    "what where which when how please thanks weather brightness bluetooth wifi "
    "remember forget memory model install update delete rename move copy paste "
    "want make create edit code python script run command explain summarise "
    "summarize document lecture notes download downloads desktop documents"
).split()
# Short typos difflib cannot judge safely (too few letters to compare).
SHORT_FIXES = {
    "tb": "tab",
    "wndw": "window",
    "pls": "please",
    "plz": "please",
    "u": "you",
    "ur": "your",
    "yt": "youtube",
    "ff": "firefox",
    "msg": "message",
    "wnat": "want",
    "teh": "the",
    "adn": "and",
    "hte": "the",
    "fo": "of",
    "cna": "can",
}
DICTIONARIES = (Path("/usr/share/dict/words"), Path("/usr/share/dict/cracklib-small"))
WORD = re.compile(r"[A-Za-z][A-Za-z']*")


@functools.lru_cache(maxsize=1)
def english() -> frozenset[str]:
    for path in DICTIONARIES:
        try:
            return frozenset(
                w.strip().lower() for w in path.read_text(errors="ignore").split()
            )
        except OSError:
            continue
    return frozenset()


@functools.lru_cache(maxsize=1)
def vocabulary() -> tuple[str, ...]:
    """The words worth correcting towards, from the registry and apps."""
    from . import registry, router

    registry.load_all()
    words = set(COMMAND_WORDS)
    for keywords in registry.KEYWORDS.values():
        for phrase in keywords:
            words.update(WORD.findall(phrase.lower()))
    for site in router.SITES:
        words.update(WORD.findall(site))
    try:
        from .tools.apps import _entries

        for app in _entries():
            if not app["hidden"]:
                words.update(WORD.findall(app["name"].lower()))
    except Exception:
        pass
    return tuple(sorted(w for w in words if len(w) >= 3))


def _fix_word(word: str) -> str:
    low = word.lower()
    if low in SHORT_FIXES:
        return SHORT_FIXES[low]
    vocab = vocabulary()
    if len(low) < 4 or low in vocab or low in english():
        return word
    match = difflib.get_close_matches(low, vocab, n=1, cutoff=0.8)
    return match[0] if match else word


def correct(text: str) -> str:
    """The message with likely typos fixed. Paths, addresses, quoted text,
    numbers and known words pass through unchanged."""
    out = []
    for token in re.split(r"(\s+)", text):
        if (
            not token
            or token.isspace()
            or re.search(r"[/~\\.:@#=_\d]", token.rstrip(".,!?"))
            or token[:1] in "'\"`"
        ):
            out.append(token)
            continue
        out.append(WORD.sub(lambda m: _fix_word(m.group(0)), token))
    return "".join(out)
