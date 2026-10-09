"""
Output formats. Each entry is a target the render pipeline knows how to fill.

`loop` is a modifier, not a resolution: it renders a clean N-second visual bed
and repeats it to the audio's length, so a 40-second loop can carry an
hour-long mix ("lofi radio" uploads).
"""

FORMATS = {
    "long_1080p": {
        "label": "YouTube 1080p (16:9)",
        "w": 1920,
        "h": 1080,
        "fps": 30,
        "notes": "The default long-form video. One song, one MP4.",
    },
    "uhd_2160p": {
        "label": "YouTube 4K (16:9)",
        "w": 3840,
        "h": 2160,
        "fps": 30,
        "notes": "Slow on a CPU-only box -- a full song is an overnight render.",
    },
    "shorts_1080x1920": {
        "label": "Shorts / Reels (9:16)",
        "w": 1080,
        "h": 1920,
        "fps": 30,
        "notes": "Vertical. Keep it under 60s for YouTube Shorts.",
    },
    "loop_1080p": {
        "label": "Seamless loop (16:9 1080p)",
        "w": 1920,
        "h": 1080,
        "fps": 30,
        "loop": True,
        "loop_seconds": 40,
        "notes": "Renders a short seamless visual bed, then repeats it under the "
        "full audio. For 'radio' style long uploads.",
    },
}

DEFAULT_FORMAT = "long_1080p"


def get(fmt_id):
    return FORMATS.get(fmt_id, FORMATS[DEFAULT_FORMAT])


def as_list():
    return [{"id": k, **v} for k, v in FORMATS.items()]
