"""Remembering things between chats: facts the user asks Acchan to keep."""

from __future__ import annotations

from typing import Annotated

from .. import memory
from ..registry import ToolError, tool

TOOLSET = "memory"
TOOLSET_SUMMARY = "remember, recall and forget facts about the user between chats"
TOOLSET_KEYWORDS = (
    "remember",
    "recall",
    "forget",
    "memory",
    "do you know",
    "my name",
    "my birthday",
    "i like",
    "i love",
    "i hate",
    "my favourite",
    "my favorite",
    "don't forget",
    "note that",
)
TOOLSET_EXAMPLES = [
    (
        "remember that my exam is on the 3rd of November",
        "remember",
        {"fact": "Emerson's exam is on 3 November"},
    ),
    ("what do you remember about my exams?", "recall", {"query": "exam"}),
]


@tool(TOOLSET, example={"fact": "Emerson's favourite colour is teal"}, voice="ok")
def remember(fact: Annotated[str, "One short fact, written in full"]) -> str:
    """Save a fact about the user to remember in every future chat."""
    if not fact.strip():
        raise ToolError("Give the fact to remember as one short sentence.")
    return (
        f"Remembered: {fact.strip()}"
        if memory.add(fact)
        else f"I already knew that: {fact.strip()}"
    )


@tool(TOOLSET, example={"query": "birthday"}, show=True, voice="ok")
def recall(
    query: Annotated[str, "A word or two to look for; empty for all"] = "",
) -> str:
    """Look up saved facts about the user."""
    found = memory.search(query)
    return "\n".join(f"- {f}" for f in found) if found else "Nothing saved about that."


@tool(TOOLSET, example={"fact": "exam"})
def forget(fact: Annotated[str, "Words from the fact to forget"]) -> str:
    """Delete saved facts that contain these words."""
    gone = memory.remove(fact)
    if not gone:
        raise ToolError(f"No saved fact contains {fact!r}. Use recall to see them.")
    return "Forgot: " + "; ".join(gone)
