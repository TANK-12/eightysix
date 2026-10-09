"""
Paths, constants and tunable defaults for NovelForge.

Everything here is resolved with os.path.expanduser so it works for any user
account, not one hard-coded machine.
"""

import os
import sys
import json

HOME = os.path.expanduser("~")

# --------------------------------------------------------------------------
# On-disk layout
# --------------------------------------------------------------------------
# We reuse the same data root the earlier "novelN.py" scripts used so old
# projects remain visible, but everything NovelForge writes is namespaced.
DATA_ROOT = os.path.join(HOME, "NovelMakerData")
PROJECTS_DIR = os.path.join(DATA_ROOT, "projects")
SERIES_DIR = os.path.join(DATA_ROOT, "series")
STYLE_LIB_PATH = os.path.join(DATA_ROOT, "style_library.json")
KNOWN_MODELS_PATH = os.path.join(DATA_ROOT, "known_models.json")
SETTINGS_PATH = os.path.join(DATA_ROOT, "novelforge_settings.json")
# Deleted projects, series and chapters are moved here, never erased, so a
# wrong click can be undone by moving the folder back.
TRASH_DIR = os.path.join(DATA_ROOT, ".trash")

for _d in (DATA_ROOT, PROJECTS_DIR, SERIES_DIR):
    os.makedirs(_d, exist_ok=True)

# --------------------------------------------------------------------------
# Jan / llama.cpp connection
# --------------------------------------------------------------------------
DEFAULT_API_BASE = "http://localhost:1337/v1"

# Jan's Flatpak bundles its llama.cpp models here. Also checked: a native
# install path. The folder scan is best-effort; the live API is authoritative.
DEFAULT_MODELS_PATHS = [
    os.path.join(
        HOME, ".var", "app", "ai.jan.Jan", "data", "Jan", "data", "llamacpp", "models"
    ),
    os.path.join(HOME, "jan", "data", "llamacpp", "models"),
    os.path.join(HOME, ".config", "Jan", "data", "llamacpp", "models"),
]


def default_models_path():
    for p in DEFAULT_MODELS_PATHS:
        if os.path.isdir(p):
            return p
    return DEFAULT_MODELS_PATHS[0]


# A tiny safety net so the model dropdown is never empty before the first scan.
FALLBACK_MODELS = [
    "gemma4-opus48-Q4_K_M",
    "Gemma-4-12B-OBLITERATED-Q4_K_M",
    "Qwen3_6-14B-A3B-FableVibes-Q5_K_M",
    "glm-4_7-flash-claude-4_5-opus_iq4_xs",
    "Qwen3_5-4B-IQ4_XS",
    "Qwen3_5-2B-Uncensored-HauhauCS-Aggressive-Q4_K_M",
    "gemma-4-E2B-it-IQ4_XS",
    "Llama-3_2-3B-Instruct-IQ4_XS",
    "Qwen3-0_6B-UD-IQ2_XXS",
]

# --------------------------------------------------------------------------
# Generation defaults -- deliberately biased toward LONG output.
# These can all be changed live in the UI; Advanced mode exposes the rest.
# --------------------------------------------------------------------------
DEFAULTS = {
    # --- scope ---
    "story_scope": "series",  # "oneshot" | "series"
    "planned_books": 3,  # only meaningful for "series"
    "world_depth": "rich",  # sketch | standard | rich | epic
    # --- length (biased long) ---
    "target_chapters": 30,
    "target_words_per_chapter": 3500,  # the loop keeps going until it hits this
    "scenes_per_chapter": 4,  # a chapter is written scene-by-scene
    "max_tokens_per_call": 4096,  # per streamed model call (not per chapter)
    "max_continues_per_scene": 3,  # if the model stalls under target, nudge it
    # --- memory / context ---
    "context_budget": 24000,  # clamped down to the model's real ctx_size
    "context_safety_margin": 1500,  # tokens kept free for the reply
    "recent_full_chapters": 2,  # kept verbatim; older ones get summarised
    "auto_codex": True,
    "auto_summary": True,
    "auto_running_synopsis": True,  # rolling "story so far" digest
    "auto_open_threads": True,  # track unresolved plot threads
    "reconcile_every": 12,  # codex contradiction sweep cadence (0 = off)
    # --- sampling ---
    "prose_temperature": 0.9,
    "structure_temperature": 0.3,  # codex / index calls
    "worldbuild_temperature": 0.78,  # Free-Rein prose passes
    "summary_temperature": 0.2,
    # anti-repetition. DRY is the effective one for llama.cpp loops; the OpenAI
    # penalties are kept light because heavy values flatten the prose.
    "dry_multiplier": 0.8,  # 0 disables DRY
    "dry_base": 1.75,
    "dry_allowed_length": 2,
    "dry_penalty_last_n": 1024,
    "repeat_penalty": 1.08,
    "repeat_last_n": 512,
    "frequency_penalty": 0.3,
    "presence_penalty": 0.3,
    "top_p": 0.92,
    "min_p": 0.03,
    "degeneration_guard": True,  # abort + retry a scene that loops
    # --- memory / stability ---
    # Generation pauses (and, if it can't recover, stops cleanly and resumably)
    # when free system RAM drops below this. Stops Jan's llama.cpp router loading
    # a second multi-GB model on a full machine and freezing the laptop.
    "ram_guard": True,
    "min_free_ram_gb": 2.5,
    "ram_guard_wait_s": 90,  # how long to wait for RAM to free before stopping
    # --- misc ---
    "strip_reasoning": True,  # drop <think>...</think> from model output
    "request_timeout": 1200,
    "advanced_mode": False,
    "theme": "dark",
    "accent": "forge",  # see theme.py
    # --- export (Export tab) ---
    "author_name": "",  # written into EPUB/PDF/audiobook metadata
    "export_formats": ["epub"],  # any of epub | pdf | txt
    "export_dir": "",  # blank = <project>/export/
    "export_open_after": True,  # reveal the folder when a job finishes
    "epub_language": "en",
    "pdf_page_size": "A4",  # A4 | Letter
    # --- cover art ---
    "cover_style": "gradient",  # gradient | duotone | minimal
    "cover_width": 1600,
    "cover_height": 2400,
    "ai_image_backend": False,  # only meaningful if diffusers is installed
    # --- audiobook / local TTS (piper) ---
    "tts_voice": "en_US-ryan-high",  # default narrator (a "-high" model; far
    # less robotic than the "-medium" ones)
    "tts_voices_dir": "",  # blank = ~/NovelMakerData/tts_voices/
    "tts_mode": "cast",  # single | cast | narrator_voices
    "tts_per_character_voices": True,  # legacy fallback when tts_mode is unset
    "tts_announce_chapter": True,
    "tts_speed": 1.0,
    "tts_variation": 0.85,  # piper noise_w_scale: prosody wobble.
    # higher = more human, lower = flatter
    "tts_format": "m4a",  # m4a | mp3 | wav
    "tts_chapter_pause_ms": 900,
    "tts_keep_chapter_wavs": False,
    # --- ui ---
    "ui_scale": 1.0,  # widget scaling, applied at startup
    "ui_density": "comfortable",  # comfortable | compact
}


# Free-Rein world-build profiles. `passes` = how many prose passes; the rest
# scale how much each pass asks for. Bigger = richer + slower.
WORLD_DEPTH = {
    "sketch": {
        "label": "Sketch",
        "passes": 1,
        "cast": "5-7",
        "locations": "3-5",
        "factions": "2-3",
        "foundation_words": 600,
        "pass_tokens": 2400,
        "threads": 3,
    },
    "standard": {
        "label": "Standard",
        "passes": 2,
        "cast": "9-13",
        "locations": "5-8",
        "factions": "3-4",
        "foundation_words": 1300,
        "pass_tokens": 3400,
        "threads": 5,
    },
    "rich": {
        "label": "Rich",
        "passes": 3,
        "cast": "15-22",
        "locations": "9-13",
        "factions": "4-6",
        "foundation_words": 2200,
        "pass_tokens": 5000,
        "threads": 8,
    },
    "epic": {
        "label": "Epic",
        "passes": 4,
        "cast": "24-34",
        "locations": "14-20",
        "factions": "6-10",
        "foundation_words": 3800,
        "pass_tokens": 6800,
        "threads": 12,
    },
}


def load_settings():
    data = dict(DEFAULTS)
    if os.path.exists(SETTINGS_PATH):
        try:
            with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
                data.update(json.load(f))
        except Exception:
            pass
    return data


def save_settings(data):
    try:
        with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def open_in_file_manager(path):
    import subprocess

    try:
        if sys.platform.startswith("win"):
            os.startfile(path)  # noqa
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
    except Exception:
        pass
