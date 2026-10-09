"""
Making a control move on its own.

Every parameter in this app is a fixed number, which is the right default and
the wrong ceiling: a cloud layer that thickens and thins over a minute reads as
weather, and one that sits at 0.45 forever reads as a filter. So a parameter
value is allowed to be an object instead of a number:

    {"base": 0.45, "mod": "lfo", "amount": 0.2, "period": 30, "shape": "sine"}

`mod` is either **"lfo"** -- a slow cycle taken from the shot's `LoopClock`, so
it is loop-exact like everything else and costs the seam nothing -- or the name
of an **audio feature** (`energy`, `sub`, `onset`, `centroid`), which only means
anything when the shot is in live mode, because a repeated loop bed has no
position in the song to read. The editor says so on the control rather than
letting you set something that silently does nothing.

This resolves in exactly one place per registry: `merge_params()`, which every
effect and every emitter already goes through. That is why it works for all
twenty of them, and for anything added later, without a line of per-effect code.
"""

AUDIO_SOURCES = ("energy", "sub", "onset", "centroid")
SHAPES = ("sine", "ramp", "pulse", "wander")

SOURCES = [
    {
        "id": "lfo",
        "label": "Slow cycle",
        "needs_live": False,
        "help": "A repeating swell. Snapped to the loop, so it costs nothing.",
    },
    {
        "id": "energy",
        "label": "Loudness",
        "needs_live": True,
        "help": "How loud the song is right now.",
    },
    {
        "id": "sub",
        "label": "Bass",
        "needs_live": True,
        "help": "Low end -- the kick and the bassline.",
    },
    {
        "id": "onset",
        "label": "Hits",
        "needs_live": True,
        "help": "Sharp attacks: drums, plucks, transients.",
    },
    {
        "id": "centroid",
        "label": "Brightness",
        "needs_live": True,
        "help": "How bright the sound is -- cymbals and highs push it up.",
    },
]


def is_modulated(value):
    return isinstance(value, dict) and "base" in value


def describe(value):
    """A short human line for the editor, e.g. 'Bass +0.20'."""
    if not is_modulated(value):
        return ""
    src = next((s for s in SOURCES if s["id"] == value.get("mod")), None)
    label = src["label"] if src else str(value.get("mod"))
    return f"{label} {float(value.get('amount', 0)):+.2f}"


def needs_live(value):
    """True if this modulation only does something in live mode."""
    if not is_modulated(value):
        return False
    return str(value.get("mod")) in AUDIO_SOURCES


def _shaped(tl, period, shape, offset=0.0):
    """A -1..1 signal that always returns to where it started at the loop."""
    if shape == "ramp":
        return tl.saw(period, offset) * 2.0 - 1.0
    if shape == "pulse":
        return 1.0 if tl.saw(period, offset) < 0.5 else -1.0
    if shape == "wander":
        # two prime-ish periods beating against each other: never quite repeats
        # inside the loop, but both wrap at it
        return 0.6 * tl.wave(period, offset) + 0.4 * tl.wave(
            period * 0.37, offset + 0.3
        )
    return tl.wave(period, offset)


def resolve(value, tl=None, spec=None):
    """Turn a possibly-modulated value into a number for this instant.

    With no clock (an API listing the saved project, say) the base value is
    returned unchanged, so a modulated parameter still reads sensibly anywhere
    that is not mid-render.
    """
    if not is_modulated(value):
        return value
    base = value.get("base")
    if not isinstance(base, (int, float)):
        return base
    if tl is None:
        return base

    amount = float(value.get("amount", 0.0) or 0.0)
    source = str(value.get("mod", "lfo"))
    if source == "lfo":
        signal = _shaped(
            tl,
            max(0.05, float(value.get("period", 20.0) or 20.0)),
            str(value.get("shape", "sine")),
            float(value.get("offset", 0.0) or 0.0),
        )
    elif source in AUDIO_SOURCES:
        # 0..1 from the analysis, recentred so `amount` swings both ways.
        # Without a live song this sits at the midpoint and contributes nothing,
        # which is the honest outcome for a repeated loop bed.
        signal = tl.audio(source, default=0.5) * 2.0 - 1.0
    else:
        return base

    out = float(base) + amount * signal
    if spec:
        lo, hi = spec.get("min"), spec.get("max")
        if isinstance(lo, (int, float)):
            out = max(float(lo), out)
        if isinstance(hi, (int, float)):
            out = min(float(hi), out)
    if spec and spec.get("type") == "int":
        out = int(round(out))
    return out


def resolve_all(merged, tl, specs):
    """Resolve every modulated entry of an already-merged parameter dict."""
    for key, value in merged.items():
        if is_modulated(value):
            merged[key] = resolve(value, tl, specs.get(key))
    return merged


def strip(params):
    """Base values only -- for anything that wants the settings, not the moment."""
    return {
        k: (v.get("base") if is_modulated(v) else v) for k, v in (params or {}).items()
    }
