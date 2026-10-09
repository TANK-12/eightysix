"""
The AMV scene -- cut a folder of video clips to the music, properly.

The older `montage` scene is still here and still works: it cuts on detected
beats and matches busy footage to loud parts. This one keeps that idea and
replaces everything underneath it.

    where the cuts go     `musicmap` -- a real beat grid, bar lines, and the
                          song's sections, so a shot is two *bars* long and
                          lands on the bar line at any tempo
    what fills them       `shotdna` -- every stretch of every clip measured for
                          business, shot scale, sharpness, colour and which way
                          the camera is moving
    how it is cut         `editstyles` -- eleven declarative styles that set the
                          pace per section, what footage each section wants,
                          which beat effects fire and what goes between shots
    the actual choosing   `amvplan` -- one global assignment over the whole
                          video rather than a greedy walk

Attach a folder of clips in Compose, pick a style, and turn the one intensity
control up or down. Everything else has a sensible default and can be opened up
if you want it.
"""

import os

from .. import amvplan, editstyles, musicmap

SCENE = {
    "id": "amv",
    "label": "AMV Studio (beat-cut editor)",
    "family": "amv",
    "description": "Cuts a folder of video clips to the song's structure -- bars, not seconds. "
    "Picks each shot by what is actually in it, fires effects on the beat, and "
    "changes its pacing between the verse and the chorus.",
    "params": [
        {
            "key": "style",
            "label": "Editing style",
            "type": "select",
            "default": editstyles.DEFAULT_STYLE,
            "options": list(editstyles.STYLES.keys()),
            "help": "Sets the pace, the shot choice, the effects and the transitions together.",
        },
        {
            "key": "intensity",
            "label": "Intensity",
            "type": "float",
            "default": 1.0,
            "min": 0.2,
            "max": 2.5,
            "help": "One control for the whole edit. Up shortens every shot and pushes every "
            "effect harder; down lets it breathe.",
        },
        {
            "key": "min_shot",
            "label": "Shortest shot (seconds)",
            "type": "float",
            "default": 0.25,
            "min": 0.1,
            "max": 4.0,
        },
        {
            "key": "max_shot",
            "label": "Longest shot (seconds)",
            "type": "float",
            "default": 12.0,
            "min": 0.5,
            "max": 60.0,
        },
        {
            "key": "fit",
            "label": "Fit",
            "type": "select",
            "default": "cover",
            "options": ["cover", "contain"],
        },
        {
            "key": "crop_letterbox",
            "label": "Crop black bars off the clips",
            "type": "bool",
            "default": True,
            "help": "Anime rips usually carry bars. Without this they get scaled up into the frame.",
        },
        {
            "key": "reuse_penalty",
            "label": "Spread the footage",
            "type": "float",
            "default": 0.55,
            "min": 0.0,
            "max": 3.0,
            "help": "How hard to avoid using the same piece of footage twice. Higher uses more of "
            "your folder and cares less about matching the music.",
        },
        {
            "key": "transition_override",
            "label": "Force one transition",
            "type": "select",
            "default": "",
            "options": [""] + list(editstyles.TRANSITIONS.keys()),
            "help": "Leave blank to let the style decide, which is usually better.",
        },
        {
            "key": "analysis_seconds",
            "label": "Analyse this much of each clip (0 = all)",
            "type": "int",
            "default": 0,
            "min": 0,
            "max": 3600,
            "help": "Looking at only the first few minutes of very long files makes the first "
            "plan much faster. It is cached either way.",
        },
    ],
}


def _pool_dir(ctx):
    for a in ctx.assets:
        if a and os.path.isdir(a):
            return a
    return None


def build_edl(ctx):
    """The planned edit for this project, or [] if there is nothing to cut."""
    pool = _pool_dir(ctx)
    if not pool:
        return []
    progress = getattr(ctx, "progress", None)
    dna = amvplan.scan_and_analyse(
        pool,
        progress=progress,
        max_seconds=int(ctx.p("analysis_seconds", 0) or 0),
    )
    dna = {k: v for k, v in dna.items() if v.get("segments")}
    if not dna:
        return []

    music = musicmap.map_music(ctx.feat)
    style = editstyles.get_style(ctx.p("style", editstyles.DEFAULT_STYLE))
    result = plan_for(ctx, music, dna, style)
    return result["shots"]


def plan_for(ctx, music, dna, style):
    """The planner call, kept separate so the editor can show a plan without
    rendering one."""
    out = amvplan.plan(
        music,
        dna,
        style,
        ctx.duration,
        {
            "intensity": float(ctx.p("intensity", 1.0)),
            "min_shot": float(ctx.p("min_shot", 0.25)),
            "max_shot": float(ctx.p("max_shot", 12.0)),
            "fit": ctx.p("fit", "cover"),
            "crop_letterbox": bool(ctx.p("crop_letterbox", True)),
            "reuse_penalty": float(ctx.p("reuse_penalty", 0.55)),
        },
    )
    forced = ctx.p("transition_override", "") or ""
    if forced and forced in editstyles.TRANSITIONS:
        meta = editstyles.TRANSITIONS[forced]
        for i, sh in enumerate(out["shots"]):
            if i == 0:
                continue
            sh["transition"] = meta["id"]
            sh["transition_ms"] = int(meta["ms"])
    return out


def frames(ctx):  # pragma: no cover - the AMV path renders from build_edl()
    raise RuntimeError("amv is rendered from build_edl(), not frames()")
