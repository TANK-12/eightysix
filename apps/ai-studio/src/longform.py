"""Longform, directable, checkpointed video generation.

How a scene is made (rebuilt 2026-10-08, see docs/AUDIT.md):

1. **Anchor.** The first scene's first frame is a txt2img; every later
   scene's first frame is an img2img of the previous scene's last frame (a
   content-aware transition rather than a hard cut).
2. **Blocks.** The remaining frames go in blocks of `anchor_interval`. Every
   frame in a block is the block's *base* frame warped by the camera
   (motion.warp: one resample, mirror-filled edges), then "healed" by an
   img2img pass. Frames inside a block do not depend on each other, so the
   HybridScheduler runs them on the iGPU and the CPU at once.
3. **Re-basing.** The last healed frame of a block becomes the base of the
   next block. So a long pan keeps walking into newly painted scenery
   instead of into an ever larger mirror image of the first frame.
4. **Colour coherence.** Each healed frame's colours are pulled toward the
   scene's anchor by `anchor_weight` (motion.color_match), which stops the
   colour drift that chaining through img2img brings. (The old code blended
   the anchor *picture* into the frame instead, which ghosted any moving
   camera.)
5. Each scene uses one seed for all its frames (a random one when the
   request says -1), which cuts frame-to-frame flicker.

Scene boundaries get a short cross-fade before interpolation and encoding.

State and cancelling: `state.json` in the work dir says `status` (running,
done, failed, cancelled), `phase`, frame counts and any error, and is
written atomically so a reader never sees half a file. `request_cancel(dir)`
(or a file named `cancel` in the work dir) stops the job at the next frame.
"""

import json
import os
import random
import shutil
import time
from pathlib import Path
from typing import Any

import config
import engine
import motion as motion_mod
from hybrid import Cancelled, HybridScheduler

CANCEL_FILE = "cancel"
TRANSITION_STRENGTH = 0.6  # how far a scene's anchor moves from the last scene


def request_cancel(work_dir):
    """Ask the job running in `work_dir` to stop at the next frame. Safe to
    call for a job that has already finished (it is ignored)."""
    p = Path(work_dir)
    if p.is_dir():
        (p / CANCEL_FILE).touch()
        return True
    return False


class LongformJob:
    def __init__(
        self,
        job_id,
        work_dir,
        scenes,
        width,
        height,
        steps,
        cfg_scale,
        anchor_interval,
        anchor_weight,
        crossfade_frames,
        use_cpu,
        upscale,
        upscale_model,
        sampler="lcm",
        use_lcm=True,
        upscale_scale=4,
        gpu_url=None,
        cpu_url=None,
    ):
        self.job_id = job_id
        self.work_dir = Path(work_dir)
        self.scenes = (
            scenes  # dicts: prompt, negative_prompt, frames, motion, strength, seed
        )
        self.width = width
        self.height = height
        self.steps = steps
        self.cfg_scale = cfg_scale
        self.sampler = sampler
        self.use_lcm = use_lcm
        self.anchor_interval = max(1, int(anchor_interval))
        self.anchor_weight = anchor_weight
        self.crossfade_frames = crossfade_frames
        self.use_cpu = use_cpu
        self.upscale = upscale
        self.upscale_scale = upscale_scale
        self.upscale_model = upscale_model
        self.gpu_url = gpu_url or config.GPU_SERVER_URL
        self.cpu_url = cpu_url or config.CPU_SERVER_URL
        self._scheduler = None

        self.frames_dir = self.work_dir / "keyframes"
        self.upscaled_dir = self.work_dir / "keyframes_up"
        self.interp_dir = self.work_dir / "interp"
        self.frames_dir.mkdir(parents=True, exist_ok=True)
        self.cancel_path = self.work_dir / CANCEL_FILE

        self.state_path = self.work_dir / "state.json"
        self.state = {
            "job_id": job_id,
            "status": "running",
            "phase": "keyframes",
            "error": None,
            "scenes": len(scenes),
            "total_frames": sum(s["frames"] for s in scenes),
            "completed_frames": 0,
            "backend_counts": {"gpu": 0, "cpu": 0},
            "started_at": time.time(),
            "seeds": [],
            "frames": [],  # per-frame checkpoint log
        }
        self._save_state()

    # -- state -------------------------------------------------------------

    def _save_state(self):
        tmp = self.state_path.with_name("state.json.tmp")
        tmp.write_text(json.dumps(self.state, indent=2))
        os.replace(tmp, self.state_path)

    def _set(self, **fields):
        self.state.update(fields)
        self._save_state()

    def _checkpoint_frame(self, global_idx, scene_idx, backend, elapsed):
        self.state["completed_frames"] += 1
        counts = self.state["backend_counts"]
        counts[backend] = counts.get(backend, 0) + 1
        self.state["frames"].append(
            {
                "index": global_idx,
                "scene": scene_idx,
                "backend": backend,
                "seconds": round(elapsed, 2),
            }
        )
        self._save_state()

    def cancelled(self):
        return self.cancel_path.exists()

    def _check_cancel(self):
        if self.cancelled():
            if self._scheduler is not None:
                self._scheduler.cancel()
            raise Cancelled()

    def _guard(self, phase, fn, *args):
        """Run one phase, recording failure or cancelling in state.json."""
        self._set(phase=phase)
        try:
            self._check_cancel()
            return fn(*args)
        except Cancelled:
            self._set(status="cancelled")
            raise
        except Exception as e:
            self._set(status="failed", error=str(e)[:2000])
            raise

    # -- keyframes ---------------------------------------------------------

    def run(self):
        """Make every keyframe. Returns (frame paths in order, backend stats)."""
        scheduler = HybridScheduler(
            use_cpu=self.use_cpu, gpu_url=self.gpu_url, cpu_url=self.cpu_url
        )
        self._scheduler = scheduler
        scheduler.start()
        try:
            paths = self._guard("keyframes", self._run, scheduler)
            return paths, scheduler.stats()
        finally:
            scheduler.shutdown()
            self._scheduler = None

    def _gen_kwargs(self, scene, seed) -> dict[str, Any]:
        return dict(
            prompt=scene["prompt"],
            negative_prompt=scene.get("negative_prompt", ""),
            width=self.width,
            height=self.height,
            steps=self.steps,
            cfg_scale=self.cfg_scale,
            seed=seed,
            sampler=self.sampler,
            use_lcm=self.use_lcm,
        )

    def _run(self, scheduler):
        all_frame_paths = []
        scene_starts = []  # global index of each scene's first frame
        prev_last = None
        global_idx = 0

        for scene_idx, scene in enumerate(self.scenes):
            self._check_cancel()
            scene_starts.append(global_idx)
            seed = scene.get("seed", -1)
            if seed is None or seed < 0:
                seed = random.randint(0, 2**31 - 1)
            self.state["seeds"].append(seed)
            kw = self._gen_kwargs(scene, seed)

            anchor_path = self.frames_dir / f"{global_idx:08d}.png"
            t0 = time.time()
            if prev_last is None:
                engine.txt2img(out_path=str(anchor_path), server_url=self.gpu_url, **kw)
            else:
                engine.img2img(
                    init_image=prev_last,
                    strength=TRANSITION_STRENGTH,
                    out_path=str(anchor_path),
                    server_url=self.gpu_url,
                    **kw,
                )
            anchor_bytes = anchor_path.read_bytes()
            self._checkpoint_frame(global_idx, scene_idx, "gpu", time.time() - t0)
            all_frame_paths.append(anchor_path)
            global_idx += 1

            base_bytes, base_step = anchor_bytes, 0
            last_path = anchor_path
            n = scene["frames"]
            for block_start in range(1, n, self.anchor_interval):
                self._check_cancel()
                steps_in_block = range(
                    block_start, min(n, block_start + self.anchor_interval)
                )
                paths = [
                    self.frames_dir / f"{global_idx + k:08d}.png"
                    for k in range(len(steps_in_block))
                ]
                tasks = [
                    self._heal_task(
                        motion_mod.warp(
                            base_bytes, scene["motion"], steps=step - base_step
                        ),
                        path,
                        scene,
                        kw,
                        anchor_bytes,
                    )
                    for step, path in zip(steps_in_block, paths)
                ]
                first = global_idx

                def progress(
                    i, backend, elapsed, _done, _total, first=first, s=scene_idx
                ):
                    self._checkpoint_frame(first + i, s, backend, elapsed)

                scheduler.run_all(tasks, progress_cb=progress)
                all_frame_paths.extend(paths)
                global_idx += len(paths)
                last_path = paths[-1]
                base_bytes, base_step = last_path.read_bytes(), steps_in_block[-1]
            prev_last = last_path

        if self.crossfade_frames > 0:
            self._apply_crossfades(all_frame_paths, scene_starts)

        self.state["gen_seconds"] = round(time.time() - self.state["started_at"], 2)
        self._save_state()
        return all_frame_paths

    def _heal_task(self, warped_bytes, out_path, scene, kw, anchor_bytes):
        def task(server_url):
            if self.cancelled():
                raise Cancelled()
            engine.img2img(
                init_image=warped_bytes,
                strength=scene["strength"],
                out_path=str(out_path),
                server_url=server_url,
                **kw,
            )
            if self.anchor_weight > 0:
                fixed = motion_mod.color_match(
                    Path(out_path).read_bytes(), anchor_bytes, self.anchor_weight
                )
                Path(out_path).write_bytes(fixed)
            return out_path

        return task

    def _apply_crossfades(self, all_frame_paths, scene_starts):
        """Blend pixels across each scene boundary so the cut isn't a hard
        jump. Never reaches past the previous scene's own first frame, and
        never past the next scene's last one."""
        from PIL import Image

        k = self.crossfade_frames
        bounds = scene_starts + [len(all_frame_paths)]
        for s in range(1, len(scene_starts)):
            start = scene_starts[s]
            tail = all_frame_paths[max(scene_starts[s - 1], start - k) : start]
            head = all_frame_paths[start : min(bounds[s + 1], start + k)]
            n = min(len(tail), len(head))
            if n == 0:
                continue
            tail, head = tail[-n:], head[:n]
            for i in range(n):
                t = (i + 1) / (n + 1)  # 0 (all tail) .. 1 (all head)
                a = Image.open(tail[i]).convert("RGB")
                b = Image.open(head[i]).convert("RGB").resize(a.size)
                Image.blend(a, b, t * 0.5).save(tail[i])
                Image.blend(a, b, 0.5 + t * 0.5).save(head[i])

    # -- upscale, interpolate, encode -------------------------------------

    def upscale_all(self, frame_paths):
        def work():
            t0 = time.time()
            if not self.upscale:
                return self.frames_dir, time.time() - t0
            self.upscaled_dir.mkdir(parents=True, exist_ok=True)
            for f in frame_paths:
                self._check_cancel()
                engine.upscale(
                    str(f),
                    str(self.upscaled_dir / f.name),
                    self.upscale_model,
                    scale=self.upscale_scale,
                )
            return self.upscaled_dir, time.time() - t0

        return self._guard("upscale", work)

    def interpolate_and_encode(self, source_dir, hold_frames, fps, out_path):
        def work():
            t0 = time.time()
            frames = sorted(Path(source_dir).glob("*.png"))
            if not frames:
                raise RuntimeError("no keyframes to make a video from")
            self.interp_dir.mkdir(parents=True, exist_ok=True)
            if len(frames) == 1:
                # RIFE needs two frames; one keyframe is simply held.
                for i in range(max(1, hold_frames)):
                    shutil.copy(frames[0], self.interp_dir / f"{i + 1:08d}.png")
            else:
                total_target = (len(frames) - 1) * hold_frames + 1
                engine.interpolate(str(source_dir), str(self.interp_dir), total_target)
            self._check_cancel()
            self._set(phase="encode")
            engine.encode_video(str(self.interp_dir), out_path, fps=fps)
            self._set(status="done", phase="done")
            return time.time() - t0

        return self._guard("interpolate", work)
