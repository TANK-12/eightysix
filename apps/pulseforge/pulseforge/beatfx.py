"""
The registry of beat-synced effects -- the things that fire *on* the music.

A cut on the beat is the floor, not the ceiling. What separates an edit that
feels alive from a slideshow is that the picture itself reacts: it snaps in on
the downbeat, shakes through the drop, flashes white on the hit, tears its
colours apart on the snare. Those are the moves this registry holds.

Each effect is one entry in `_FX` below: an id, a label, a plain description, a
family, a parameter schema, and a `build(events, p, ctx)` that returns an
**ffmpeg filter string**. `events` are times in seconds measured from the start
of the shot the effect is attached to; `ctx` carries that shot's width, height,
frame rate and duration. Adding an effect is one entry -- the API, the picker
and the parameter form are all generated from the table, the same way motion
effects and emitters already work.

Why filters rather than numpy: a montage decodes real video, and pushing every
frame of a five-minute AMV through Python would cost more than the encode. Every
expression here was checked against the ffmpeg on this machine before it was
written down, because half of the obvious spellings silently do nothing -- a
parameter that is not marked timeline-tunable accepts an expression, reads it
once, and holds that value for the whole shot, with no error anywhere.

The events themselves come from `musicmap`: beats, downbeats, hits and drops.
The planner in `amvplan.py` decides which effect gets which events.
"""

MAX_EVENTS = 10  # per shot; an expression with more is long and pointless


# --------------------------------------------------------------------------
# expression helpers
# --------------------------------------------------------------------------
def pulse(events, decay=8.0, var="t", limit=MAX_EVENTS):
    """An expression that spikes to 1 at each event and decays away.

    Written as nested `max()` rather than a sum so two events close together
    give one pulse of height 1, not one of height 2 -- which on a zoom is the
    difference between a punch and the picture leaving the frame."""
    ev = [float(e) for e in events][:limit]
    if not ev:
        return "0"
    terms = [f"(exp(-{decay:.3f}*({var}-{e:.4f}))*gte({var},{e:.4f}))" for e in ev]
    expr = terms[0]
    for t in terms[1:]:
        expr = f"max({expr},{t})"
    return expr


def windows(events, width=0.05, var="t", limit=MAX_EVENTS):
    """An `enable=` expression: true for `width` seconds after each event."""
    ev = [float(e) for e in events][:limit]
    if not ev:
        return "0"
    terms = [f"between({var},{e:.4f},{e + width:.4f})" for e in ev]
    expr = terms[0]
    for t in terms[1:]:
        expr = f"max({expr},{t})"
    return expr


def _even(n):
    """ffmpeg wants even dimensions for yuv420p."""
    n = int(round(n))
    return n + (n % 2)


# --------------------------------------------------------------------------
# the effects
# --------------------------------------------------------------------------
def _zoom_punch(events, p, ctx):
    a = float(p["amount"])
    if a <= 0.001:
        return ""
    # zoompan calls its clock `time`, not `t`
    z = f"1+{a:.3f}*({pulse(events, float(p['decay']), var='time')})"
    return (
        f"zoompan=z='{z}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
        f":d=1:s={_even(ctx['w'])}x{_even(ctx['h'])}:fps={ctx['fps']}"
    )


def _shake(events, p, ctx):
    a = float(p["amount"])
    if a <= 0.001:
        return ""
    m = max(2, int(round(a * 0.05 * ctx["h"])))
    w, h = _even(ctx["w"]), _even(ctx["h"])
    pw, ph = _even(w + 2 * m), _even(h + 2 * m)
    f = float(p["speed"])
    env = pulse(events, float(p["decay"]))
    # Grown a little, then cropped back with a moving window: the frame never
    # runs out of picture at the edge of the shake, which a plain translate does.
    return (
        f"scale={pw}:{ph},crop={w}:{h}"
        f":x='{m}+{m}*sin(2*PI*{f:.2f}*t)*({env})'"
        f":y='{m}+{m}*cos(2*PI*{f * 1.31:.2f}*t)*({env})'"
    )


def _push_in(events, p, ctx):
    """A steady drift in or out across the whole shot -- no events."""
    a = float(p["amount"])
    if abs(a) <= 0.001:
        return ""
    dur = max(0.05, float(ctx["dur"]))
    z = (
        f"1+{a:.4f}*(time/{dur:.3f})"
        if a > 0
        else f"{1 - a:.4f}+{a:.4f}*(time/{dur:.3f})"
    )
    return (
        f"zoompan=z='{z}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
        f":d=1:s={_even(ctx['w'])}x{_even(ctx['h'])}:fps={ctx['fps']}"
    )


def _flash(events, p, ctx):
    a = float(p["amount"])
    if a <= 0.001:
        return ""
    return f"eq=brightness='{a:.3f}*({pulse(events, float(p['decay']))})':eval=frame"


def _sat_pump(events, p, ctx):
    a = float(p["amount"])
    if abs(a) <= 0.001:
        return ""
    return f"eq=saturation='1+{a:.3f}*({pulse(events, float(p['decay']))})':eval=frame"


def _hue_kick(events, p, ctx):
    a = float(p["degrees"])
    if abs(a) <= 0.1:
        return ""
    return f"hue=h='{a:.2f}*({pulse(events, float(p['decay']))})'"


def _strobe(events, p, ctx):
    a = float(p["amount"])
    r = float(p["rate"])
    if a <= 0.001 or r <= 0:
        return ""
    return f"eq=brightness='{a:.3f}*lt(mod(t*{r:.3f},1),0.5)':eval=frame"


def _invert_hit(events, p, ctx):
    if not events:
        return ""
    return f"negate=enable='{windows(events, float(p['width']))}'"


def _blur_hit(events, p, ctx):
    s = float(p["sigma"])
    if s <= 0.05 or not events:
        return ""
    # gblur's sigma is not timeline-tunable in ffmpeg, so an expression there
    # would be read once and held. Gated on `enable` instead, which is.
    return f"gblur=sigma={s:.2f}:steps=1:enable='{windows(events, float(p['width']))}'"


def _rgb_split(events, p, ctx):
    a = float(p["amount"])
    if a <= 0.05 or not events:
        return ""
    px = max(1, int(round(a * 0.012 * ctx["w"])))
    # rgbashift's shifts are integer options: they are settable over the
    # timeline but they do not accept an expression, so `rh='4*t'` fails
    # outright with "undefined constant t". A gated window is the workable
    # spelling -- and a hard tear that lasts two frames on the hit is the look
    # anyway; a decaying one just smears it.
    return (
        f"rgbashift=rh={px}:bh={-px}" f":enable='{windows(events, float(p['width']))}'"
    )


def _chroma_ghost(events, p, ctx):
    a = float(p["amount"])
    if a <= 0.05:
        return ""
    px = max(1, int(round(a * 0.01 * ctx["w"])))
    return f"chromashift=cbh={px}:crh={-px}"


def _echo_trail(events, p, ctx):
    n = int(p["frames"])
    if n < 2:
        return ""
    return f"tmix=frames={n}:weights='{' '.join(['1'] * n)}'"


def _lens_warp(events, p, ctx):
    k = float(p["amount"])
    if abs(k) <= 0.005:
        return ""
    return f"lenscorrection=k1={-k:.4f}:k2={-k * 0.35:.4f}"


def _grain(events, p, ctx):
    n = int(p["amount"])
    if n <= 0:
        return ""
    return f"noise=alls={n}:allf=t"


def _vignette_pulse(events, p, ctx):
    a = float(p["amount"])
    if a <= 0.001:
        return ""
    env = pulse(events, float(p["decay"]))
    return f"vignette=angle='PI/4.2-{a * 0.5:.3f}*({env})':eval=frame"


def _bar_slam(events, p, ctx):
    """Cinema bars that slam in on the event and stay for `hold` seconds."""
    frac = float(p["height"])
    if frac <= 0.005 or not events:
        return ""
    en = windows(events, float(p["hold"]))
    return (
        f"drawbox=x=0:y=0:w=iw:h=ih*{frac:.3f}:color=black@1:t=fill:enable='{en}',"
        f"drawbox=x=0:y='ih*(1-{frac:.3f})':w=iw:h=ih*{frac:.3f}:color=black@1:t=fill"
        f":enable='{en}'"
    )


def _mirror(events, p, ctx):
    return "hflip" if p.get("on") else ""


# --------------------------------------------------------------------------
# the table
# --------------------------------------------------------------------------
def _amount(default=0.35, lo=0.0, hi=1.0, label="Strength"):
    return {
        "key": "amount",
        "label": label,
        "type": "float",
        "default": default,
        "min": lo,
        "max": hi,
    }


def _decay(default=8.0):
    return {
        "key": "decay",
        "label": "How fast it settles",
        "type": "float",
        "default": default,
        "min": 1.0,
        "max": 30.0,
        "help": "Higher settles quicker. 8 is about a fifth of a second.",
    }


_FX = [
    {
        "id": "zoom_punch",
        "label": "Zoom punch",
        "family": "camera",
        "description": "Snaps in on the beat and eases back out. The single most useful move in the list.",
        "params": [_amount(0.14, 0.0, 0.6, "How far it punches"), _decay(9.0)],
        "build": _zoom_punch,
    },
    {
        "id": "shake",
        "label": "Camera shake",
        "family": "camera",
        "description": "Knocks the frame around on the hit. Good on drops, tiring everywhere.",
        "params": [
            _amount(0.35, 0.0, 1.0, "How hard"),
            {
                "key": "speed",
                "label": "Wobble speed",
                "type": "float",
                "default": 9.0,
                "min": 2.0,
                "max": 30.0,
            },
            _decay(7.0),
        ],
        "build": _shake,
    },
    {
        "id": "push_in",
        "label": "Slow push",
        "family": "camera",
        "description": "A steady drift in across the shot. Negative pulls back out instead.",
        "params": [
            {
                "key": "amount",
                "label": "Distance",
                "type": "float",
                "default": 0.08,
                "min": -0.4,
                "max": 0.4,
            }
        ],
        "build": _push_in,
    },
    {
        "id": "flash",
        "label": "Flash",
        "family": "colour",
        "description": "A burst of white on the beat, fading out.",
        "params": [_amount(0.35, 0.0, 1.0, "Brightness"), _decay(11.0)],
        "build": _flash,
    },
    {
        "id": "sat_pump",
        "label": "Colour pump",
        "family": "colour",
        "description": "Colour surges on the beat and settles. Subtler than a flash and wears better over a long video.",
        "params": [_amount(0.5, -1.0, 2.0, "Amount"), _decay(8.0)],
        "build": _sat_pump,
    },
    {
        "id": "hue_kick",
        "label": "Hue kick",
        "family": "colour",
        "description": "Twists every colour round the wheel on the hit, then unwinds.",
        "params": [
            {
                "key": "degrees",
                "label": "How far round",
                "type": "float",
                "default": 30.0,
                "min": -180.0,
                "max": 180.0,
            },
            _decay(9.0),
        ],
        "build": _hue_kick,
    },
    {
        "id": "strobe",
        "label": "Strobe",
        "family": "colour",
        "description": "Hard on/off flicker at a fixed rate. Use sparingly and never for long.",
        "params": [
            _amount(0.25, 0.0, 1.0, "Depth"),
            {
                "key": "rate",
                "label": "Flashes per second",
                "type": "float",
                "default": 8.0,
                "min": 1.0,
                "max": 24.0,
            },
        ],
        "build": _strobe,
    },
    {
        "id": "invert_hit",
        "label": "Invert hit",
        "family": "glitch",
        "description": "One or two frames of inverted colour on the beat. Reads as a punch, not as a colour.",
        "params": [
            {
                "key": "width",
                "label": "How long (seconds)",
                "type": "float",
                "default": 0.05,
                "min": 0.02,
                "max": 0.4,
            }
        ],
        "build": _invert_hit,
    },
    {
        "id": "blur_hit",
        "label": "Blur hit",
        "family": "camera",
        "description": "A short smear on the beat, like the camera was struck.",
        "params": [
            {
                "key": "sigma",
                "label": "How much blur",
                "type": "float",
                "default": 8.0,
                "min": 0.5,
                "max": 40.0,
            },
            {
                "key": "width",
                "label": "How long (seconds)",
                "type": "float",
                "default": 0.07,
                "min": 0.02,
                "max": 0.5,
            },
        ],
        "build": _blur_hit,
    },
    {
        "id": "rgb_split",
        "label": "Colour tear",
        "family": "glitch",
        "description": "Pulls the red and blue apart on the hit. The classic edit look.",
        "params": [
            _amount(0.5, 0.0, 1.0, "How far apart"),
            {
                "key": "width",
                "label": "How long (seconds)",
                "type": "float",
                "default": 0.08,
                "min": 0.02,
                "max": 0.5,
            },
        ],
        "build": _rgb_split,
    },
    {
        "id": "chroma_ghost",
        "label": "Chroma ghost",
        "family": "glitch",
        "description": "A constant colour offset for the whole shot. Cheap analogue-tape feel.",
        "params": [_amount(0.4, 0.0, 1.0, "How far")],
        "build": _chroma_ghost,
    },
    {
        "id": "echo_trail",
        "label": "Echo trail",
        "family": "glitch",
        "description": "Blends the last few frames together so movement smears behind itself.",
        "params": [
            {
                "key": "frames",
                "label": "Frames blended",
                "type": "int",
                "default": 3,
                "min": 2,
                "max": 12,
            }
        ],
        "build": _echo_trail,
    },
    {
        "id": "lens_warp",
        "label": "Lens warp",
        "family": "glitch",
        "description": "Bows the picture out like a wide lens. Constant across the shot.",
        "params": [_amount(0.08, -0.3, 0.3, "Bulge")],
        "build": _lens_warp,
    },
    {
        "id": "grain",
        "label": "Grain",
        "family": "glitch",
        "description": "Film grain over the shot.",
        "params": [
            {
                "key": "amount",
                "label": "Grain",
                "type": "int",
                "default": 10,
                "min": 0,
                "max": 60,
            }
        ],
        "build": _grain,
    },
    {
        "id": "vignette_pulse",
        "label": "Vignette pulse",
        "family": "camera",
        "description": "The corners darken and breathe with the beat.",
        "params": [_amount(0.3, 0.0, 1.0, "Depth"), _decay(7.0)],
        "build": _vignette_pulse,
    },
    {
        "id": "bar_slam",
        "label": "Cinema bars",
        "family": "camera",
        "description": "Black bars slam in on the hit and hold. Good on a title moment.",
        "params": [
            {
                "key": "height",
                "label": "Bar height",
                "type": "float",
                "default": 0.1,
                "min": 0.02,
                "max": 0.25,
            },
            {
                "key": "hold",
                "label": "How long (seconds)",
                "type": "float",
                "default": 0.5,
                "min": 0.05,
                "max": 5.0,
            },
        ],
        "build": _bar_slam,
    },
    {
        "id": "mirror",
        "label": "Mirror",
        "family": "camera",
        "description": "Flips the shot left to right. Turns a repeated clip into a different shot.",
        "params": [{"key": "on", "label": "Flip", "type": "bool", "default": True}],
        "build": _mirror,
    },
]

FX = {e["id"]: {k: v for k, v in e.items() if k != "build"} for e in _FX}
_BUILDERS = {e["id"]: e["build"] for e in _FX}


def defaults_for(fx_id):
    meta = FX.get(fx_id) or {}
    return {p["key"]: p.get("default") for p in meta.get("params", [])}


def merge_params(fx_id, params):
    """Schema defaults with the user's values on top, each clamped to its own
    range. A saved edit never has to carry every key, so adding a parameter
    later cannot break an old project."""
    merged = defaults_for(fx_id)
    specs = {p["key"]: p for p in (FX.get(fx_id) or {}).get("params", [])}
    for k, v in (params or {}).items():
        if v is None or k not in specs:
            continue
        spec = specs[k]
        if spec["type"] in ("float", "int"):
            try:
                v = float(v)
            except (TypeError, ValueError):
                continue
            if "min" in spec:
                v = max(float(spec["min"]), v)
            if "max" in spec:
                v = min(float(spec["max"]), v)
            v = int(round(v)) if spec["type"] == "int" else v
        merged[k] = v
    return merged


def build(fx_id, events, params, ctx):
    """The ffmpeg filter string for one effect on one shot, or "" for nothing.

    A misspelt id returns "" rather than raising: an effect that cannot be
    built should cost that effect, never the render."""
    fn = _BUILDERS.get(fx_id)
    if fn is None:
        return ""
    try:
        return fn(list(events or []), merge_params(fx_id, params), ctx) or ""
    except Exception as e:  # pragma: no cover - defensive
        print(f"[pulseforge] beat effect {fx_id} failed to build: {e}")
        return ""


def build_chain(fx_list, ctx):
    """Every effect on one shot, joined into one filter chain.

    `fx_list` is [{id, events, params}]. Order matters and is preserved:
    geometry before colour before grain reads the way an editor would stack
    them, and that is the order the planner emits."""
    parts = [
        build(f.get("id", ""), f.get("events", []), f.get("params"), ctx)
        for f in fx_list or []
    ]
    return ",".join([p for p in parts if p])


def fx_as_list():
    order = {"camera": 0, "colour": 1, "glitch": 2}
    return sorted(
        ({"id": k, **v} for k, v in FX.items()),
        key=lambda e: (order.get(str(e.get("family") or ""), 9), e["id"]),
    )


__all__ = [
    "FX",
    "build",
    "build_chain",
    "fx_as_list",
    "defaults_for",
    "merge_params",
    "pulse",
    "windows",
]
