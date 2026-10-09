"""Talks to the three native engines that do the actual work:
- sd-server (stable-diffusion.cpp, Vulkan) kept resident so the model stays
  loaded in VRAM between calls -- this is what makes back-to-back
  generations fast instead of paying multi-second reload cost every time.
- realesrgan-ncnn-vulkan  -> AI upscale (the speed trick: generate small,
  upscale big instead of generating at full resolution).
- rife-ncnn-vulkan        -> frame interpolation for video mode.
"""

import base64
import json
import subprocess
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

import config
from catalog import LCM_LORA_NAME


class EngineError(RuntimeError):
    pass


def _run(cmd):
    proc = subprocess.run(
        [str(c) for c in cmd],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    if proc.returncode != 0:
        raise EngineError(
            f"command failed ({proc.returncode}): {' '.join(str(c) for c in cmd)}\n{proc.stdout}"
        )
    return proc.stdout


def _sd_request(server_url, path, payload, timeout=900):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"{server_url}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        raise EngineError(
            f"sd-server error {e.code}: {e.read().decode(errors='replace')}"
        )
    except urllib.error.URLError as e:
        raise EngineError(f"sd-server unreachable at {server_url}: {e}")


def wait_for_server(server_url=config.SD_SERVER_URL, timeout=120):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen(f"{server_url}/sdapi/v1/samplers", timeout=2)
            return True
        except Exception:
            time.sleep(0.5)
    return False


def _with_lcm_lora(prompt, use_lcm):
    if not use_lcm:
        return prompt
    tag = f"<lora:{LCM_LORA_NAME}:1>"
    return prompt if tag in prompt else f"{prompt} {tag}"


def txt2img(
    prompt,
    negative_prompt,
    width,
    height,
    steps,
    cfg_scale,
    seed,
    out_path,
    server_url=config.SD_SERVER_URL,
    sampler="lcm",
    use_lcm=True,
):
    body = {
        "prompt": _with_lcm_lora(prompt, use_lcm),
        "negative_prompt": negative_prompt,
        "width": width,
        "height": height,
        "steps": steps,
        "cfg_scale": cfg_scale,
        "sampler_name": sampler,
        "seed": seed,
    }
    result = _sd_request(server_url, "/sdapi/v1/txt2img", body)
    Path(out_path).write_bytes(base64.b64decode(result["images"][0]))
    return out_path


def img2img(
    prompt,
    negative_prompt,
    init_image,
    width,
    height,
    steps,
    cfg_scale,
    strength,
    seed,
    out_path,
    server_url=config.SD_SERVER_URL,
    sampler="lcm",
    use_lcm=True,
):
    if isinstance(init_image, (str, Path)):
        init_bytes = Path(init_image).read_bytes()
    else:
        init_bytes = init_image  # already raw PNG bytes (e.g. from a motion warp)
    init_b64 = base64.b64encode(init_bytes).decode()
    body = {
        "prompt": _with_lcm_lora(prompt, use_lcm),
        "negative_prompt": negative_prompt,
        "init_images": [init_b64],
        "denoising_strength": strength,
        "width": width,
        "height": height,
        "steps": steps,
        "cfg_scale": cfg_scale,
        "sampler_name": sampler,
        "seed": seed,
    }
    result = _sd_request(server_url, "/sdapi/v1/img2img", body)
    Path(out_path).write_bytes(base64.b64decode(result["images"][0]))
    return out_path


def upscale(in_path, out_path, model_name, scale=4):
    cmd = [
        config.REALESRGAN_BIN,
        "-i",
        in_path,
        "-o",
        out_path,
        "-n",
        model_name,
        "-s",
        str(scale),
        "-m",
        config.UPSCALE_MODELS_DIR,
        # -t caps the per-tile Vulkan allocation. Without it ncnn auto-picks a
        # tile bigger than the Iris Xe per-allocation ceiling and returns block
        # garbage instead of failing -- see config.UPSCALE_TILE.
        "-t",
        str(config.UPSCALE_TILE),
    ]
    _run(cmd)
    out = Path(out_path)
    if not out.is_file() or out.stat().st_size == 0:
        # realesrgan-ncnn-vulkan exits 0 without writing anything when it
        # cannot read its input; say so instead of failing later on open.
        raise EngineError(
            f"the upscaler made no picture from {Path(in_path).name} "
            "(it could not read the input or ran out of graphics memory)"
        )
    return out_path


def interpolate(frame_dir, out_dir, target_frame_count):
    out_dir_p = Path(out_dir)
    out_dir_p.mkdir(parents=True, exist_ok=True)
    if not any(Path(frame_dir).glob("*.png")):
        # rife on an empty folder prints "decode image failed" and segfaults
        raise EngineError("smooth motion had no frames to work from")
    cmd = [
        config.RIFE_BIN,
        "-i",
        frame_dir,
        "-o",
        out_dir,
        "-n",
        str(target_frame_count),
        "-m",
        config.RIFE_MODEL_DIR,
    ]
    if config.RIFE_UHD_MODE:
        cmd.append("-u")  # rife has no -t; -u is its large-frame (tiled/padded) path
    _run(cmd)
    made = len(list(out_dir_p.glob("*.png")))
    if made < int(target_frame_count):
        # rife can exit 0 after failing to decode its inputs
        raise EngineError(
            f"smooth motion made {made} of {target_frame_count} frames "
            "(it could not read some of the input frames)"
        )
    return out_dir


def encode_video(frame_dir, out_path, fps):
    cmd = [
        "ffmpeg",
        "-y",
        "-framerate",
        str(fps),
        "-i",
        str(Path(frame_dir) / "%08d.png"),
        # libx264 with yuv420p needs even sizes (65x63 fails with rc 187):
        # pad odd sides by one pixel.
        "-vf",
        "pad=ceil(iw/2)*2:ceil(ih/2)*2",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-crf",
        "18",
        str(out_path),
    ]
    _run(cmd)
    return out_path


def new_id():
    return uuid.uuid4().hex[:12]
