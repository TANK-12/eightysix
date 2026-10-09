"""Natural phrasing for voice commands (acchan/phrases.py): natural sentences
reach the right tool with the right arguments, and chit-chat or questions
that are not commands do not match at all."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from acchan import phrases, registry  # noqa: E402

registry.load_all()

POSITIVE = [
    ("could you open firefox", "launch_app", {"name": "firefox"}),
    ("Hey Acchan, open Steam please.", "launch_app", {"name": "steam"}),
    ("um can you fire up the file explorer", "launch_app", {"name": "file explorer"}),
    ("bring up qobuz for me", "launch_app", {"name": "qobuz"}),
    ("turn it down to 30", "set_volume", {"percent": 30}),
    ("turn the volume up to 80 percent", "set_volume", {"percent": 80}),
    ("volume 40", "set_volume", {"percent": 40}),
    ("set the volume to 55%", "set_volume", {"percent": 55}),
    ("what's playing", "now_playing", {}),
    ("what song is this?", "now_playing", {}),
    ("what am I listening to", "now_playing", {}),
    ("pause the music", "media_control", {"action": "pause"}),
    ("skip this song", "media_control", {"action": "next"}),
    ("next track please", "media_control", {"action": "next"}),
    ("go back a song", "media_control", {"action": "previous"}),
    ("resume", "media_control", {"action": "play"}),
    ("what time is it", "what_time", {}),
    ("what's the time", "what_time", {}),
    ("what's the weather", "weather", {}),
    ("what's the weather like in Perth", "weather", {"place": "perth"}),
    ("search for rust borrow checker", "open_web", {"address": "rust borrow checker"}),
    ("look up the weather radar", "open_web", {"address": "weather radar"}),
    ("switch to the youtube tab", "switch_tab", {"tab": "youtube"}),
    ("switch to workspace 3", "switch_workspace", {"workspace": "3"}),
    ("switch to firefox", "focus_window", {"window": "firefox"}),
    ("make it fullscreen", "fullscreen_window", {}),
    ("what tabs do I have open", "browser_tabs", {}),
    ("make the screen brighter", "set_brightness", {"percent": "+10"}),
    ("brightness 60", "set_brightness", {"percent": "60"}),
    ("paus the musik", "media_control", {"action": "pause"}),  # mis-heard
]

NEGATIVE = [
    "how are you",
    "tell me a joke",
    "what do you think about python",
    "open your heart to me",
    "why is the sky blue",
    "can you explain how the volume knob works",
    "what is the meaning of life",
    "I had a long day at uni",
    "write me a poem about the sea",
    "what time does the shop close tomorrow",
    "what is the weather like on mars in a science fiction story",
    "summarise this document",
    "who won the world cup in 2022",
    "turn it down to a dull roar",
    "volume of a sphere",
    "thanks",
    "hello",
    "delete my notes",
    "run the tests",
    "close firefox",
]


@pytest.mark.parametrize("text,tool,args", POSITIVE)
def test_natural_sentences_match(text, tool, args):
    found = phrases.match(text)
    assert found is not None, text
    assert (found[0], found[1]) == (tool, args)
    assert found[2] >= phrases.THRESHOLD


@pytest.mark.parametrize("text", NEGATIVE)
def test_chit_chat_does_not_match(text):
    assert phrases.match(text) is None


def test_risky_tools_have_no_phrases():
    for entry in registry.TOOLS.values():
        if entry.risky:
            assert not entry.phrases, entry.name
    assert {p.tool for p in phrases.phrases()}.isdisjoint(
        {t.name for t in registry.TOOLS.values() if t.risky}
    )


def test_every_phrase_slot_is_a_parameter():
    for phrase in phrases.phrases():
        props = registry.TOOLS[phrase.tool].properties
        for name in [*phrase.slots, *phrase.fixed]:
            assert name in props, (phrase.tool, phrase.text, name)


def test_fillers_are_stripped():
    assert phrases.normalize(
        "Um, hey Acchan, could you please open the Steam app?"
    ) == ("open steam app")
