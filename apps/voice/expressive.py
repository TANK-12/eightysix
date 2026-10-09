"""Emotion and sound tags in text to speak: "[angry] I told you. [sigh]".

The vocabulary, and how each expressive engine style renders a tag, live in
shared/voice_emotions.json. A model row with "expressive": "<style>" gets the
tags rendered its way by its engine; every other row gets them taken out
(plain()), so a plain voice never reads "angry" aloud. Bracket text that is
not a known tag stays as it was: "(see above)" is still read. Moods need
square brackets; round ones take only the tags marked "round" (sounds and
pauses: "(laughs)"), so "(normal)" or "(quiet)" in a sentence stay words.
Full-width brackets (［怒り］, （笑）) count too.
"""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MOODS = ("emotion", "delivery")
_BRACKET = re.compile(
    r"[\[［]([^\[\]［］\n]{1,60})[\]］]|[(（]([^()（）\n]{1,60})[)）]"
)
_OPENERS = ("[", "(", "［", "（")
# a markdown marker at a line start: heading, list item, quote, table row
_MARKER = re.compile(
    r"[ \t]*(?:#{1,6}[ \t]+|[-*+][ \t]+|\d+[.)][ \t]+|>[ \t]*|\|[ \t]*)"
)
_EMPTY = {"tags": {}, "styles": {}, "names": {}}
log = logging.getLogger("voice.expressive")
_SPACES = re.compile(r"[ \t]{2,}")
_SPACE_PUNCT = re.compile(r"[ \t]+([,.!?;:。、！？])")
_cache: dict = {}


def vocab_path() -> Path:
    shared = os.environ.get("FORGE_SHARED_DIR") or ROOT.parent.parent / "shared"
    return Path(shared) / "voice_emotions.json"


def vocab() -> dict:
    """voice_emotions.json plus an alias -> tag table, re-read when it changes."""
    p = vocab_path()
    try:
        key = (str(p), p.stat().st_mtime_ns)
    except OSError:
        return _EMPTY
    if _cache.get("key") != key:
        try:
            d = json.loads(p.read_text())
            styles = d.get("styles")
            if not (
                isinstance(d.get("tags"), dict)
                and isinstance(styles, dict)
                and all(isinstance(s, dict) for s in styles.values())
                and all(isinstance(s.get("map", {}), dict) for s in styles.values())
            ):
                raise ValueError("it needs a tags table and a styles table")
            names = {}
            for tag, t in d.get("tags", {}).items():
                for a in (tag, *t.get("aliases", [])):
                    names[a.lower()] = tag
        except (OSError, ValueError, AttributeError, TypeError) as e:
            # a typo in the file must not stop every voice: the last good list
            kept = "keeping the last good tags" if "data" in _cache else "no tags"
            log.warning("%s unreadable, %s: %s", p, kept, e)
            _cache.setdefault("data", _EMPTY)
            _cache["key"] = key
            return _cache["data"]
        _cache.clear()
        _cache.update(key=key, data=dict(d, names=names))
    return _cache["data"]


def _tags(inner: str, names: dict) -> list[str] | None:
    parts = [" ".join(p.lower().split()) for p in inner.split(",")]
    tags = [names.get(p) for p in parts]
    return [t for t in tags if t] if all(tags) else None


def _known(m: re.Match, v: dict) -> list[str] | None:
    """The tags a bracket match holds, or None when it is just text: round
    brackets take only tags marked "round" in the vocabulary, except the
    full-width （…） Japanese scripts write every direction in."""
    tags = _tags(m.group(1) or m.group(2), v["names"])
    if tags is None or m.group(1) is not None or m.group(0).startswith("（"):
        return tags
    return tags if all(v["tags"].get(t, {}).get("round") for t in tags) else None


def parse(text: str) -> list[tuple[str, str]]:
    """The text as ("text", words) and ("tag", tag name) pieces, in order."""
    v = vocab()
    out: list[tuple[str, str]] = []
    at = 0
    for m in _BRACKET.finditer(text):
        tags = _known(m, v)
        if tags is None:
            continue
        if m.start() > at:
            out.append(("text", text[at : m.start()]))
        out += [("tag", t) for t in tags]
        at = m.end()
    if at < len(text):
        out.append(("text", text[at:]))
    return out


def kind(tag: str) -> str:
    return vocab()["tags"].get(tag, {}).get("kind", "")


def mood(pieces: list[tuple[str, str]]) -> str | None:
    """The first emotion or delivery tag: one mood per request."""
    for k, v in pieces:
        if k == "tag" and kind(v) in MOODS:
            return v
    return None


def style(name: str) -> dict:
    return vocab()["styles"].get(name or "plain") or vocab()["styles"].get("plain", {})


def render(pieces: list[tuple[str, str]], st: dict) -> str:
    """Tags as the style writes them (or nothing), spaces tidied."""
    mapping, tight = st.get("map") or {}, bool(st.get("tight"))
    out: list[str] = []
    eat = False
    for k, v in pieces:
        if k == "tag":
            mark = mapping.get(v, "")
            if mark and tight:  # no spaces around it (Japanese)
                if out:
                    out[-1] = out[-1].rstrip(" \t")
                out.append(mark)
            elif mark:
                out.append(" " + mark + " " if out else mark + " ")
            eat = eat or tight and bool(mark) or not mark
            continue
        out.append(v.lstrip(" \t") if eat else v)
        eat = False
    text = _SPACE_PUNCT.sub(r"\1", _SPACES.sub(" ", "".join(out)))
    return "\n".join(line.strip() for line in text.splitlines()).strip()


def _bracketed(text: str) -> bool:
    return any(c in text for c in _OPENERS)


def plain(text: str) -> str:
    """The text with every known tag taken out (pause becomes '...')."""
    if not _bracketed(text):
        return text
    return render(parse(text), style("plain"))


def prepare(text: str) -> str:
    """Tags kept whole through the markdown clean-up that runs before speech
    (speech_text): a space between a tag and a tag right after it, so
    "[sad](sigh)" is not read as a link (a real link such as "[Calm](url)"
    stays one), and a line of only tags joined to the next one, after its
    markdown marker, so "[angry]" on its own line does not become a sentence
    and "# Alert" under it is still a heading."""
    if not _bracketed(text):
        return text
    v = vocab()
    out: list[str] = []
    at = 0
    for m in _BRACKET.finditer(text):
        if _known(m, v) is None:
            continue
        out.append(text[at : m.end()])
        at = m.end()
        nxt = _BRACKET.match(text, at)
        if nxt and _known(nxt, v) is not None:
            out.append(" ")
    out.append(text[at:])
    lines: list[str] = []
    for line in "".join(out).split("\n"):
        fence = line.lstrip().startswith(("```", "~~~"))
        if (
            lines
            and not fence
            and has_tags(lines[-1])
            and not re.search(r"\w", plain(lines[-1]))
        ):
            m = _MARKER.match(line)
            head = m.group(0) if m else ""
            lines[-1] = head + lines[-1].strip() + " " + line[len(head) :].lstrip()
        else:
            lines.append(line)
    return "\n".join(lines)


def has_tags(text: str) -> bool:
    return any(k == "tag" for k, _ in parse(text))
