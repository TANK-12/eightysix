"""How a catalog entry becomes a stable-diffusion.cpp command line.

One table maps a part's role to the sd flag that loads it; the sd-server
command (image models) and the sd CLI command (video models) are both built
from an entry's parts through it. Nothing here starts a process.
"""

import os
from pathlib import Path

import config

# role -> sd flag. "lora" parts are not passed by path: sd loads LoRAs by name
# from --lora-model-dir.
ROLE_FLAGS = {
    "checkpoint": "-m",
    "diffusion": "--diffusion-model",
    "high_noise_diffusion": "--high-noise-diffusion-model",
    "uncond_diffusion": "--uncond-diffusion-model",
    "llm": "--llm",
    "llm_vision": "--llm_vision",
    "t5xxl": "--t5xxl",
    "clip_l": "--clip_l",
    "clip_g": "--clip_g",
    "clip_vision": "--clip_vision",
    "vae": "--vae",
    "audio_vae": "--audio-vae",
}

GPU_BACKEND = "diffusion=vulkan0,vae=vulkan0,te=vulkan0"
CPU_BACKEND = "diffusion=cpu,vae=cpu,te=cpu"


def build_name(entry):
    return entry.get("engine_build") or config.DEFAULT_ENGINE_BUILD


def build_dir(entry):
    return Path(config.ENGINE_BUILDS[build_name(entry)]["dir"])


def server_bin(entry):
    b = config.ENGINE_BUILDS[build_name(entry)]
    return Path(b["dir"]) / b["server"]


def cli_bin(entry):
    b = config.ENGINE_BUILDS[build_name(entry)]
    return Path(b["dir"]) / b["cli"]


def build_available(entry):
    """True when the engine build this entry needs is on disk."""
    name = build_name(entry)
    if name not in config.ENGINE_BUILDS:
        return False
    b = config.ENGINE_BUILDS[name]
    binary = b["server"] if entry.get("engine") == "sd" else b["cli"]
    return (Path(b["dir"]) / binary).is_file()


def engine_env(entry):
    """Environment for an sd process: its build's own shared libraries."""
    return {**os.environ, "LD_LIBRARY_PATH": str(build_dir(entry))}


def part_args(entry, paths):
    """Flags that load the entry's parts. paths: filename -> Path on disk."""
    args = []
    for p in entry["parts"]:
        flag = ROLE_FLAGS.get(p["role"])
        if flag:
            args += [flag, str(paths[p["filename"]])]
    return args


def server_cmd(entry, paths, port, backend, lora_dir):
    """The sd-server command for an image entry on one port and backend."""
    cmd = [str(server_bin(entry))] + part_args(entry, paths)
    cmd += ["--lora-model-dir", str(lora_dir)]
    cmd += [
        "--backend",
        backend,
        "--listen-ip",
        config.SD_SERVER_HOST,
        "--listen-port",
        str(port),
    ]
    return cmd + list(entry.get("engine_flags", []))


def wants_cpu_helper(entry):
    """Whether to start the second sd-server on CPU. Only entries that opt in
    (the small SD1.5 checkpoints) do: a second copy of a big model's weights in
    RAM (31 GiB, no swap) could freeze the laptop, and a large model on CPU is
    too slow to help."""
    return bool(entry.get("cpu_helper")) and entry.get("tier") != "big"


def round_frames(frames, grid):
    """Round a frame count up to the model's grid (step*k + offset)."""
    if not grid:
        return frames
    step, offset = grid
    if frames <= offset:
        return offset
    k = -(-(frames - offset) // step)
    return step * k + offset


def video_cmd(
    entry,
    paths,
    prompt,
    out_path,
    negative_prompt="",
    frames=None,
    width=None,
    height=None,
    seed=-1,
    steps=None,
    init_image=None,
):
    """The sd CLI command for one video job (-M vid_gen)."""
    s = entry.get("settings", {})
    frames = round_frames(frames or s.get("frames", 33), s.get("frame_grid"))
    cmd = [str(cli_bin(entry)), "-M", "vid_gen"] + part_args(entry, paths)
    cmd += ["-p", prompt]
    if negative_prompt:
        cmd += ["-n", negative_prompt]
    cmd += [
        "-W",
        str(width or s.get("width", 832)),
        "-H",
        str(height or s.get("height", 480)),
        "--video-frames",
        str(frames),
        "--steps",
        str(steps or s.get("steps", 20)),
        "--cfg-scale",
        str(s.get("cfg_scale", 6.0)),
        "--sampling-method",
        s.get("sampler", "euler"),
        "-s",
        str(seed),
    ]
    if s.get("fps"):
        cmd += ["--fps", str(s["fps"])]
    if s.get("flow_shift") is not None:
        cmd += ["--flow-shift", str(s["flow_shift"])]
    hn = s.get("high_noise")
    if hn:
        cmd += [
            "--high-noise-steps",
            str(hn.get("steps", -1)),
            "--high-noise-cfg-scale",
            str(hn.get("cfg_scale", s.get("cfg_scale", 6.0))),
            "--high-noise-sampling-method",
            hn.get("sampler", "euler"),
        ]
    if init_image:
        cmd += ["-i", str(init_image)]
    cmd += ["--backend", GPU_BACKEND, "-o", str(out_path)]
    return cmd + list(entry.get("engine_flags", []))
