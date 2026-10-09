"""No CSS transition on the always-open pages lasts for minutes (task 63).

WHY THIS EXISTS
    The final analyst of the 2026-10-07 overhaul found `#wall-tint` with
    `transition: background-color 60s linear`, while WallFx.tint() sets a new
    colour every 60 s. The fade was therefore always running: a full-window
    style, paint and composite on every display frame, on home, in apps, on
    battery and in lite mode, never capped by ForgeFrameCap
    (sessions/2026-10-07-overhaul/critics/final-analyst.md, audit item 3).
    A short fade keeps the look and runs for a few seconds a minute.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGES = ("hub/index.html", "desktop/particles.html")
LIMIT_S = 5.0

DURATION = re.compile(r"(?<![\w.-])(\d*\.?\d+)(ms|s)\b")


def long_transitions(text: str) -> list[str]:
    found = []
    for m in re.finditer(r"transition(?:-duration)?\s*:\s*([^;}]*)", text):
        for value, unit in DURATION.findall(m.group(1)):
            seconds = float(value) / (1000 if unit == "ms" else 1)
            if seconds >= LIMIT_S:
                found.append(m.group(0).strip())
    return found


def test_scanner_sees_a_long_fade():
    assert long_transitions("#x { transition: background-color 60s linear; }")
    assert long_transitions("#x { transition-duration: 9000ms }")
    assert not long_transitions("#x { transition: opacity .25s, transform 2s; }")


def test_no_page_has_a_transition_of_five_seconds_or_more():
    for page in PAGES:
        text = (ROOT / page).read_text()
        assert long_transitions(text) == [], page
