"""JSON that only holds finite numbers.

Python's json reads NaN, Infinity and numbers too big for a float (1e999),
but a project or settings file holding one can no longer be sent back to the
page, so it would never open again. Everything that takes JSON from outside
(request bodies, imported project files) reads it through `loads`."""

import json
import math


def _refuse_constant(word):
    raise ValueError(word)


def _finite_float(text):
    value = float(text)
    if not math.isfinite(value):
        raise ValueError("-Infinity" if text.startswith("-") else "Infinity")
    return value


def loads(text):
    """json.loads that raises ValueError("NaN" / "Infinity" / "-Infinity")."""
    return json.loads(text, parse_constant=_refuse_constant, parse_float=_finite_float)


NOT_FINITE = ("NaN", "Infinity", "-Infinity")
