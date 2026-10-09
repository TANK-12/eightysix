"""
Paths, persisted settings, and the shared feature/quality tables.

Everything resolves through Path.home() so it works for any user account.
"""

import json
import math
import os
import sys
import shutil
import subprocess
from pathlib import Path

HOME = Path.home()

DATA_ROOT = HOME / "MediaForgeData"
MANIFEST_DIR = DATA_ROOT / "manifests"  # library-move undo logs (never auto-deleted)
INDEX_DB = DATA_ROOT / "file_index.db"  # fast-search SQLite index
SETTINGS_PATH = DATA_ROOT / "settings.json"
DL_DIR = HOME / "Downloads" / "MediaForge"

for _d in (DATA_ROOT, MANIFEST_DIR):
    _d.mkdir(parents=True, exist_ok=True)


DEFAULTS = {
    # appearance
    "theme": "dark",
    "accent": "cyan",
    "advanced_mode": True,
    # encoding
    "encoder_family": "x264",  # x264 | x265
    "hw_encoder": "cpu",  # cpu | vaapi | qsv | nvenc
    "crf": 22,
    "preset": "medium",
    "tune": "none",
    "container": "mp4",
    "audio_codec": "aac",
    "audio_bitrate": "192k",
    "threads": 0,  # 0 = all
    # subtitles
    "sub_scale_w": 1280,
    "sub_scale_h": 720,
    "sub_letterbox": True,
    "sub_mode": "hardbake_embedded",  # hardbake_embedded | hardbake_file | translate_hardbake | transcribe_hardbake | convert_only
    # translation
    "translate_backend": "jan",  # jan | google | deepl | none
    "jan_base": "http://localhost:1337/v1",
    "jan_model": "",
    "deepl_key": "",
    "target_language": "English",
    "source_language": "auto",
    # transcription (whisper)
    "whisper_model": "base",
    "whisper_lang": "auto",
    # organiser
    "library_root": (
        "/run/media/ejb/14DE4324DE42FD8C/Anime"
        if os.path.isdir("/run/media/ejb/14DE4324DE42FD8C/Anime")
        else str(HOME / "Media" / "Anime")
    ),
    # shallow by design — one folder per series, files directly inside
    "naming_pattern": "{title} ({year})/{title} - S{season:02d}E{episode:02d}",
    "metadata_provider": "anilist",  # anilist | jikan | tmdb | none
    "tmdb_key": "",
    "organise_action": "move",  # move | copy | hardlink
    "on_conflict": "skip",  # skip | number | conflicts_folder
    "hash_check": True,
    # manga
    "manga_threads": 3,
    "manga_headless": False,
    "manga_delay": 1.5,
    "manga_make_pdf": True,
    "manga_make_cbz": False,
    # image studio
    "fal_key": "",
    "request_timeout": 900,
}


ACCENTS = {
    "cyan": {"primary": "#22b8cf", "hover": "#3bc9db"},
    "violet": {"primary": "#7048e8", "hover": "#845ef7"},
    "lime": {"primary": "#66a80f", "hover": "#82c91e"},
    "rose": {"primary": "#e64980", "hover": "#f06595"},
}


def value_problem(key, value):
    """Why `value` cannot be stored under `key`, or None. A known key keeps
    its default's type (jan_base 5 used to be saved and then stopped the app
    from starting); anything else must be a plain value of sane size."""
    if len(str(key)) > 100:
        return "a setting name is too long"
    if isinstance(value, str) and len(value) > 4096:
        return f"{key} is too long"
    if isinstance(value, float) and not math.isfinite(value):
        return f"{key} must be a finite number"
    if key not in DEFAULTS:
        if value is not None and not isinstance(value, (str, bool, int, float)):
            return f"{key} must be a plain value"
        return None
    d = DEFAULTS[key]
    if isinstance(d, bool):
        return None if isinstance(value, bool) else f"{key} must be true or false"
    if isinstance(d, (int, float)):
        ok = isinstance(value, (int, float)) and not isinstance(value, bool)
        return None if ok else f"{key} must be a number"
    if isinstance(d, str):
        return None if isinstance(value, str) else f"{key} must be text"
    return None


def load_settings():
    data = dict(DEFAULTS)
    if SETTINGS_PATH.exists():
        try:
            saved = json.loads(SETTINGS_PATH.read_text("utf-8"))
            if isinstance(saved, dict):
                # a value of the wrong type falls back to its default
                data.update(
                    {k: v for k, v in saved.items() if value_problem(k, v) is None}
                )
        except Exception:
            pass
    return data


def save_settings(data):
    try:
        SETTINGS_PATH.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), "utf-8"
        )
    except Exception:
        pass


def open_path(path):
    path = str(path)
    try:
        if sys.platform.startswith("win"):
            os.startfile(path)  # noqa
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
    except Exception:
        pass


def which(name):
    return shutil.which(name)


# --------------------------------------------------------------------------
# ffmpeg capability probe (cached)
# --------------------------------------------------------------------------
_FF_CACHE = {}


def ffmpeg_caps():
    if _FF_CACHE:
        return _FF_CACHE
    caps = {
        "ffmpeg": which("ffmpeg"),
        "ffprobe": which("ffprobe"),
        "encoders": set(),
        "hwaccels": set(),
    }
    if caps["ffmpeg"]:
        try:
            out = subprocess.run(
                [caps["ffmpeg"], "-hide_banner", "-encoders"],
                capture_output=True,
                text=True,
                timeout=15,
            ).stdout
            for enc in (
                "libx264",
                "libx265",
                "h264_nvenc",
                "hevc_nvenc",
                "h264_qsv",
                "hevc_qsv",
                "h264_vaapi",
                "hevc_vaapi",
            ):
                if enc in out:
                    caps["encoders"].add(enc)
            out2 = subprocess.run(
                [caps["ffmpeg"], "-hide_banner", "-hwaccels"],
                capture_output=True,
                text=True,
                timeout=15,
            ).stdout
            for hw in ("vaapi", "qsv", "cuda", "vulkan"):
                if hw in out2:
                    caps["hwaccels"].add(hw)
        except Exception:
            pass
    _FF_CACHE.update(caps)
    return caps


def available_hw_encoders():
    """Return list of hw options this box can actually do, always incl. 'cpu'."""
    caps = ffmpeg_caps()
    opts = ["cpu"]
    if (
        "h264_vaapi" in caps["encoders"]
        and "vaapi" in caps["hwaccels"]
        and os.path.exists("/dev/dri/renderD128")
    ):
        opts.append("vaapi")
    if "h264_qsv" in caps["encoders"] and "qsv" in caps["hwaccels"]:
        opts.append("qsv")
    if "h264_nvenc" in caps["encoders"]:
        opts.append("nvenc")
    return opts


VIDEO_EXTS = {
    ".mkv",
    ".mp4",
    ".avi",
    ".mov",
    ".webm",
    ".flv",
    ".m4v",
    ".ts",
    ".wmv",
    ".mpg",
    ".mpeg",
}
SUB_EXTS = {".srt", ".ass", ".ssa", ".vtt", ".sub"}
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tiff"}
