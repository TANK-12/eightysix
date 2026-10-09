"""
The description you paste under the video.

Every long mix needs a tracklist with timestamps, and writing one by hand for a
twenty-track upload is miserable -- while the app already knows every number
involved. So it writes the description, in YouTube's chapter format, and also
embeds the chapter marks in the MP4 itself so players show them on the scrubber.

YouTube's rules for turning a description into chapters are specific and easy to
miss, so they are checked rather than assumed: the first mark must be `0:00`,
there must be at least three, and each must run at least ten seconds. Anything
that fails comes back as a plain-language warning instead of silently producing
a video with no chapters on it.
"""

MIN_CHAPTERS = 3
MIN_CHAPTER_SECONDS = 10.0


def timestamp(seconds):
    """`0:07`, `4:31`, `1:02:03` -- the format YouTube parses."""
    total = max(0, int(round(float(seconds))))
    h, rest = divmod(total, 3600)
    m, s = divmod(rest, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def entries(spans, cards, songs=None):
    """One `{start, end, title}` per play, titled from the card or the filename.

    Titles **wrap**: a repeating playlist has many more spans than songs, and
    the fourth play of track one is still track one, not "Track 7".
    """
    out = []
    for i, span in enumerate(spans):
        card = (cards[i % len(cards)] if cards else {}) or {}
        title = (card.get("title") or "").strip()
        if not title and songs:
            name = str(songs[i % len(songs)]).rsplit("/", 1)[-1]
            title = name.rsplit(".", 1)[0].replace("-", " ").replace("_", " ").strip()
        if not title:
            title = f"Track {i % max(1, len(songs or cards or [1])) + 1}"
        sub = (card.get("subtitle") or "").strip()
        out.append(
            {
                "start": float(span["start"]),
                "end": float(span["end"]),
                "title": title,
                "subtitle": sub,
            }
        )
    return out


def warnings_for(items):
    """What would stop YouTube turning this into chapters."""
    out = []
    if not items:
        return ["No songs yet, so there is nothing to list."]
    if items[0]["start"] > 0.4:
        out.append("The first chapter has to start at 0:00.")
    if len(items) < MIN_CHAPTERS:
        out.append(
            f"YouTube needs at least {MIN_CHAPTERS} chapters; this has "
            f"{len(items)}. The tracklist is still worth pasting in."
        )
    short = [
        it["title"] for it in items if (it["end"] - it["start"]) < MIN_CHAPTER_SECONDS
    ]
    if short:
        out.append(
            "Under ten seconds, so they will not become chapters: "
            + ", ".join(short[:4])
            + ("…" if len(short) > 4 else "")
        )
    return out


def description(items, header="", footer=""):
    """The block of text to paste into the video description."""
    lines = []
    if header:
        lines += [header.rstrip(), ""]
    for it in items:
        line = f"{timestamp(it['start'])} {it['title']}"
        if it["subtitle"]:
            line += f" — {it['subtitle']}"
        lines.append(line)
    if footer:
        lines += ["", footer.rstrip()]
    return "\n".join(lines) + "\n"


def ffmetadata(items, total):
    """An ffmpeg metadata file, so the marks live in the MP4 itself."""
    out = [";FFMETADATA1"]
    for i, it in enumerate(items):
        end = items[i + 1]["start"] if i + 1 < len(items) else max(total, it["end"])
        out += [
            "",
            "[CHAPTER]",
            "TIMEBASE=1/1000",
            f"START={int(round(it['start'] * 1000))}",
            f"END={int(round(max(end, it['start'] + 0.001) * 1000))}",
            # '=', ';', '#' and newlines are the characters ffmetadata treats
            # specially; everything else can go through as it is
            "title=" + _esc(it["title"]),
        ]
    return "\n".join(out) + "\n"


def _esc(text):
    out = str(text)
    for ch in ("\\", "=", ";", "#"):
        out = out.replace(ch, "\\" + ch)
    return out.replace("\n", " ")


def build(spans, cards, songs=None, total=None, header="", footer=""):
    """Everything at once, for the API and the renderer."""
    items = entries(spans, cards, songs)
    return {
        "items": items,
        "description": description(items, header, footer),
        "ffmetadata": ffmetadata(items, total if total is not None else 0.0),
        "warnings": warnings_for(items),
    }
