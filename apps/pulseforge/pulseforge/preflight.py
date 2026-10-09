"""
What would go wrong if you uploaded this.

Everything here is something the app already knows and you would otherwise find
out from YouTube, or from a comment. It is deliberately a *report*, not a gate:
each item says what it found, how much it matters, and what to do, and nothing
refuses to render.

Severities: "stop" is a real problem, "check" is worth a look, "fine" is
confirmation that something you might worry about is actually in order.
"""

import os

from . import tracklist
from .ffrunner import probe_media
from .sequence import measure_loudness

TARGET_LUFS = -14.0
LOUDNESS_TOLERANCE = 1.5
MIN_CHAPTER_VIDEO = 60.0


def _length(seconds):
    """Minutes reads badly for a short clip: "0 minutes" is not information."""
    if seconds >= 90:
        return f"{seconds / 60:.0f} minutes"
    return f"{seconds:.0f} seconds"


def _item(level, title, detail, fix=""):
    return {"level": level, "title": title, "detail": detail, "fix": fix}


def check_project(project, spans=None, duration=0.0):
    """Everything checkable before a render."""
    out = []
    songs = project.playlist_paths()
    if not songs:
        return [
            _item(
                "stop",
                "No songs",
                "This project has no audio yet.",
                "Add songs on the Compose tab.",
            )
        ]

    missing = [s for s in songs if not os.path.exists(s)]
    if missing:
        out.append(
            _item(
                "stop",
                "Missing audio",
                f"{len(missing)} song(s) in the playlist are gone from disk.",
                "Remove them from the playlist or put the files back.",
            )
        )

    shots = project.data.get("shots") or []
    if not shots:
        out.append(
            _item(
                "check",
                "No shots",
                "Nothing has been set up in the Scenery tab, so this will "
                "render a plain gradient.",
                "Add a background and press Find the moving parts.",
            )
        )
    else:
        no_image = [
            i
            for i, sh in enumerate(shots)
            if not sh.get("image") and sh.get("kind") != "card"
        ]
        if no_image:
            out.append(
                _item(
                    "check",
                    "Shots with no background",
                    f"Shot(s) {', '.join(str(i + 1) for i in no_image)} have "
                    "no image and are not cards.",
                    "Pick a background, or mark them as cards.",
                )
            )

    if spans:
        items = tracklist.entries(
            spans, project.data.get("cards") or [], [os.path.basename(s) for s in songs]
        )
        warnings = list(tracklist.warnings_for(items))
        if duration and duration < MIN_CHAPTER_VIDEO and len(items) >= 3:
            warnings.append(
                f"{duration:.0f} seconds with {len(items)} chapters -- YouTube tends "
                "to ignore chapters on very short videos."
            )
        for warning in warnings:
            out.append(
                _item(
                    "check",
                    "Chapters",
                    warning,
                    "Chapters are optional; the tracklist is still useful.",
                )
            )
        if not warnings:
            # only say chapters are fine when nothing above has said otherwise
            out.append(
                _item("fine", "Chapters", f"{len(items)} chapter(s) look usable.")
            )

    untitled = [
        i
        for i, c in enumerate(project.data.get("cards") or [])
        if not (c or {}).get("title")
    ]
    if untitled and len(untitled) == len(songs):
        out.append(
            _item(
                "check",
                "No track titles",
                "None of the songs have a title, so the tracklist will use "
                "their filenames.",
                "Name them on the Compose tab.",
            )
        )

    gains = project.data.get("song_gain") or []
    if not gains and len(songs) > 1:
        levels = [measure_loudness(s) for s in songs]
        usable = [x for x in levels if x is not None]
        if len(usable) > 1 and (max(usable) - min(usable)) > 4.0:
            out.append(
                _item(
                    "check",
                    "Songs jump in volume",
                    f"The playlist spans {max(usable) - min(usable):.1f} dB "
                    "between its quietest and loudest track.",
                    "Press Level the playlist on the Compose tab.",
                )
            )
        elif usable:
            out.append(_item("fine", "Levels", "The playlist is already even."))
    return out


def check_render(path, expect_duration=None):
    """Everything checkable about a finished file."""
    out = []
    if not path or not os.path.exists(path):
        return [
            _item(
                "stop",
                "No render",
                "There is no finished file to check yet.",
                "Render first.",
            )
        ]
    info = probe_media(path)
    size = os.path.getsize(path)
    dur = float(info.get("duration") or 0.0)
    w, h = info.get("width"), info.get("height")

    if not info.get("has_audio"):
        out.append(
            _item(
                "stop",
                "No audio track",
                "The file has no sound in it.",
                "Check the render log for an audio error.",
            )
        )
    else:
        out.append(_item("fine", "Audio", "The file has a muxed audio track."))

    lufs = measure_loudness(path)
    if lufs is None:
        out.append(_item("check", "Loudness", "Could not be measured."))
    elif abs(lufs - TARGET_LUFS) > LOUDNESS_TOLERANCE:
        out.append(
            _item(
                "check",
                "Loudness",
                f"{lufs:.1f} LUFS; YouTube normalises toward {TARGET_LUFS:.0f}.",
                "Adjust the loudness target in Settings and re-render.",
            )
        )
    else:
        out.append(_item("fine", "Loudness", f"{lufs:.1f} LUFS, on target."))

    if w and h:
        ratio = w / h
        known = {"16:9": 16 / 9, "9:16": 9 / 16, "4:3": 4 / 3, "1:1": 1.0}
        near = min(known, key=lambda k: abs(known[k] - ratio))
        if abs(known[near] - ratio) > 0.02:
            out.append(
                _item(
                    "check",
                    "Unusual shape",
                    f"{w}x{h} is not a standard ratio.",
                    "Pick one of the built-in formats.",
                )
            )
        else:
            out.append(_item("fine", "Shape", f"{w}x{h} ({near})."))

    if expect_duration and dur and abs(dur - expect_duration) > 1.0:
        out.append(
            _item(
                "check",
                "Length",
                f"The file is {dur:.0f}s; {expect_duration:.0f}s was expected.",
                "Check the render log for a truncated encode.",
            )
        )

    gb = size / 1e9
    if gb > 100:
        out.append(
            _item(
                "check",
                "Very large file",
                f"{gb:.1f} GB.",
                "YouTube's limit is 256 GB, but the upload will take a while.",
            )
        )
    else:
        out.append(
            _item(
                "fine",
                "File size",
                f"{size / 1e6:.0f} MB for {_length(dur)}.",
            )
        )
    return out


def summarise(items):
    counts = {"stop": 0, "check": 0, "fine": 0}
    for it in items:
        counts[it["level"]] = counts.get(it["level"], 0) + 1
    return counts
