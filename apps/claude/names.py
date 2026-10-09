"""Human names for conversations, shown on the tabs instead of "New conversation".

Emerson (2026-09-27) wanted the tabs to read like people, not topics. The list
is the whole registry: add or remove a name here and nothing else changes.
A conversation's name is picked once from its id and saved in its metadata,
so it never changes on its own; the user can rename it from the tab.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable

NAMES = (
    "Aiko",
    "Akira",
    "Asuka",
    "Chihiro",
    "Emi",
    "Haru",
    "Hikari",
    "Hina",
    "Hotaru",
    "Itsuki",
    "Kaede",
    "Kaito",
    "Kana",
    "Kenji",
    "Kiko",
    "Koharu",
    "Mei",
    "Mika",
    "Minato",
    "Mio",
    "Nagi",
    "Nao",
    "Nene",
    "Rei",
    "Ren",
    "Rin",
    "Riku",
    "Sakura",
    "Sora",
    "Suzu",
    "Takumi",
    "Tomo",
    "Tsubaki",
    "Yui",
    "Yuki",
    "Yuna",
    "Yuzu",
    "Ami",
    "Daichi",
    "Hayato",
    "Izumi",
    "Kohaku",
    "Momo",
    "Natsu",
    "Noa",
    "Rika",
    "Shun",
    "Toru",
    "Umi",
    "Wakana",
)


def pick(conv_id: str, taken: Iterable[str] = ()) -> str:
    """The name for `conv_id`: the one its id points at, or the next free one
    after it. Names repeat only once every name in the list is in use."""
    used = {n.casefold() for n in taken}
    start = int(hashlib.sha1(conv_id.encode()).hexdigest(), 16) % len(NAMES)
    for step in range(len(NAMES)):
        name = NAMES[(start + step) % len(NAMES)]
        if name.casefold() not in used:
            return name
    return NAMES[start]


def clean(name: str) -> str:
    """A name the user typed, tidied: one line, trimmed, at most 32 characters."""
    return " ".join(str(name).split())[:32]
