"""Ways Relay talks to Emerson. One module per channel, found by discovery.

A channel module defines:

    NAME = "gmail"
    def configured(settings) -> bool
    def send(settings, subject, body, in_reply_to="", references="") -> str
        (returns the sent message's id, "" if it has none)
    def poll(settings, state) -> list[Incoming]
        (only new messages; `state` is a dict the channel may keep a cursor in)
    def test(settings) -> str   (a plain-words result of a connection test)

Adding ntfy or Telegram later is one new file here, nothing else.
"""

from __future__ import annotations

import importlib
import pkgutil
from dataclasses import dataclass, field


@dataclass
class Incoming:
    channel: str
    sender: str
    subject: str
    text: str
    message_id: str = ""
    in_reply_to: str = ""
    references: list[str] = field(default_factory=list)
    trusted: bool = False
    reason: str = ""
    files: list[str] = field(default_factory=list)  # saved attachments' paths


def modules() -> dict:
    found = {}
    for info in pkgutil.iter_modules(__path__):
        module = importlib.import_module(f"{__name__}.{info.name}")
        if hasattr(module, "NAME") and hasattr(module, "send"):
            found[module.NAME] = module
    return found


def ready(settings: dict) -> dict:
    return {n: m for n, m in modules().items() if m.configured(settings)}
