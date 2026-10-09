"""
Editing styles -- the registry that says *how* to cut, not just *where*.

Cutting on the beat is one decision. An editing style is the whole set of them:
how long a shot is held in a verse versus a chorus, what kind of footage each
section wants, which effects fire on which musical events, what happens between
shots, and where the picture slows down. Every one of those is data here, not
code, so a new style is one entry in `_STYLES` and nothing else changes -- the
API, the picker and the parameter form are generated from the table.

A style entry reads like a set of instructions to an assistant editor:

    pace        how long a shot is held, in BARS, per section kind
    prefer      what the shot picker should look for, per section kind
    fx          which beat effects fire, on what, in which sections
    transition  what goes between shots, and what is different at a section
                change or a drop
    speed       where the footage is slowed down or sped up

Section kinds come from `musicmap`: intro, verse, chorus, build, breakdown,
bridge, outro. `"*"` matches any of them, and `_default` catches anything the
style did not name, so a style is never obliged to be exhaustive.

The event vocabulary in `fx[].on`:

    beat            every beat of the shot
    downbeat        the first beat of each bar
    bar2            every other bar -- half as busy as downbeat
    hit             transients big enough to notice
    drop            where a build releases
    shot_start      once, at the top of the shot
    section_start   only if this shot begins a section

The craft behind the defaults is the ordinary advice of the form: cut with the
groove rather than only on the hook, hold longer through a breakdown and release
into the chorus, change the *kind* of sync between sections rather than doing
one thing for four minutes, and let the effects sit out most of the time so they
still mean something when they arrive.
"""

# --------------------------------------------------------------------------
# transitions -- every one checked against this machine's ffmpeg
# --------------------------------------------------------------------------
_TRANSITIONS = [
    ("cut", "Cut", None, 0, "Straight cut. The default, and right most of the time."),
    ("crossfade", "Crossfade", "fade", 250, "Softens the join. Good for slow music."),
    ("dissolve", "Dissolve", "dissolve", 280, "A grainier crossfade, film-like."),
    (
        "dip_black",
        "Dip to black",
        "fadeblack",
        300,
        "A beat of black between shots. Reads as a paragraph break.",
    ),
    (
        "dip_white",
        "Dip to white",
        "fadewhite",
        180,
        "A flash of white. Punchier than black, tiring in quantity.",
    ),
    (
        "whip_left",
        "Whip left",
        "slideleft",
        150,
        "Slams the next shot in from the right. Matches footage already moving left.",
    ),
    ("whip_right", "Whip right", "slideright", 150, "The same, the other way."),
    ("zoom_blur", "Zoom through", "zoomin", 220, "Pushes into the next shot."),
    ("blur_wipe", "Blur wipe", "hblur", 260, "Smears across the join."),
    (
        "pixel",
        "Pixelate",
        "pixelize",
        200,
        "Breaks into blocks and back. Digital, harsh.",
    ),
    ("radial", "Radial wipe", "radial", 300, "Sweeps round like a clock hand."),
    ("circle_open", "Iris open", "circleopen", 320, "Opens from the centre. Old-film."),
    ("squeeze", "Squeeze", "squeezeh", 200, "Crushes the outgoing shot away."),
    ("grey", "Through grey", "fadegrays", 300, "Drains the colour out and back in."),
    ("diagonal", "Diagonal wipe", "diagtl", 260, "Across the corner."),
    ("slice", "Slice", "hlslice", 220, "Cuts across in horizontal bands."),
    ("smooth_left", "Smooth left", "smoothleft", 240, "A soft directional push."),
    ("wipe_left", "Wipe left", "wipeleft", 200, "A hard edge travelling across."),
]

TRANSITIONS = {
    t[0]: {"id": t[0], "label": t[1], "xfade": t[2], "ms": t[3], "description": t[4]}
    for t in _TRANSITIONS
}


def transition_list():
    return [TRANSITIONS[t[0]] for t in _TRANSITIONS]


# --------------------------------------------------------------------------
# the styles
# --------------------------------------------------------------------------
_STYLES = [
    {
        "id": "classic",
        "label": "Classic beat cut",
        "description": "Cuts on the bar, tightens through the chorus, and stays out of the way. "
        "If you are not sure which to pick, pick this one.",
        "pace": {
            "intro": 4,
            "verse": 2,
            "chorus": 1,
            "build": 1,
            "breakdown": 4,
            "bridge": 2,
            "outro": 4,
            "_default": 2,
        },
        "prefer": {
            "intro": {"action": 0.2, "scale": "wide"},
            "verse": {"action": 0.4},
            "chorus": {"action": 0.8},
            "build": {"action": 0.5},
            "breakdown": {"action": 0.15},
            "outro": {"action": 0.2, "scale": "wide"},
            "_default": {"action": 0.5},
        },
        "fx": [
            {
                "id": "zoom_punch",
                "on": "downbeat",
                "in": ["chorus", "build"],
                "params": {"amount": 0.1},
            },
        ],
        "transition": {
            "default": "cut",
            "on_section": "dip_black",
            "on_drop": "dip_white",
        },
        "speed": {},
    },
    {
        "id": "hype",
        "label": "Hype",
        "description": "Fast, loud and shameless. Zoom punches on every bar, a flash on the drop, "
        "shake through the chorus. Made for a trailer or a hype edit.",
        "pace": {
            "intro": 2,
            "verse": 1,
            "chorus": 0.5,
            "build": 0.5,
            "breakdown": 2,
            "bridge": 1,
            "outro": 2,
            "_default": 1,
        },
        "prefer": {
            "intro": {"action": 0.3},
            "verse": {"action": 0.55},
            "chorus": {"action": 0.95},
            "build": {"action": 0.7},
            "_default": {"action": 0.7},
        },
        "fx": [
            {
                "id": "zoom_punch",
                "on": "downbeat",
                "in": ["*"],
                "params": {"amount": 0.18, "decay": 10},
            },
            {
                "id": "shake",
                "on": "drop",
                "in": ["chorus", "build"],
                "params": {"amount": 0.5},
            },
            {"id": "flash", "on": "drop", "in": ["*"], "params": {"amount": 0.5}},
            {
                "id": "sat_pump",
                "on": "downbeat",
                "in": ["chorus"],
                "params": {"amount": 0.4},
            },
        ],
        "transition": {
            "default": "cut",
            "on_section": "dip_white",
            "on_drop": "dip_white",
        },
        "speed": {},
    },
    {
        "id": "action",
        "label": "Action",
        "description": "Built for fight scenes. Cuts hard on the beat, matches the direction the "
        "camera is already travelling, and drops into slow motion on the hit.",
        "pace": {
            "intro": 2,
            "verse": 1,
            "chorus": 0.5,
            "build": 0.5,
            "breakdown": 2,
            "bridge": 1,
            "outro": 2,
            "_default": 1,
        },
        "prefer": {
            "intro": {"action": 0.4},
            "verse": {"action": 0.7},
            "chorus": {"action": 1.0},
            "build": {"action": 0.85},
            "breakdown": {"action": 0.3},
            "_default": {"action": 0.75},
        },
        "fx": [
            {
                "id": "zoom_punch",
                "on": "downbeat",
                "in": ["*"],
                "params": {"amount": 0.14},
            },
            {
                "id": "shake",
                "on": "hit",
                "in": ["chorus", "build"],
                "params": {"amount": 0.4, "decay": 9},
            },
            {"id": "blur_hit", "on": "drop", "in": ["*"], "params": {"sigma": 14}},
        ],
        "transition": {
            "default": "cut",
            "on_section": "whip",
            "on_drop": "zoom_blur",
            "match_direction": True,
        },
        "speed": {"drop": 0.55},
    },
    {
        "id": "emotional",
        "label": "Emotional",
        "description": "Long held shots and soft dissolves. Nothing flashes, nothing shakes. "
        "The camera drifts in slowly across each shot.",
        "pace": {
            "intro": 8,
            "verse": 4,
            "chorus": 2,
            "build": 4,
            "breakdown": 8,
            "bridge": 4,
            "outro": 8,
            "_default": 4,
        },
        "prefer": {
            "intro": {"action": 0.1, "scale": "wide"},
            "verse": {"action": 0.2, "scale": "close"},
            "chorus": {"action": 0.45},
            "breakdown": {"action": 0.08, "scale": "close"},
            "outro": {"action": 0.1, "scale": "wide"},
            "_default": {"action": 0.25},
        },
        "fx": [
            {
                "id": "push_in",
                "on": "shot_start",
                "in": ["*"],
                "params": {"amount": 0.07},
            },
        ],
        "transition": {
            "default": "crossfade",
            "on_section": "dissolve",
            "on_drop": "crossfade",
        },
        "speed": {},
    },
    {
        "id": "sakuga",
        "label": "Sakuga showcase",
        "description": "Finds the best-animated stretches in your clips and holds them. "
        "Cuts on the big hits rather than on every beat, so the animation gets room.",
        "pace": {
            "intro": 4,
            "verse": 2,
            "chorus": 2,
            "build": 2,
            "breakdown": 4,
            "bridge": 2,
            "outro": 4,
            "_default": 2,
        },
        "prefer": {
            "_default": {"action": 0.9, "quality": 1.0},
            "breakdown": {"action": 0.4, "quality": 1.0},
            "intro": {"action": 0.5, "quality": 1.0},
        },
        "fx": [
            {"id": "zoom_punch", "on": "drop", "in": ["*"], "params": {"amount": 0.1}},
        ],
        "transition": {"default": "cut", "on_section": "dip_black", "on_drop": "cut"},
        "speed": {},
    },
    {
        "id": "lyric",
        "label": "Lyric-led",
        "description": "Cuts where the singing changes rather than where the drum hits, and holds "
        "close shots under the vocal. Use it on a song with words that matter.",
        "pace": {
            "intro": 4,
            "verse": 2,
            "chorus": 1,
            "build": 2,
            "breakdown": 4,
            "bridge": 2,
            "outro": 4,
            "_default": 2,
        },
        "prefer": {
            "verse": {"action": 0.3, "scale": "close"},
            "chorus": {"action": 0.6, "scale": "close"},
            "intro": {"action": 0.2, "scale": "wide"},
            "_default": {"action": 0.4},
        },
        "fx": [
            {
                "id": "push_in",
                "on": "shot_start",
                "in": ["verse", "chorus"],
                "params": {"amount": 0.05},
            },
        ],
        "transition": {
            "default": "cut",
            "on_section": "crossfade",
            "on_drop": "dip_white",
        },
        "speed": {},
        "cut_on_vocal": True,
    },
    {
        "id": "retro",
        "label": "Retro tape",
        "description": "Grain, a chroma smear and a dip to white on every section. "
        "Looks like it was dubbed off a VHS in 1997, which is the point.",
        "pace": {
            "intro": 4,
            "verse": 2,
            "chorus": 1,
            "build": 2,
            "breakdown": 4,
            "bridge": 2,
            "outro": 4,
            "_default": 2,
        },
        "prefer": {"_default": {"action": 0.45}},
        "fx": [
            {"id": "grain", "on": "none", "in": ["*"], "params": {"amount": 16}},
            {
                "id": "chroma_ghost",
                "on": "none",
                "in": ["*"],
                "params": {"amount": 0.35},
            },
            {
                "id": "vignette_pulse",
                "on": "downbeat",
                "in": ["chorus"],
                "params": {"amount": 0.25},
            },
        ],
        "transition": {"default": "cut", "on_section": "dip_white", "on_drop": "pixel"},
        "speed": {},
    },
    {
        "id": "edit",
        "label": "Edit style",
        "description": "The short-form look: very fast cuts, colour tears, an inverted frame on the "
        "hit, bars slamming in. Exhausting over four minutes and perfect over forty seconds.",
        "pace": {
            "intro": 1,
            "verse": 0.5,
            "chorus": 0.5,
            "build": 0.5,
            "breakdown": 1,
            "bridge": 0.5,
            "outro": 1,
            "_default": 0.5,
        },
        "prefer": {"_default": {"action": 0.8}, "breakdown": {"action": 0.4}},
        "fx": [
            {
                "id": "zoom_punch",
                "on": "beat",
                "in": ["*"],
                "params": {"amount": 0.16, "decay": 14},
            },
            {
                "id": "rgb_split",
                "on": "hit",
                "in": ["chorus", "build"],
                "params": {"amount": 0.6},
            },
            {"id": "invert_hit", "on": "drop", "in": ["*"], "params": {"width": 0.05}},
            {
                "id": "bar_slam",
                "on": "section_start",
                "in": ["chorus"],
                "params": {"height": 0.11, "hold": 0.7},
            },
        ],
        "transition": {"default": "cut", "on_section": "pixel", "on_drop": "dip_white"},
        "speed": {},
    },
    {
        "id": "cinematic",
        "label": "Cinematic",
        "description": "Wide shots, black bars throughout, slow dissolves at every section. "
        "Restrained on purpose -- it is trying to look like a film, not an edit.",
        "pace": {
            "intro": 8,
            "verse": 4,
            "chorus": 2,
            "build": 4,
            "breakdown": 8,
            "bridge": 4,
            "outro": 8,
            "_default": 4,
        },
        "prefer": {
            "_default": {"action": 0.3, "scale": "wide"},
            "chorus": {"action": 0.5},
            "breakdown": {"action": 0.1, "scale": "wide"},
        },
        "fx": [
            {
                "id": "bar_slam",
                "on": "shot_start",
                "in": ["*"],
                "params": {"height": 0.12, "hold": 600.0},
            },
            {
                "id": "push_in",
                "on": "shot_start",
                "in": ["*"],
                "params": {"amount": 0.05},
            },
        ],
        "transition": {
            "default": "cut",
            "on_section": "dissolve",
            "on_drop": "dip_black",
        },
        "speed": {},
    },
    {
        "id": "chill",
        "label": "Chill",
        "description": "Barely edits at all. Very long shots, long dissolves, no effects. "
        "For a lofi mix where the footage should not be competing with the music.",
        "pace": {"_default": 8, "chorus": 8, "breakdown": 16, "intro": 8, "outro": 16},
        "prefer": {"_default": {"action": 0.12}, "chorus": {"action": 0.25}},
        "fx": [
            {
                "id": "push_in",
                "on": "shot_start",
                "in": ["*"],
                "params": {"amount": 0.06},
            }
        ],
        "transition": {
            "default": "crossfade",
            "on_section": "crossfade",
            "on_drop": "crossfade",
        },
        "speed": {},
    },
    {
        "id": "build_drop",
        "label": "Build and drop",
        "description": "Holds almost still through the build, tightening as it climbs, then lets go "
        "completely on the drop. Made for electronic music with one big moment.",
        "pace": {
            "intro": 8,
            "verse": 4,
            "build": 1,
            "chorus": 0.5,
            "breakdown": 8,
            "bridge": 4,
            "outro": 8,
            "_default": 2,
        },
        "prefer": {
            "build": {"action": 0.35},
            "chorus": {"action": 1.0},
            "breakdown": {"action": 0.1},
            "_default": {"action": 0.4},
        },
        "fx": [
            {
                "id": "push_in",
                "on": "shot_start",
                "in": ["build"],
                "params": {"amount": 0.18},
            },
            {
                "id": "shake",
                "on": "drop",
                "in": ["*"],
                "params": {"amount": 0.6, "decay": 5},
            },
            {"id": "flash", "on": "drop", "in": ["*"], "params": {"amount": 0.6}},
            {
                "id": "zoom_punch",
                "on": "downbeat",
                "in": ["chorus"],
                "params": {"amount": 0.2},
            },
        ],
        "transition": {
            "default": "cut",
            "on_section": "zoom_blur",
            "on_drop": "dip_white",
        },
        "speed": {"drop": 0.6},
    },
]

STYLES = {s["id"]: s for s in _STYLES}
DEFAULT_STYLE = "classic"


def get_style(style_id):
    return STYLES.get(style_id) or STYLES[DEFAULT_STYLE]


def styles_as_list():
    return [dict(s) for s in _STYLES]


def pace_for(style, kind):
    """Shot length in bars for a section of this kind."""
    pace = style.get("pace") or {}
    return float(pace.get(kind, pace.get("_default", 2)))


def prefer_for(style, kind):
    """What the shot picker should aim at in a section of this kind."""
    pref = style.get("prefer") or {}
    return dict(pref.get(kind, pref.get("_default", {"action": 0.5})))


def fx_for(style, kind):
    """The effect entries that apply in a section of this kind."""
    out = []
    for f in style.get("fx") or []:
        where = f.get("in") or ["*"]
        if "*" in where or kind in where:
            out.append(f)
    return out


__all__ = [
    "STYLES",
    "TRANSITIONS",
    "DEFAULT_STYLE",
    "get_style",
    "styles_as_list",
    "transition_list",
    "pace_for",
    "prefer_for",
    "fx_for",
]
