"""
Model catalog: what models exist, how big they are, how much context they can
take, and a per-size "profile" so a 0.6B model isn't handed the same 4000-word
prompt as a 14B one.

Sources merged (in priority order):
  1. Jan's live /v1/models API          (authoritative ids)
  2. a scan of the llama.cpp models dir  (+ reads model.yml for ctx_size)
  3. a small built-in fallback list
  4. anything the user typed in by hand  (minus anything they hid)
"""

import os
import re
import json

from .config import KNOWN_MODELS_PATH, FALLBACK_MODELS

# --------------------------------------------------------------------------
# Size profiles
# --------------------------------------------------------------------------
PROFILES = {
    "tiny": {  # <= ~1.5B  (Qwen3-0.6B, 0.8B)
        "label": "tiny",
        "rag_tokens": 400,  # retrieved passages per scene
        "plan_scenes": 3,
        "scene_prompt_words": 900,
        "structure_retries": 4,
        "loose_json": True,  # prefer 'KEY: value' formats it can follow
        "codex_every_n": 2,  # skip some codex passes to save calls
        "outline_batch": 3,  # outline lines per request (small = followable)
        "max_context_words": 2200,
    },
    "small": {  # ~2B-4B
        "label": "small",
        "rag_tokens": 600,  # retrieved passages per scene
        "plan_scenes": 4,
        "scene_prompt_words": 1400,
        "structure_retries": 3,
        "loose_json": True,
        "codex_every_n": 1,
        "outline_batch": 4,
        "max_context_words": 4500,
    },
    "medium": {  # ~7B-13B
        "label": "medium",
        "rag_tokens": 900,  # retrieved passages per scene
        "plan_scenes": 4,
        "scene_prompt_words": 2200,
        "structure_retries": 2,
        "loose_json": False,
        "codex_every_n": 1,
        "outline_batch": 6,
        "max_context_words": 8000,
    },
    "large": {  # 14B+
        "label": "large",
        "rag_tokens": 1400,  # retrieved passages per scene
        "plan_scenes": 5,
        "scene_prompt_words": 3200,
        "structure_retries": 2,
        "loose_json": False,
        "codex_every_n": 1,
        "outline_batch": 10,
        "max_context_words": 12000,
    },
}

REASONING_HINT = (
    "vibethinker",
    "-think",
    "thinking",
    "reason",
    "r1-",
    "deepseek-r1",
    "qwq",
)


def _params_billions(model_id):
    """Best-effort parameter count from the id. Handles 0_6B, E2B, 14B-A3B,
    3.5B, 27B etc. For MoE 'total-Aactive' we use the *active* count when
    present because that's what governs speed and effective capability."""
    s = model_id.lower().replace("_", ".")
    active = re.search(r"a(\d+(?:\.\d+)?)\s*b", s)  # e.g. 14B-A3B  -> 3
    if active:
        return float(active.group(1))
    m = re.search(r"\be?(\d+(?:\.\d+)?)\s*b\b", s)  # e2b, 0.6b, 4b, 27b
    if m:
        return float(m.group(1))
    return None


def profile_for(model_id, ctx_size=None):
    b = _params_billions(model_id)
    if b is None:
        key = "small"
    elif b <= 1.5:
        key = "tiny"
    elif b <= 4.5:
        key = "small"
    elif b <= 13:
        key = "medium"
    else:
        key = "large"
    prof = dict(PROFILES[key])
    prof["params_b"] = b
    prof["is_reasoning"] = any(h in model_id.lower() for h in REASONING_HINT)
    prof["ctx_size"] = ctx_size or 8192
    return prof


# --------------------------------------------------------------------------
# Folder scan + model.yml
# --------------------------------------------------------------------------
def scan_models_folder(path):
    """Return {model_id: {"ctx_size": int|None, "size_bytes": int|None,
    "weights": bool}}. `weights` is whether the model can really load: a
    .gguf in its folder, or a model.yml model_path (relative to Jan's data
    folder, two levels above `path`) that points at a file that exists."""
    out = {}
    if not path or not os.path.isdir(path):
        return out
    try:
        entries = sorted(
            d
            for d in os.listdir(path)
            if os.path.isdir(os.path.join(path, d)) and not d.startswith(".")
        )
    except Exception:
        return out
    for name in entries:
        meta = {
            "ctx_size": None,
            "size_bytes": None,
            "weights": False,
            "embedding": False,
        }
        folder = os.path.join(path, name)
        try:
            meta["weights"] = any(f.endswith(".gguf") for f in os.listdir(folder))
        except OSError:
            pass
        yml = os.path.join(folder, "model.yml")
        if os.path.exists(yml):
            try:
                with open(yml, "r", encoding="utf-8") as f:
                    for line in f:
                        m = re.match(r"\s*ctx_size\s*:\s*(\d+)", line)
                        if m:
                            meta["ctx_size"] = int(m.group(1))
                        m = re.match(r"\s*size_bytes\s*:\s*(\d+)", line)
                        if m:
                            meta["size_bytes"] = int(m.group(1))
                        if re.match(r"\s*embedding\s*:\s*true\b", line):
                            meta["embedding"] = True
                        m = re.match(r"\s*model_path\s*:\s*(\S.*?)\s*$", line)
                        if m and not meta["weights"]:
                            target = m.group(1).strip("'\"")
                            root = os.path.dirname(os.path.dirname(path))
                            if not os.path.isabs(target):
                                target = os.path.join(root, target)
                            meta["weights"] = os.path.isfile(target)
            except Exception:
                pass
        out[name] = meta
    return out


# --------------------------------------------------------------------------
# User add/hide registry (never touches disk model files)
# --------------------------------------------------------------------------
class ModelRegistry:
    def __init__(self, path=KNOWN_MODELS_PATH):
        self.path = path
        self.data = {"user_added": [], "hidden": []}
        self.load()

    def load(self):
        if os.path.exists(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    self.data.update(json.load(f))
            except Exception:
                pass

    def save(self):
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def add(self, name):
        name = (name or "").strip()
        if not name:
            return
        if name in self.data["hidden"]:
            self.data["hidden"].remove(name)
        if name not in self.data["user_added"]:
            self.data["user_added"].append(name)
        self.save()

    def hide(self, name):
        if not name:
            return
        if name in self.data["user_added"]:
            self.data["user_added"].remove(name)
        if name not in self.data["hidden"]:
            self.data["hidden"].append(name)
        self.save()

    def resolve(self, discovered):
        seen, result = set(), []
        for m in list(discovered) + list(self.data["user_added"]):
            if not m or m in self.data["hidden"] or m in seen:
                continue
            seen.add(m)
            result.append(m)
        return result


class Catalog:
    """One object the GUI holds; call refresh() to rescan."""

    def __init__(self):
        self.registry = ModelRegistry()
        self.meta = {}  # model_id -> {ctx_size, size_bytes}
        self.models = []  # filled by refresh(); never made-up names
        self.api_count = 0
        self.scan_count = 0

    def refresh(self, client, folder):
        api = client.list_models() if client else []
        folder_meta = scan_models_folder(folder)
        real = [
            m
            for m, meta in folder_meta.items()
            if meta.get("weights") and not meta.get("embedding")
        ]
        # a folder with no weights is a model that is not there, even if Jan
        # still lists it; a model Jan serves with no folder here still counts
        # nor is an embedding model (search vectors, it cannot write)
        empty = {
            m
            for m, meta in folder_meta.items()
            if not meta.get("weights") or meta.get("embedding")
        }
        self.api_count = len(api)
        self.scan_count = len(real)
        self.meta = folder_meta
        discovered = list(api) + real
        self.models = [m for m in self.registry.resolve(discovered) if m not in empty]
        return self.models

    def ctx_size(self, model_id):
        m = self.meta.get(model_id) or {}
        return m.get("ctx_size") or 8192

    def profile(self, model_id):
        return profile_for(model_id, self.ctx_size(model_id))

    def describe(self, model_id):
        prof = self.profile(model_id)
        bits = [
            f"~{prof['params_b']}B" if prof.get("params_b") else "size unknown",
            f"{prof['ctx_size']} ctx",
            f"{prof['label']} profile",
        ]
        if prof["is_reasoning"]:
            bits.append("reasoning-tuned (thinking will be stripped)")
        return " · ".join(bits)
