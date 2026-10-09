"""
Paths, persisted settings, and the ffmpeg capability probe.

Everything resolves through Path.home() so it works for any user account.
Nothing is written inside the app folder -- user data lives in
~/PulseForgeData/.
"""

import json
import math
import os
import shutil
import subprocess
from pathlib import Path

HOME = Path.home()

DATA_ROOT = HOME / "PulseForgeData"
PROJECTS_DIR = DATA_ROOT / "projects"
MOTION_CACHE_DIR = DATA_ROOT / "cache" / "motion"
BEDS_CACHE_DIR = DATA_ROOT / "cache" / "beds"
PRESETS_DIR = DATA_ROOT / "presets"  # looks the user saved themselves
SETTINGS_PATH = DATA_ROOT / "settings.json"
DEFAULT_RENDER_DIR = HOME / "Videos" / "PulseForge"
OUTPUTS_DIR = DATA_ROOT / "outputs"  # Autopilot's state, ledger and ready packages
AUTOPILOT_DIR = OUTPUTS_DIR / "autopilot"

for _d in (DATA_ROOT, PROJECTS_DIR, MOTION_CACHE_DIR, BEDS_CACHE_DIR, PRESETS_DIR):
    _d.mkdir(parents=True, exist_ok=True)


# internal render height per quality tier -- ffmpeg upscales to the real format
QUALITY_HEIGHTS = {"draft": 540, "standard": 720, "high": 1080}


DEFAULTS = {
    # rendering
    "encoder": "cpu",  # cpu | vaapi | qsv
    "crf": 18,  # visually near-lossless for flat visualiser output
    "preset": "medium",
    "audio_bitrate": "256k",
    "loudness_lufs": -14.0,  # YouTube's normalisation target
    "threads": 0,  # 0 = all cores
    # How many shot beds to render at once. Deliberately well under the core
    # count: a render should not make the machine unusable while it runs.
    "render_workers": 3,
    "preview_seconds": 20,
    "preview_height": 540,
    "shot_loop_seconds": 12.0,  # unique motion per shot before it repeats
    "shot_preview_seconds": 10,
    "render_quality": "standard",  # draft (540p) | standard (720p) | high (1080p)
    # paths / services
    "render_dir": str(DEFAULT_RENDER_DIR),
    # ui
    "advanced_mode": False,
    # "simple" is a guided four-step page; "advanced" is the full editor. The
    # choice sticks once made.
    "ui_mode": "simple",
}


def load_settings():
    data = dict(DEFAULTS)
    if SETTINGS_PATH.exists():
        try:
            data.update(json.loads(SETTINGS_PATH.read_text(encoding="utf-8")))
        except Exception:
            pass
    # NaN or Infinity cannot be sent to the page, and one such value used to
    # stop the app from starting at all: such a value is simply left out
    return {
        k: v
        for k, v in data.items()
        if not (isinstance(v, float) and not math.isfinite(v))
    }


def save_settings(data):
    try:
        SETTINGS_PATH.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception:
        pass


def which(name):
    return shutil.which(name)


_FF_CACHE: dict = {}


def ffmpeg_caps():
    """{'ffmpeg', 'ffprobe', 'encoders': set, 'hwaccels': set}. Cached."""
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
            for hw in ("vaapi", "qsv"):
                if hw in out2:
                    caps["hwaccels"].add(hw)
        except Exception:
            pass
    _FF_CACHE.update(caps)
    return caps


def available_encoders():
    """Encoder options this box can actually do. 'cpu' is always present."""
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
    return opts


AUDIO_EXTS = {".mp3", ".wav", ".flac", ".m4a", ".aac", ".ogg", ".opus", ".wma"}
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
