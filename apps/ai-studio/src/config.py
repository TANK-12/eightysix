"""Paths and defaults for the local image/video generator."""

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

BIN_DIR = ROOT / "bin"
# AI_STUDIO_MODELS_DIR / AI_STUDIO_OUTPUTS_DIR let a scratch copy or a test run
# point at its own folders instead of the live ones.
MODELS_DIR = Path(os.environ.get("AI_STUDIO_MODELS_DIR", ROOT / "models"))
OUTPUTS_DIR = Path(os.environ.get("AI_STUDIO_OUTPUTS_DIR", ROOT / "outputs"))
STATIC_DIR = ROOT / "static"

SD_BIN = BIN_DIR / "sd"
SD_SERVER_BIN = BIN_DIR / "sd-server"

# Two builds of stable-diffusion.cpp sit side by side. "current" is the build
# every SD1.5 checkpoint has been run on (master-841, 2026-09-04). "next" is a
# newer upstream release in bin/next/ (master-945-a1ded76, 2026-10-06) that
# adds Qwen-Image 2.1 and later fixes; it has only passed --help / version.
# A catalog entry picks its build with "engine_build"; entries without one use
# DEFAULT_ENGINE_BUILD (override with AI_STUDIO_SD_BUILD=next to switch all).
ENGINE_BUILDS = {
    "current": {"dir": BIN_DIR, "cli": "sd", "server": "sd-server"},
    "next": {"dir": BIN_DIR / "next", "cli": "sd-cli", "server": "sd-server"},
}
DEFAULT_ENGINE_BUILD = os.environ.get("AI_STUDIO_SD_BUILD", "current")
REALESRGAN_BIN = BIN_DIR / "realesrgan-ncnn-vulkan"
RIFE_BIN = BIN_DIR / "rife-ncnn-vulkan"

# Which model sd-server runs is dynamic -- see catalog/ (the declarative list
# of models and the files, "parts", each needs) and model_manager.py (installs
# and deletes parts and owns the sd-server processes). Parts are stored once
# in PARTS_DIR and shared by file name; files from before the rebuild stay in
# LEGACY_MODEL_DIR and are still found there. LoRA parts live in SD_LORA_DIR
# because sd-server loads LoRAs by name from one folder.
PARTS_DIR = MODELS_DIR / "parts"
LEGACY_MODEL_DIR = MODELS_DIR / "sd" / "catalog"
SD_LORA_DIR = MODELS_DIR / "sd" / "lora"
# Space a download must leave free on the disk.
DISK_SPARE_BYTES = 5 * 1024**3

SD_SERVER_HOST = "127.0.0.1"

# Two model servers: one pinned to the iGPU (fast, does most of the work),
# one pinned to CPU (slower, but runs concurrently instead of sitting idle).
# For longform jobs with many keyframes, a scheduler hands frames to
# whichever backend will free up soonest -- see hybrid.py.
GPU_SERVER_PORT = 1234
CPU_SERVER_PORT = 1235
GPU_SERVER_URL = f"http://{SD_SERVER_HOST}:{GPU_SERVER_PORT}"
CPU_SERVER_URL = f"http://{SD_SERVER_HOST}:{CPU_SERVER_PORT}"
SD_SERVER_URL = GPU_SERVER_URL  # default / single-server use (image mode)

UPSCALE_MODELS_DIR = MODELS_DIR / "upscale"
UPSCALE_MODEL_FAST = "realesr-animevideov3-x4"  # small (~1.2MB), very fast
UPSCALE_MODEL_QUALITY = "realesrgan-x4plus"  # bigger (~33MB), sharper detail

# The Iris Xe's Vulkan driver enforces a per-allocation VRAM ceiling (the same
# one that forces --*-conv-direct / --vae-tiling on sd-server -- see
# model_manager._launch). realesrgan-ncnn-vulkan defaults to auto tile sizing
# (-t 0), which on this machine picks a tile far larger than that ceiling: the
# allocation fails mid-run and the tool writes back coherent rectangular block
# garbage instead of erroring, so a clean generated image comes out of "AI
# upscale" corrupted. A fixed, conservative tile keeps every allocation under
# the ceiling; ncnn pads tiles internally so seams are not visible. Lower this
# further if block artifacts ever reappear.
UPSCALE_TILE = 200
# rife-ncnn-vulkan has no -t; its large-frame path is -u (UHD mode). Video mode
# generates at <=512px keyframes today so it does not currently hit the ceiling,
# but flip this on if interpolation ever shows the same block artifacts.
RIFE_UHD_MODE = False

RIFE_MODEL_DIR = MODELS_DIR / "interp" / "rife-v4.6"

OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

# Steps/cfg/sampler are per-model (each catalog entry's "settings") since they aren't
# portable across models -- see model_manager.run_settings().
DEFAULT_BASE_SIZE = 512  # native gen resolution before AI upscale
