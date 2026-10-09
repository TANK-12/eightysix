"""
Things drawn over the finished video: what's playing, and how far through it is.

These belong in the **assembly pass**, not in the shot beds. A bed is a few
seconds of picture repeated for the length of a song, so anything that has to
change as the mix moves on cannot live inside one. Building them as ffmpeg
filters instead means a three-hour video costs a handful of filter expressions
rather than three hours of drawing.

The progress bar is a full-width bar slid in from the left by `overlay`, which
costs two filters for the whole video however long it runs. It is deliberately
*not* a `drawbox` with a width expression: `drawbox` has no time variable -- its
`t` is the border thickness -- so such a bar sits at full width forever. That
shipped once and only measuring the rendered frames caught it.
"""

MAX_ENTRIES = 300  # a filter graph with thousands of drawtexts is not worth it

POSITIONS = {
    "bottom-left": ("{pad}", "h-th-{pad}"),
    "bottom-right": ("w-tw-{pad}", "h-th-{pad}"),
    "top-left": ("{pad}", "{pad}"),
    "top-right": ("w-tw-{pad}", "{pad}"),
}


def escape(text):
    """Escape for ffmpeg's `drawtext`, which treats these specially."""
    return (
        str(text or "")
        .replace("\\", "\\\\")
        .replace(":", "\\:")
        .replace("'", "’")
        .replace("%", "\\%")
        .replace("\n", " ")
    )


def bar_height(out_h, thickness=0.006):
    return max(2, int(float(thickness) * out_h))


def progress_track(out_h, opacity=0.8, thickness=0.006):
    """The dim groove the fill runs along. Static, so a plain filter will do."""
    h = bar_height(out_h, thickness)
    op = max(0.0, min(1.0, float(opacity))) * 0.18
    return f"drawbox=x=0:y=ih-{h}:w=iw:h={h}:color=white@{op:.3f}:t=fill"


def progress_input(out_w, out_h, thickness=0.006, color="white"):
    """ffmpeg input arguments for the moving fill.

    The fill has to be an `overlay`, not a `drawbox`. **`drawbox` has no notion
    of time** -- its `t` is the border *thickness* -- so a width expression
    using `t` reads a constant and the bar simply sits at full width for the
    whole video. That shipped once and was caught only by measuring the
    rendered frames. `overlay` does take the timestamp, so the fill is a
    full-width bar slid in from the left instead.
    """
    h = bar_height(out_h, thickness)
    return ["-f", "lavfi", "-i", f"color=c={color}:s={int(out_w)}x{h}"]


def progress_overlay(duration, out_w, in_label, bar_index, out_label, opacity=0.8):
    """The filter that slides the fill across as the video plays."""
    op = max(0.0, min(1.0, float(opacity)))
    slide = f"-({int(out_w)}*(1-t/{max(0.001, float(duration)):.3f}))"
    return (
        f"[{bar_index}:v]format=rgba,colorchannelmixer=aa={op:.3f}[pbar];"
        f"[{in_label}][pbar]overlay=x='{slide}':y=H-h:format=auto[{out_label}]"
    )


def now_playing(
    spans,
    cards,
    songs=None,
    out_h=1080,
    position="bottom-left",
    opacity=0.8,
    size="s",
    prefix="",
):
    """A small line naming the current track, up the whole time it plays.

    Different from the title cards in `sequence.text_filter()`, which announce a
    song and then get out of the way; this is the persistent "what is this"
    label those channels keep in a corner.
    """
    # No decorative glyph by default: ffmpeg falls back to whatever font it
    # finds, and a music note that the font lacks renders as an empty box.
    if not spans:
        return ""
    scale = {"s": 0.022, "m": 0.030, "l": 0.040}.get(str(size), 0.022)
    px = max(12, int(out_h * scale))
    pad = max(16, int(out_h * 0.035))
    ax, ay = POSITIONS.get(str(position), POSITIONS["bottom-left"])
    ax, ay = ax.format(pad=pad), ay.format(pad=pad)
    op = max(0.0, min(1.0, float(opacity)))

    parts = []
    for i, span in enumerate(spans[:MAX_ENTRIES]):
        title = ""
        idx = i % max(1, len(cards)) if cards else 0
        if cards and idx < len(cards):
            title = (cards[idx] or {}).get("title") or ""
        if not title and songs:
            name = str(songs[i % len(songs)]).rsplit("/", 1)[-1]
            title = name.rsplit(".", 1)[0].replace("-", " ").replace("_", " ")
        if not title:
            continue
        parts.append(
            f"drawtext=text='{escape(prefix + title)}':fontcolor=white@{op:.3f}"
            f":fontsize={px}:x={ax}:y={ay}"
            f":enable='between(t,{span['start']:.2f},{span['end']:.2f})'"
            f":shadowcolor=black@0.6:shadowx=2:shadowy=2"
        )
    return ",".join(parts)


def build(project_overlay, spans, cards, songs, duration, out_h):
    """The whole overlay chain for a render, or an empty string."""
    cfg = project_overlay or {}
    chain = []
    if cfg.get("now_playing"):
        chain.append(
            now_playing(
                spans,
                cards,
                songs,
                out_h=out_h,
                position=cfg.get("position", "bottom-left"),
                opacity=cfg.get("opacity", 0.8),
                size=cfg.get("size", "s"),
            )
        )
    if cfg.get("progress"):
        chain.append(progress_track(out_h, cfg.get("opacity", 0.8)))
    return ",".join(c for c in chain if c)


def wants_progress(project_overlay):
    return bool((project_overlay or {}).get("progress"))
