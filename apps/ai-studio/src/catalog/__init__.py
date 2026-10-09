"""The model catalog: one declarative registry for every model AI Studio offers.

Each ``catalog/<kind>.py`` holds an ``ENTRIES`` list; this package merges them
into ``CATALOG`` (id -> entry). Adding a model is one entry in one file. The
schema is in ``docs/2026-10-08-rebuild-plan.md``; ``validate`` checks it.

``world.py`` belongs to the 3D-world work and may not exist yet; it is loaded
when present and skipped when missing.
"""

import importlib

KINDS = ("image", "video", "world")
TIERS = ("compact", "big")
# Roles a part may have. The sd roles map to sd.cpp flags in engine_flags.py;
# "weights" and "code" are for world runners.
ROLES = (
    "checkpoint",
    "diffusion",
    "high_noise_diffusion",
    "uncond_diffusion",
    "llm",
    "llm_vision",
    "t5xxl",
    "clip_l",
    "clip_g",
    "clip_vision",
    "vae",
    "audio_vae",
    "lora",
    "weights",
    "code",
)

DEFAULT_MODEL_ID = "meinamix-v10"

# Kept for the SD1.5 path: the LCM speed-up add-on is loaded by name from the
# LoRA folder (engine.py adds the tag to the prompt).
LCM_LORA_URL = (
    "https://huggingface.co/latent-consistency/lcm-lora-sdv1-5/resolve/main/"
    "pytorch_lora_weights.safetensors"
)
LCM_LORA_FILENAME = "lcm-lora-sd15.safetensors"
LCM_LORA_NAME = "lcm-lora-sd15"


def hf(repo, path):
    """Download URL of one file in a Hugging Face repo."""
    return f"https://huggingface.co/{repo}/resolve/main/{path}"


def part(role, repo, path, size_bytes, filename=None, gated=False):
    """One file a model needs. ``filename`` is the local name (defaults to the
    last part of ``path``); parts with the same filename are the same file and
    are stored once. ``gated`` repos need a Hugging Face sign-in to download."""
    out = {
        "role": role,
        "url": hf(repo, path),
        "filename": filename or path.rsplit("/", 1)[-1],
        "size_bytes": size_bytes,
    }
    if gated:
        out["gated"] = True
    return out


def validate(entry):
    """Raise ValueError naming what is wrong with one catalog entry."""
    eid = entry.get("id")
    for key in ("id", "kind", "label", "blurb", "tier", "engine", "parts"):
        if not entry.get(key) and entry.get(key) != []:
            raise ValueError(f"{eid}: missing {key}")
    if entry["kind"] not in KINDS:
        raise ValueError(f"{eid}: unknown kind {entry['kind']}")
    if entry["tier"] not in TIERS:
        raise ValueError(f"{eid}: unknown tier {entry['tier']}")
    names = set()
    for p in entry["parts"]:
        if p.get("role") not in ROLES:
            raise ValueError(f"{eid}: unknown part role {p.get('role')}")
        if not p.get("filename") or "/" in p["filename"] or p["filename"][0] == ".":
            raise ValueError(f"{eid}: bad part filename {p.get('filename')!r}")
        if not isinstance(p.get("size_bytes"), int) or p["size_bytes"] <= 0:
            raise ValueError(f"{eid}: part {p['filename']} needs size_bytes")
        if not str(p.get("url", "")).startswith("https://"):
            raise ValueError(f"{eid}: part {p['filename']} needs an https url")
        dest = p.get("dest")
        if dest is not None and (
            not isinstance(dest, str)
            or dest.startswith(("/", "~"))
            or ".." in dest.replace("\\", "/").split("/")
        ):
            raise ValueError(f"{eid}: part {p['filename']} has an unsafe dest")
        if p["filename"] in names:
            raise ValueError(f"{eid}: part {p['filename']} listed twice")
        names.add(p["filename"])
    return entry


def _load(kind):
    try:
        module = importlib.import_module(f"catalog.{kind}")
    except ModuleNotFoundError as e:
        if e.name == f"catalog.{kind}":
            return []  # this kind has no file yet (world.py may come later)
        raise
    return list(getattr(module, "ENTRIES", []))


def build():
    """Merge every kind's ENTRIES into one id -> entry dict, validated.

    A clash of ids, or of one filename used for two different downloads, is an
    error: parts are shared by filename, so both would land on one file.
    """
    catalog = {}
    urls = {}
    for kind in KINDS:
        for entry in _load(kind):
            entry = validate({"kind": kind, **entry})
            if entry["id"] in catalog:
                raise ValueError(f"duplicate model id {entry['id']}")
            for p in entry["parts"]:
                seen = urls.setdefault(p["filename"], (p["url"], p["size_bytes"]))
                if seen != (p["url"], p["size_bytes"]):
                    raise ValueError(
                        f"{entry['id']}: {p['filename']} means two different files"
                    )
            catalog[entry["id"]] = entry
    return catalog


CATALOG = build()
