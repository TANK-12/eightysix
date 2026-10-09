"""Avatars for Forge apps: Live2D models, motions made from recipes, and
generated puppets. Stdlib only, like the rest of shared/.

Emerson asked for this on 2026-09-24: a live anime avatar in the Claude app,
with "mor ethan 8 motions for each model and also generaons when needed", a
generator, saver and editor, and Nyarch's Arch-chan as the first model.

The layout under ``shared/avatars/``:

* ``live2d/<id>/``: one Live2D model per folder (its ``*.model3.json``).
  Arch-chan came from Nyarch Assistant; the rest are Live2D Inc's official
  samples (Free Material License, ``live2d/LICENSE-live2d-free-material.md``).
* ``motion_recipes.json``: the shared motions. Each recipe becomes a real
  ``.motion3.json`` per model on demand (``ensure_motions``), written into
  ``live2d/<id>/forge_motions/``. Only the curves the model has are
  written, with names translated (``PARAM_ANGLE_X``, Mao's vowel mouth).
* ``motions_custom/<name>.json``: recipes made later (improvised, from Jan, or
  saved in the editor). They join the list with no code change.
* ``puppets/<name>.json``: generated 2D puppets (``forge_puppet.js`` draws
  them).

Real Live2D ``.moc3`` models can only be authored in Live2D's own editor, so
generated characters are puppets, not moc3 files. That is said plainly in the
UI too.
"""

from __future__ import annotations

import json
import math
import os
import random
import re
import time
from pathlib import Path

ROOT = Path(
    os.environ.get("FORGE_AVATARS_DIR") or Path(__file__).resolve().parent / "avatars"
)

# Standard parameter ranges: values in recipes are clamped to these.
RANGES: dict[str, tuple[float, float]] = {
    "ParamAngleX": (-30, 30),
    "ParamAngleY": (-30, 30),
    "ParamAngleZ": (-30, 30),
    "ParamBodyAngleX": (-10, 10),
    "ParamBodyAngleY": (-10, 10),
    "ParamBodyAngleZ": (-10, 10),
    "ParamEyeBallX": (-1, 1),
    "ParamEyeBallY": (-1, 1),
    "ParamEyeLOpen": (0, 2),
    "ParamEyeROpen": (0, 2),
    "ParamEyeLSmile": (0, 1),
    "ParamEyeRSmile": (0, 1),
    "ParamMouthOpenY": (0, 1),
    "ParamMouthForm": (-1, 1),
    "ParamBrowLY": (-1, 1),
    "ParamBrowRY": (-1, 1),
    "ParamCheek": (0, 1),
    "ParamBreath": (0, 1),
}

# Names some models use instead of the standard ones, tried in order.
ALIASES: dict[str, list[str]] = {
    "ParamMouthOpenY": ["ParamA"],
    "ParamCheek": ["PARAM_TERE"],
    "ParamEyeLSmile": ["ParamEyeRSmile"],
}

# A recipe's "EyeLSmile" also drives the right eye when the model has one.
MIRRORED = {"ParamEyeLSmile": "ParamEyeRSmile"}

ENVELOPES = ("none", "bell", "in", "out")
FPS = 30
MAX_DURATION = 20.0
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_\-]{0,47}$")


class AvatarError(ValueError):
    """A bad recipe, puppet or name. The message is safe to show the user."""


# --- names --------------------------------------------------------------------


def safe_name(name: str) -> str:
    """A file-safe id: lower case, digits, _ and -."""
    slug = re.sub(r"[^a-z0-9_\-]+", "_", str(name).strip().lower()).strip("_-")
    if not NAME_RE.match(slug or ""):
        raise AvatarError("Give it a name made of letters, digits, - or _")
    return slug


def snake(param: str) -> str:
    """ParamAngleX -> PARAM_ANGLE_X (Cubism 2 style ids)."""
    body = param[5:] if param.startswith("Param") else param
    return "PARAM_" + re.sub(r"(?<!^)(?=[A-Z])", "_", body).upper()


def resolve(param: str, ids: set[str]) -> str | None:
    """The id this model uses for a standard parameter, or None."""
    for candidate in [param, snake(param), *ALIASES.get(param, [])]:
        if candidate in ids:
            return candidate
    return None


# --- recipes ------------------------------------------------------------------


def envelope(kind: str, x: float) -> float:
    """0..1 weight at x (0..1 through the motion)."""
    x = min(1.0, max(0.0, x))
    if kind == "bell":
        return math.sin(math.pi * x)
    if kind == "in":
        return x
    if kind == "out":
        return 1.0 - x
    return 1.0


def sample(curve: dict, t: float, duration: float) -> float:
    """A curve's value at time t: keyframes (eased) plus a wave."""
    value = 0.0
    keys = curve.get("keys") or []
    if keys:
        if t <= keys[0][0]:
            value = keys[0][1]
        elif t >= keys[-1][0]:
            value = keys[-1][1]
        else:
            for (t0, v0), (t1, v1) in zip(keys, keys[1:]):
                if t0 <= t <= t1:
                    x = 0.0 if t1 == t0 else (t - t0) / (t1 - t0)
                    x = x * x * (3 - 2 * x)  # smoothstep, so it eases
                    value = v0 + (v1 - v0) * x
                    break
    wave = curve.get("wave")
    if wave:
        w = wave.get("offset", 0.0) + wave.get("amp", 0.0) * math.sin(
            2 * math.pi * wave.get("freq", 1.0) * t + wave.get("phase", 0.0)
        )
        value += w * envelope(curve.get("env", "none"), t / duration if duration else 0)
    return value


def validate_recipe(recipe: object) -> dict:
    """A clean copy of a recipe, or AvatarError. Used for anything not
    written by hand: improvised, from Jan, or posted by a page."""
    if not isinstance(recipe, dict):
        raise AvatarError("A motion must be an object")
    try:
        duration = float(recipe.get("duration", 0))
    except (TypeError, ValueError):
        raise AvatarError("duration must be a number")
    if not 0.2 <= duration <= MAX_DURATION:
        raise AvatarError(f"duration must be 0.2 to {MAX_DURATION:g} seconds")
    curves_in = recipe.get("curves")
    if not isinstance(curves_in, dict) or not curves_in:
        raise AvatarError("A motion needs at least one curve")
    curves: dict[str, dict] = {}
    for param, curve in curves_in.items():
        if param not in RANGES:
            raise AvatarError(f"Unknown parameter {param}")
        if not isinstance(curve, dict):
            raise AvatarError(f"{param}: a curve must be an object")
        clean: dict = {}
        keys = curve.get("keys")
        if keys is not None:
            try:
                pts = sorted((float(t), float(v)) for t, v in keys)
            except (TypeError, ValueError):
                raise AvatarError(f"{param}: keys must be [seconds, value] pairs")
            if not pts or len(pts) > 200:
                raise AvatarError(f"{param}: 1 to 200 keys")
            clean["keys"] = [[round(t, 3), round(v, 3)] for t, v in pts]
        wave = curve.get("wave")
        if wave is not None:
            if not isinstance(wave, dict):
                raise AvatarError(f"{param}: wave must be an object")
            try:
                clean["wave"] = {
                    k: float(wave.get(k, d))
                    for k, d in (("amp", 0), ("freq", 1), ("phase", 0), ("offset", 0))
                }
            except (TypeError, ValueError):
                raise AvatarError(f"{param}: wave values must be numbers")
            if not 0 < clean["wave"]["freq"] <= 20:
                raise AvatarError(f"{param}: wave freq must be above 0 and at most 20")
            env = curve.get("env", "none")
            if env not in ENVELOPES:
                raise AvatarError(f"{param}: env must be one of {', '.join(ENVELOPES)}")
            clean["env"] = env
        if not clean:
            raise AvatarError(f"{param}: give keys, a wave, or both")
        curves[param] = clean
    mood = recipe.get("mood") or []
    return {
        "label": str(recipe.get("label") or "")[:60],
        "mood": [str(m)[:20] for m in mood][:6] if isinstance(mood, list) else [],
        "duration": round(duration, 3),
        "loop": bool(recipe.get("loop", False)),
        "curves": curves,
    }


def custom_dir(root: Path = ROOT) -> Path:
    return root / "motions_custom"


def load_recipes(root: Path = ROOT) -> dict[str, dict]:
    """Built-in recipes, then custom ones (a custom one may not replace a
    built-in: it gets saved under its own name)."""
    recipes: dict[str, dict] = {}
    base = root / "motion_recipes.json"
    if base.is_file():
        for name, recipe in json.loads(base.read_text()).items():
            if not name.startswith("_"):
                recipes[name] = {**recipe, "source": "built-in"}
    folder = custom_dir(root)
    if folder.is_dir():
        for path in sorted(folder.glob("*.json")):
            if path.stem in recipes:
                continue
            try:
                recipe = validate_recipe(json.loads(path.read_text()))
            except (AvatarError, ValueError):
                continue
            recipes[path.stem] = {**recipe, "source": "custom"}
    return recipes


def save_recipe(name: str, recipe: dict, root: Path = ROOT) -> str:
    """Save a custom recipe; returns its id. Existing ids get a number."""
    clean = validate_recipe(recipe)
    base = safe_name(name)
    taken = set(load_recipes(root))
    slug, n = base, 2
    while slug in taken:
        slug, n = f"{base}_{n}", n + 1
    folder = custom_dir(root)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{slug}.json").write_text(json.dumps(clean, indent=1))
    return slug


def delete_recipe(name: str, root: Path = ROOT) -> bool:
    path = custom_dir(root) / f"{safe_name(name)}.json"
    if not path.is_file():
        return False
    path.unlink()
    return True


def improvise(seed: int | None = None, mood: str = "") -> dict:
    """A new motion made up from random waves and poses, for "generate one
    when needed". Same seed, same motion."""
    rng = random.Random(seed)
    duration = round(rng.uniform(1.6, 4.0), 2)
    head = ["ParamAngleX", "ParamAngleY", "ParamAngleZ"]
    body = ["ParamBodyAngleX", "ParamBodyAngleZ"]
    curves: dict[str, dict] = {}
    for param in rng.sample(head, rng.randint(2, 3)) + rng.sample(body, 1):
        lo, hi = RANGES[param]
        span = (hi - lo) / 2
        if rng.random() < 0.5:
            curves[param] = {
                "wave": {
                    "amp": round(rng.uniform(0.2, 0.6) * span, 2),
                    "freq": round(rng.choice([0.5, 1, 1.5, 2, 3]) / duration * 2, 2),
                    "phase": round(rng.uniform(0, 6.28), 2),
                },
                "env": "bell",
            }
        else:
            pose = round(rng.uniform(-0.7, 0.7) * span, 1)
            curves[param] = {
                "keys": [
                    [0, 0],
                    [duration * 0.25, pose],
                    [duration * 0.75, pose * 0.8],
                    [duration, 0],
                ]
            }
    face = {
        "happy": ("ParamMouthForm", 1.0),
        "flirty": ("ParamCheek", 1.0),
        "sad": ("ParamBrowLY", -0.8),
        "think": ("ParamEyeBallY", 0.8),
        "hype": ("ParamMouthOpenY", 0.8),
    }.get(mood) or rng.choice(
        [("ParamMouthForm", 1.0), ("ParamBrowLY", 0.7), ("ParamEyeBallX", 0.7)]
    )
    p, v = face
    curves[p] = {
        "keys": [[0, 0], [duration * 0.2, v], [duration * 0.8, v], [duration, 0]]
    }
    return validate_recipe(
        {
            "label": "Improvised",
            "mood": [mood] if mood else [],
            "duration": duration,
            "curves": curves,
        }
    )


# --- Live2D models --------------------------------------------------------------


def model_file(folder: Path) -> Path | None:
    """The model settings file: Cubism 4 (.model3.json) or Cubism 2 (.model.json)."""
    found = sorted(folder.glob("*.model3.json")) or sorted(folder.glob("*.model.json"))
    return found[0] if found else None


def cubism(path: Path) -> int:
    """2 for a Cubism 2 settings file, 4 for Cubism 3/4/5."""
    return 4 if path.name.endswith(".model3.json") else 2


PARAM2_RE = re.compile(rb"PARAM_[A-Z0-9_]+")


def model_params(folder: Path) -> set[str]:
    """Parameter ids, from the display-info file (Cubism 4) or, failing that,
    the PARAM_* names stored in the Cubism 2 .moc."""
    cdi = sorted(folder.glob("*.cdi3.json"))
    if cdi:
        try:
            data = json.loads(cdi[0].read_text())
        except ValueError:
            return set()
        return {p.get("Id", "") for p in data.get("Parameters", [])} - {""}
    ids: set[str] = set()
    for moc in folder.glob("**/*.moc"):
        ids |= {m.decode() for m in PARAM2_RE.findall(moc.read_bytes())}
    return ids


def tracks(
    recipe: dict, ids: set[str], intensity: float = 1.0, speed: float = 1.0
) -> tuple[float, int, dict[str, list[float]]]:
    """(duration, steps, {model param id: steps+1 values at FPS}) for a recipe."""
    duration = recipe["duration"] / max(0.1, speed)
    steps = max(2, int(math.ceil(duration * FPS)))
    out: dict[str, list[float]] = {}
    for param, curve in recipe["curves"].items():
        targets = [resolve(param, ids)]
        if param in MIRRORED:
            targets.append(resolve(MIRRORED[param], ids))
        lo, hi = RANGES[param]
        rest = 1.0 if param in ("ParamEyeLOpen", "ParamEyeROpen") else 0.0
        for target in dict.fromkeys(t for t in targets if t):
            values = []
            for i in range(steps + 1):
                t = duration * i / steps
                raw = sample(curve, t * speed, recipe["duration"])
                value = rest + (raw - rest) * intensity
                values.append(round(min(hi, max(lo, value)), 3))
            out[target] = values
    return duration, steps, out


def motion3(
    recipe: dict, ids: set[str], intensity: float = 1.0, speed: float = 1.0
) -> dict | None:
    """A recipe as a Live2D motion3 document for a model with these ids.
    None when the model has none of the recipe's parameters."""
    duration, steps, found = tracks(recipe, ids, intensity, speed)
    curves = []
    for target, values in found.items():
        segments: list[float] = [0.0, values[0]]
        for i, value in enumerate(values[1:], 1):
            segments += [0, round(duration * i / steps, 4), value]
        curves.append({"Target": "Parameter", "Id": target, "Segments": segments})
    if not curves:
        return None
    return {
        "Version": 3,
        "Meta": {
            "Duration": round(duration, 4),
            "Fps": FPS,
            "Loop": recipe.get("loop", False),
            "AreBeziersRestricted": True,
            "CurveCount": len(curves),
            "TotalSegmentCount": steps * len(curves),
            "TotalPointCount": (steps + 1) * len(curves),
            "UserDataCount": 0,
            "TotalUserDataSize": 0,
        },
        "Curves": curves,
    }


def mtn(
    recipe: dict, ids: set[str], intensity: float = 1.0, speed: float = 1.0
) -> str | None:
    """A recipe as a Cubism 2 .mtn motion (one line of values per parameter,
    one value per frame). None when the model has none of its parameters."""
    _, _, found = tracks(recipe, ids, intensity, speed)
    if not found:
        return None
    lines = ["# Live2D Animator Motion Data (Forge recipe)", f"$fps={FPS}", ""]
    lines += ["$fadein=300", "$fadeout=300", ""]
    for target, values in found.items():
        lines.append(f"{target}=" + ",".join(f"{v:g}" for v in values))
    return "\n".join(lines) + "\n"


def ensure_motions(
    model_id: str, root: Path = ROOT, recipes: dict | None = None
) -> dict[str, str]:
    """Write the recipe motions this model lacks (or that changed); return
    {recipe id: path relative to the model folder}."""
    folder = root / "live2d" / safe_name(model_id)
    settings = model_file(folder)
    if not settings:
        raise AvatarError(f"No Live2D model called {model_id}")
    recipes = load_recipes(root) if recipes is None else recipes
    ids = model_params(folder)
    ext = ".motion3.json" if cubism(settings) == 4 else ".mtn"
    out_dir = folder / "forge_motions"
    out_dir.mkdir(exist_ok=True)
    written: dict[str, str] = {}
    for name, recipe in recipes.items():
        if ext == ".mtn":
            text = mtn(recipe, ids)
        else:
            doc = motion3(recipe, ids)
            text = None if doc is None else json.dumps(doc, separators=(",", ":"))
        if text is None:
            continue
        path = out_dir / f"{name}{ext}"
        if not path.is_file() or path.read_text() != text:
            path.write_text(text)
        written[name] = f"forge_motions/{name}{ext}"
    for stale in out_dir.glob(f"*{ext}"):
        if stale.name[: -len(ext)] not in written:
            stale.unlink()
    return written


NICE_NAMES = {"arch": "Arch-chan", "epsilon2_1": "Epsilon", "unitychan": "Unity-chan"}

# The newest .moc3 format the bundled viewer can open. Nyarch's viewer
# (pixi-live2d-display with its Cubism core) opens formats 1 to 5. Ren is
# format 6 (Cubism 5.3); the official core 6.00 opens it, but that core broke
# every model under this viewer when tried on 2026-09-24, so it stays out.
MAX_MOC_VERSION = 5


def moc_version(folder: Path) -> int:
    mocs = sorted(folder.glob("*.moc3"))
    if not mocs:
        return 0
    with mocs[0].open("rb") as f:
        head = f.read(5)
    return head[4] if len(head) == 5 and head[:4] == b"MOC3" else 0


def list_models(root: Path = ROOT) -> list[dict]:
    """Every Live2D model with its own motions and expressions."""
    models = []
    base = root / "live2d"
    if not base.is_dir():
        return models
    for folder in sorted(p for p in base.iterdir() if p.is_dir()):
        path = model_file(folder)
        if not path:
            continue
        try:
            settings = json.loads(path.read_text())
        except ValueError:
            continue
        level = cubism(path)
        if level == 4:
            refs = settings.get("FileReferences", {})
            groups = refs.get("Motions") or {}
            name_key, file_key = "Name", "File"
            expressions = refs.get("Expressions") or []
            hits = [h.get("Name") for h in settings.get("HitAreas") or []]
            supported = 0 < moc_version(folder) <= MAX_MOC_VERSION
        else:
            groups = settings.get("motions") or {}
            name_key, file_key = "name", "file"
            expressions = settings.get("expressions") or []
            hits = [h.get("name") for h in settings.get("hit_areas") or []]
            supported = (
                bool(settings.get("model")) and (folder / settings["model"]).is_file()
            )
        motions = {
            group: [m.get(name_key) or Path(m.get(file_key, "")).stem for m in items]
            for group, items in groups.items()
        }
        models.append(
            {
                "id": folder.name,
                "name": NICE_NAMES.get(
                    folder.name, folder.name.replace("_", " ").title()
                ),
                "url": f"avatars/live2d/{folder.name}/{path.name}",
                "cubism": level,
                "motions": motions,
                "own_motion_count": sum(len(v) for v in motions.values()),
                "expressions": [
                    e.get(name_key) or Path(e.get(file_key, "")).name.split(".")[0]
                    for e in expressions
                ],
                "hit_areas": [h for h in hits if h],
                "params": len(model_params(folder)),
                "supported": supported,
            }
        )
    return models


# --- puppets --------------------------------------------------------------------

PUPPET_FIELDS = {
    "hair_style": ("short", "long", "twintails", "spiky", "bob", "ponytail", "messy"),
    "bangs": ("straight", "side", "split", "messy", "none"),
    "eye_shape": ("round", "sharp", "sleepy", "sparkly"),
    "mouth_style": ("small", "cat", "grin", "fang"),
    "outfit": (
        "hoodie",
        "apron_hoodie",
        "uniform",
        "jacket",
        "dress",
        "tank",
        "kimono",
    ),
    "accessory": (
        "none",
        "headphones",
        "cat_ears",
        "glasses",
        "ribbon",
        "horns",
        "halo",
        "anvil",
    ),
    "body": ("girl", "boy", "androgynous"),
}
PUPPET_COLOURS = (
    "skin",
    "hair",
    "hair_streak",
    "eyes",
    "outfit",
    "outfit_trim",
    "accent",
)
PUPPET_NUMBERS = {
    "eye_size": (0.6, 1.6),
    "face_width": (0.8, 1.2),
    "hair_volume": (0.7, 1.5),
    "blush": (0, 1),
    "soot": (0, 1),
    "head_tilt": (-10, 10),
}
COLOUR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


def puppets_dir(root: Path = ROOT) -> Path:
    return root / "puppets"


def validate_puppet(data: object) -> dict:
    if not isinstance(data, dict):
        raise AvatarError("A puppet must be an object")
    clean: dict = {"name": str(data.get("name") or "Unnamed")[:40]}
    for field, allowed in PUPPET_FIELDS.items():
        value = data.get(field, allowed[0])
        if value not in allowed:
            raise AvatarError(f"{field} must be one of {', '.join(allowed)}")
        clean[field] = value
    colours = data.get("colours") or {}
    clean["colours"] = {}
    for key in PUPPET_COLOURS:
        value = str(colours.get(key) or "#888888")
        if not COLOUR_RE.match(value):
            raise AvatarError(f"colour {key} must look like #aabbcc")
        clean["colours"][key] = value.lower()
    for key, (lo, hi) in PUPPET_NUMBERS.items():
        try:
            value = float(
                data.get(key, (lo + hi) / 2 if lo < 0 else max(lo, min(hi, 1)))
            )
        except (TypeError, ValueError):
            raise AvatarError(f"{key} must be a number")
        clean[key] = round(min(hi, max(lo, value)), 3)
    clean["notes"] = str(data.get("notes") or "")[:500]
    return clean


def save_puppet(data: dict, root: Path = ROOT) -> str:
    clean = validate_puppet(data)
    slug = safe_name(data.get("id") or clean["name"])
    folder = puppets_dir(root)
    folder.mkdir(parents=True, exist_ok=True)
    clean["saved"] = time.time()
    (folder / f"{slug}.json").write_text(json.dumps(clean, indent=1))
    return slug


def load_puppet(name: str, root: Path = ROOT) -> dict:
    path = puppets_dir(root) / f"{safe_name(name)}.json"
    if not path.is_file():
        raise AvatarError(f"No puppet called {name}")
    return {"id": path.stem, **json.loads(path.read_text())}


def list_puppets(root: Path = ROOT) -> list[dict]:
    folder = puppets_dir(root)
    if not folder.is_dir():
        return []
    out = []
    for path in sorted(folder.glob("*.json")):
        try:
            out.append({"id": path.stem, **json.loads(path.read_text())})
        except ValueError:
            continue
    return out


def delete_puppet(name: str, root: Path = ROOT) -> bool:
    path = puppets_dir(root) / f"{safe_name(name)}.json"
    if not path.is_file():
        return False
    path.unlink()
    return True


def random_puppet(seed: int | None = None, body: str = "", style: str = "") -> dict:
    """A generated character. style: cute, cool, sexy or empty for any."""
    rng = random.Random(seed)
    palettes = {
        "cute": (
            ["#ffb3c7", "#f7d774", "#c9a7ff", "#8fd3ff", "#ffe0b3"],
            ["#ff8fb1", "#9be7c4", "#b8a1ff"],
        ),
        "cool": (
            ["#2b2d42", "#dfe3ea", "#4a6fa5", "#1f1f24", "#8d99ae"],
            ["#3a86ff", "#00b4d8", "#e0e1dd"],
        ),
        "sexy": (
            ["#1b1b1f", "#7a1f3d", "#f1e3c8", "#5b2a86", "#c0392b"],
            ["#e63946", "#9d4edd", "#ffb703"],
        ),
    }
    style = style if style in palettes else rng.choice(list(palettes))
    hairs, accents = palettes[style]
    body = body if body in PUPPET_FIELDS["body"] else rng.choice(PUPPET_FIELDS["body"])
    skin = rng.choice(["#ffe4d2", "#f8d5bd", "#eab896", "#c98e6b", "#8d5a3b"])
    hair_styles = {
        "girl": ["long", "twintails", "bob", "ponytail"],
        "boy": ["short", "spiky", "messy"],
        "androgynous": ["short", "bob", "messy", "ponytail"],
    }[body]
    return validate_puppet(
        {
            "name": "Generated",
            "body": body,
            "hair_style": rng.choice(hair_styles),
            "bangs": rng.choice(PUPPET_FIELDS["bangs"][:4]),
            "eye_shape": rng.choice(
                ["sparkly", "round"]
                if style == "cute"
                else ["sharp", "sleepy", "round"]
            ),
            "mouth_style": rng.choice(PUPPET_FIELDS["mouth_style"]),
            "outfit": rng.choice(PUPPET_FIELDS["outfit"]),
            "accessory": rng.choice(PUPPET_FIELDS["accessory"]),
            "colours": {
                "skin": skin,
                "hair": rng.choice(hairs),
                "hair_streak": rng.choice(accents),
                "eyes": rng.choice(accents + ["#6a4c93", "#2a9d8f", "#e76f51"]),
                "outfit": rng.choice(
                    ["#22223b", "#2d3142", "#3d405b", "#f2e9e4", "#9a031e"]
                ),
                "outfit_trim": rng.choice(accents),
                "accent": rng.choice(accents),
            },
            "eye_size": (
                rng.uniform(1.1, 1.5) if style == "cute" else rng.uniform(0.85, 1.2)
            ),
            "face_width": rng.uniform(0.9, 1.05),
            "hair_volume": rng.uniform(0.9, 1.3),
            "blush": rng.uniform(0.3, 0.8) if style != "cool" else rng.uniform(0, 0.3),
            "soot": 0,
            "head_tilt": 0,
        }
    )


JAN_MOTION_SYSTEM = (
    "You design motions for an anime avatar. Reply with ONE JSON object only, no prose. "
    'Shape: {"label": str, "duration": seconds 0.5-6, "loop": false, "curves": {PARAM: CURVE}}. '
    'CURVE is {"keys": [[seconds, value], ...]} or {"wave": {"amp": n, "freq": hz, "phase": 0}, "env": "bell"}. '
    "PARAM and value ranges: "
    + ", ".join(f"{k} {lo}..{hi}" for k, (lo, hi) in RANGES.items())
    + ". "
    "Eye open rests at 1, everything else rests at 0. Start and end at rest. Use 2 to 6 curves."
)


def recipe_from_text(text: str) -> dict:
    """The first JSON object in a model's reply, validated."""
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise AvatarError("The model did not reply with a motion")
    try:
        data = json.loads(text[start : end + 1])
    except ValueError:
        raise AvatarError("The model's motion was not valid JSON")
    return validate_recipe(data)
