"""Kokoro voice catalog: lists what the model file actually contains, labelled
by parsing its naming convention (e.g. "af_heart" = American Female "Heart").
No hardcoded voice list -- if Kokoro ships more voices later, they show up
automatically next time the model loads.
"""

from __future__ import annotations

_LANG = {
    "a": "American English",
    "b": "British English",
    "j": "Japanese",
    "z": "Mandarin",
    "e": "Spanish",
    "f": "French",
    "h": "Hindi",
    "i": "Italian",
    "p": "Brazilian Portuguese",
}
_GENDER = {"f": "female", "m": "male"}


def describe(name: str) -> dict:
    """'af_heart' -> {id, label, language, gender}. Unknown patterns still
    get a sane fallback label rather than being dropped."""
    lang_code, _, rest = name.partition("_")
    if len(lang_code) == 2 and lang_code[0] in _LANG and lang_code[1] in _GENDER:
        language = _LANG[lang_code[0]]
        gender = _GENDER[lang_code[1]]
        display = rest.replace("_", " ").title() or name
        label = f"{display} — {language}, {gender}"
    else:
        language, gender, label = "unknown", "unknown", name
    return {"id": name, "label": label, "language": language, "gender": gender}


def catalog(voice_names: list[str]) -> list[dict]:
    return sorted(
        (describe(n) for n in voice_names),
        key=lambda v: (v["language"], v["gender"], v["id"]),
    )


# Voice-style blending partners, keyed by the Kokoro prefix (language +
# gender) then by tone. The chosen voice always stays dominant (at least 75%,
# emotion.MAX_BLEND_WEIGHT); a small weight of the partner's style vector
# brightens, darkens or softens the delivery by expression. Voice picks
# never change -- only the style vector fed to the model. A prefix with no
# entry, or a partner missing from the model file, means no blend.
BLEND_PARTNERS: dict[str, dict[str, list[str]]] = {
    "af": {
        "bright": ["af_bella", "af_sky"],
        "dark": ["af_kore", "af_sarah"],
        "soft": ["af_nicole", "af_river"],
    },
    "am": {
        "bright": ["am_puck", "am_adam"],
        "dark": ["am_onyx", "am_fenrir"],
        "soft": ["am_echo", "am_liam"],
    },
    "bf": {
        "bright": ["bf_lily", "bf_isabella"],
        "dark": ["bf_emma", "bf_isabella"],
        "soft": ["bf_alice", "bf_lily"],
    },
    "bm": {
        "bright": ["bm_lewis", "bm_fable"],
        "dark": ["bm_george", "bm_daniel"],
        "soft": ["bm_daniel", "bm_fable"],
    },
}


def blend_partner(
    voice: str, tone: str, available: list[str] | None = None
) -> str | None:
    """'am_michael', 'dark' -> 'am_onyx': the first listed partner for the
    voice's prefix and tone that is not the chosen voice itself and (when
    `available` is given) exists in the model file; None otherwise."""
    prefix, _, _ = voice.partition("_")
    for partner in BLEND_PARTNERS.get(prefix, {}).get(tone, []):
        if partner == voice:
            continue
        if available is not None and partner not in available:
            continue
        return partner
    return None
