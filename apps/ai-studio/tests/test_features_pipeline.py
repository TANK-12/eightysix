"""Audit 2026-10-08: the image and video pipelines run end to end against a
fake sd-server (tests/sd_stub.py) on CPU.

Real: the HTTP requests and their JSON shape, the PNG round trip, motion
warps, the GPU+CPU scheduler, RIFE (the real binary, forced onto the CPU
with `-g -1`), ffmpeg encoding checked with ffprobe, the library and
thumbnails. Faked: the diffusion model (the stub) and Real-ESRGAN (a tiny
script that resizes with Pillow: the real binary has no CPU mode, so it would
touch the iGPU). Nothing reads or writes Emerson's models/ or outputs/.
"""

# PIL's getpixel() is typed as float | tuple | None; these tests read RGB images.
# pyright: reportIndexIssue=false, reportOptionalSubscript=false, reportArgumentType=false

import base64
import io
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest
from fastapi import HTTPException
from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "src"))
sys.path.insert(0, str(HERE))

import config  # noqa: E402  # pyright: ignore[reportMissingImports]
import engine  # noqa: E402  # pyright: ignore[reportMissingImports]
import library  # noqa: E402  # pyright: ignore[reportMissingImports]
import longform  # noqa: E402  # pyright: ignore[reportMissingImports]
from hybrid import Cancelled  # noqa: E402  # pyright: ignore[reportMissingImports]
from sd_stub import SdStub  # noqa: E402

REAL_RIFE = config.ROOT / "bin" / "rife-ncnn-vulkan"
REAL_RIFE_MODEL = config.ROOT / "models" / "interp" / "rife-v4.6"
PY = sys.executable


def ffprobe(path):
    out = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-count_frames",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=codec_name,width,height,nb_read_frames,pix_fmt",
            "-of",
            "json",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return json.loads(out)["streams"][0]


@pytest.fixture
def stubs():
    with SdStub() as gpu, SdStub() as cpu:
        yield gpu, cpu


@pytest.fixture
def studio(tmp_path, monkeypatch, stubs):
    """Every path and server URL the pipeline uses, pointed at scratch."""
    gpu, cpu = stubs
    out = tmp_path / "outputs"
    out.mkdir()
    monkeypatch.setattr(config, "OUTPUTS_DIR", out)
    monkeypatch.setattr(config, "GPU_SERVER_URL", gpu.url)
    monkeypatch.setattr(config, "CPU_SERVER_URL", cpu.url)
    monkeypatch.setattr(config, "SD_SERVER_URL", gpu.url)
    monkeypatch.setattr(library, "DB_PATH", out / "library.db")
    library.init()

    # RIFE: the real binary, on the CPU.
    rife = tmp_path / "rife-cpu"
    rife.write_text(f'#!/bin/sh\nexec "{REAL_RIFE}" "$@" -g -1\n')
    rife.chmod(0o755)
    monkeypatch.setattr(config, "RIFE_BIN", rife)
    monkeypatch.setattr(config, "RIFE_MODEL_DIR", REAL_RIFE_MODEL)
    # Real-ESRGAN stand-in: same flags, Pillow resize.
    up = tmp_path / "upscale-fake"
    up.write_text(
        f"#!{PY}\nimport sys\nfrom PIL import Image\n"
        "a = sys.argv[1:]\nget = lambda f: a[a.index(f) + 1]\n"
        "im = Image.open(get('-i')); s = int(get('-s'))\n"
        "im.resize((im.width * s, im.height * s)).save(get('-o'))\n"
    )
    up.chmod(0o755)
    monkeypatch.setattr(config, "REALESRGAN_BIN", up)
    return {"gpu": gpu, "cpu": cpu, "out": out, "tmp": tmp_path}


# -- engine request building ---------------------------------------------------


def test_txt2img_sends_a1111_body_and_saves_png(studio):
    gpu = studio["gpu"]
    dest = studio["tmp"] / "a.png"
    engine.txt2img(
        "a fox",
        "blurry",
        96,
        64,
        4,
        1.5,
        7,
        str(dest),
        server_url=gpu.url,
        sampler="euler",
        use_lcm=False,
    )
    (body,) = gpu.bodies("/txt2img")
    want = {
        "prompt": "a fox",
        "negative_prompt": "blurry",
        "width": 96,
        "height": 64,
        "steps": 4,
        "cfg_scale": 1.5,
        "sampler_name": "euler",
        "seed": 7,
    }
    assert {k: body.get(k) for k in want} == want
    assert Image.open(dest).size == (96, 64)


def test_lcm_lora_tag_added_once(studio):
    gpu = studio["gpu"]
    dest = studio["tmp"] / "a.png"
    engine.txt2img(
        "a fox", "", 64, 64, 4, 1, 1, str(dest), server_url=gpu.url, use_lcm=True
    )
    engine.txt2img(
        gpu.bodies("/txt2img")[0]["prompt"],
        "",
        64,
        64,
        4,
        1,
        1,
        str(dest),
        server_url=gpu.url,
        use_lcm=True,
    )
    prompts = [b["prompt"] for b in gpu.bodies("/txt2img")]
    assert all(p.count("<lora:") == 1 for p in prompts), prompts


def test_img2img_sends_the_init_image_from_bytes_or_path(studio):
    gpu = studio["gpu"]
    src = studio["tmp"] / "src.png"
    Image.new("RGB", (64, 64), (10, 200, 30)).save(src)
    for init in (src, src.read_bytes()):
        engine.img2img(
            "x",
            "",
            init,
            64,
            64,
            4,
            1,
            0.4,
            3,
            str(studio["tmp"] / "o.png"),
            server_url=gpu.url,
            use_lcm=False,
        )
    for body in gpu.bodies("/img2img"):
        assert base64.b64decode(body["init_images"][0]) == src.read_bytes()
        assert body["denoising_strength"] == 0.4


def test_server_errors_become_engine_errors(studio):
    gpu = studio["gpu"]
    gpu.fail_with = 500
    with pytest.raises(engine.EngineError, match="500"):
        engine.txt2img(
            "x", "", 64, 64, 1, 1, 1, str(studio["tmp"] / "a.png"), server_url=gpu.url
        )
    with pytest.raises(engine.EngineError, match="unreachable"):
        engine.txt2img(
            "x",
            "",
            64,
            64,
            1,
            1,
            1,
            str(studio["tmp"] / "a.png"),
            server_url="http://127.0.0.1:9",
        )


# -- long-form video -----------------------------------------------------------


def make_job(studio, scenes, job_id="vid1", **kw):
    args = dict(
        job_id=job_id,
        work_dir=studio["out"] / job_id,
        scenes=scenes,
        width=64,
        height=64,
        steps=2,
        cfg_scale=1.0,
        anchor_interval=3,
        anchor_weight=0.2,
        crossfade_frames=2,
        use_cpu=True,
        upscale=False,
        upscale_model="fake",
        sampler="euler",
        use_lcm=False,
    )
    args.update(kw)
    return longform.LongformJob(**args)


def scene(prompt, frames, motion="pan-right", seed=-1):
    return {
        "prompt": prompt,
        "negative_prompt": "",
        "frames": frames,
        "motion": motion,
        "strength": 0.35,
        "seed": seed,
    }


def test_two_scene_video_end_to_end(studio):
    job = make_job(
        studio, [scene("forest", 7, "pan-right", seed=11), scene("city", 4, "zoom-out")]
    )
    frames, stats = job.run()
    assert [p.name for p in frames] == [f"{i:08d}.png" for i in range(11)]
    assert all(Image.open(p).size == (64, 64) for p in frames)
    src, _t = job.upscale_all(frames)
    out = studio["out"] / "vid1" / "final.mp4"
    job.interpolate_and_encode(src, hold_frames=4, fps=12, out_path=out)
    info = ffprobe(out)
    assert (info["codec_name"], info["width"], info["height"], info["pix_fmt"]) == (
        "h264",
        64,
        64,
        "yuv420p",
    )
    assert int(info["nb_read_frames"]) == (11 - 1) * 4 + 1

    state = json.loads((studio["out"] / "vid1" / "state.json").read_text())
    assert (
        state["status"],
        state["phase"],
        state["completed_frames"],
        state["total_frames"],
    ) == ("done", "done", 11, 11)
    assert state["seeds"][0] == 11 and state["seeds"][1] >= 0
    # one seed per scene, used by every frame of that scene
    seeds = [b["seed"] for b in studio["gpu"].bodies("") + studio["cpu"].bodies("")]
    assert set(seeds) == set(state["seeds"])
    # second scene's anchor is an img2img transition, not a fresh txt2img
    assert len(studio["gpu"].bodies("/txt2img")) == 1
    assert sum(state["backend_counts"].values()) == 11
    assert set(stats) == {"gpu", "cpu"}


def test_cpu_backend_really_takes_frames_when_it_keeps_up(studio):
    job = make_job(studio, [scene("sea", 9, "zoom-in")], anchor_interval=8)
    frames, stats = job.run()
    assert len(frames) == 9
    # with the stub both backends are equally fast, so both get work
    assert stats["cpu"]["frames_done"] >= 1 and stats["gpu"]["frames_done"] >= 1


def test_dead_cpu_server_still_makes_the_video(studio, monkeypatch):
    job = make_job(studio, [scene("sea", 6, "pan-left")], cpu_url="http://127.0.0.1:9")
    frames, stats = job.run()
    assert len(frames) == 6
    assert stats["cpu"]["frames_done"] == 0


def test_motion_reaches_the_frames(studio):
    """The healed frames carry the camera: a pan of a two-colour anchor
    moves the colour boundary."""
    gpu = studio["gpu"]
    job = make_job(
        studio,
        [scene("x", 4, "pan-right")],
        use_cpu=False,
        anchor_weight=0,
        crossfade_frames=0,
    )
    real_txt2img = engine.txt2img

    def split_anchor(**kw):
        real_txt2img(**kw)
        im = Image.new("RGB", (64, 64), (250, 0, 0))
        im.paste((0, 0, 250), (32, 0, 64, 64))
        im.save(kw["out_path"])

    import longform as lf  # pyright: ignore[reportMissingImports]

    lf.engine.txt2img, saved = split_anchor, lf.engine.txt2img
    try:
        frames, _ = job.run()
    finally:
        lf.engine.txt2img = saved

    def edge(p):
        im = Image.open(p).convert("RGB")
        return next(
            x for x in range(64) if im.getpixel((x, 32))[2] > im.getpixel((x, 32))[0]
        )

    edges = [edge(p) for p in frames]
    assert edges[0] == 32 and edges[1] < edges[0] and edges[3] < edges[1], edges
    assert gpu.bodies("/img2img")


def test_single_keyframe_video_holds_the_frame(studio):
    job = make_job(studio, [scene("still", 1, "static")])
    frames, _ = job.run()
    out = studio["out"] / "vid1" / "final.mp4"
    job.interpolate_and_encode(job.frames_dir, hold_frames=6, fps=12, out_path=out)
    assert int(ffprobe(out)["nb_read_frames"]) == 6


def test_upscale_runs_per_keyframe(studio):
    job = make_job(studio, [scene("x", 3, "zoom-in")], upscale=True, upscale_scale=2)
    frames, _ = job.run()
    src, _t = job.upscale_all(frames)
    assert sorted(p.name for p in src.glob("*.png")) == [p.name for p in frames]
    assert Image.open(next(src.glob("*.png"))).size == (128, 128)


def test_crossfade_never_reaches_into_an_older_scene(studio):
    job = make_job(
        studio,
        [
            scene("a", 2, "static", 1),
            scene("b", 1, "static", 2),
            scene("c", 3, "static", 3),
        ],
        crossfade_frames=5,
        anchor_weight=0,
    )
    calls = []
    real = job._apply_crossfades

    def spy(paths, starts):
        calls.append(list(starts))
        return real(paths, starts)

    job._apply_crossfades = spy
    frames, _ = job.run()
    assert calls == [[0, 2, 3]]
    first = Image.open(frames[0]).convert("RGB").getpixel((5, 5))
    anchor_colour = Image.new(
        "RGB", (1, 1), (40 + 1 * 53 % 200, 40 + 97 % 200, 40 + 31 % 200)
    ).getpixel((0, 0))
    # frame 0 is scene a's own anchor: only scene b (1 frame back) may blend into frame 1
    assert first == anchor_colour


def test_cancel_stops_at_the_next_frame(studio):
    studio["gpu"].delay = studio["cpu"].delay = 0.05
    job = make_job(studio, [scene("long", 30, "pan-up")], anchor_interval=2)
    threading.Timer(0.3, longform.request_cancel, args=(job.work_dir,)).start()
    t0 = time.time()
    with pytest.raises(Cancelled):
        job.run()
    assert time.time() - t0 < 3
    state = json.loads(job.state_path.read_text())
    assert state["status"] == "cancelled" and state["completed_frames"] < 30


def test_failure_is_recorded_in_state(studio):
    studio["gpu"].fail_with = studio["cpu"].fail_with = 500
    job = make_job(studio, [scene("x", 3)])
    with pytest.raises(engine.EngineError):
        job.run()
    state = json.loads(job.state_path.read_text())
    assert state["status"] == "failed" and "500" in state["error"]


def test_state_file_is_never_half_written(studio):
    job = make_job(studio, [scene("x", 1)])
    bad = []
    stop = threading.Event()

    def reader():
        while not stop.is_set():
            try:
                json.loads(job.state_path.read_text())
            except json.JSONDecodeError:
                bad.append(1)
            except FileNotFoundError:
                pass

    t = threading.Thread(target=reader)
    t.start()
    for i in range(300):
        job.state["frames"].append({"index": i, "pad": "x" * 200})
        job._save_state()
    stop.set()
    t.join()
    assert bad == []


# -- library -----------------------------------------------------------------


def test_library_thumbnails_for_images_and_videos(studio):
    out = studio["out"]
    (out / "img1").mkdir()
    Image.new("RGB", (1600, 1200), (0, 90, 200)).save(out / "img1" / "final.jpg")
    library.record("img1", "image", "blue", "", {}, "/outputs/img1/final.jpg", 1.0)
    job = make_job(studio, [scene("x", 2, "static")], job_id="vid2")
    frames, _ = job.run()
    job.interpolate_and_encode(job.frames_dir, 2, 12, out / "vid2" / "final.mp4")
    library.record("vid2", "video", "x", "", {}, "/outputs/vid2/final.mp4", 1.0)
    library.record("gone", "image", "gone", "", {}, "/outputs/gone/final.jpg", 1.0)

    rows = {r["id"]: r for r in library.search("")}
    assert rows["img1"]["thumb_url"] == "/outputs/img1/thumb.jpg"
    assert max(Image.open(out / "img1" / "thumb.jpg").size) <= library.THUMB_SIZE
    assert rows["vid2"]["thumb_url"] == "/outputs/vid2/thumb.jpg"
    assert Image.open(out / "vid2" / "thumb.jpg").size == (64, 64)
    assert rows["gone"]["missing"] is True and rows["img1"]["missing"] is False


def test_library_output_path_stays_inside_outputs(studio):
    assert (
        library.output_path("/outputs/a/b.png")
        == (studio["out"] / "a" / "b.png").resolve()
    )
    for url in ("/outputs/../x.png", "/outputs/a/../../x", "/etc/passwd", "", None):
        assert library.output_path(url) is None


def test_library_orphans_lists_failed_job_folders(studio):
    job = make_job(studio, [scene("x", 3)], job_id="fail1")
    studio["gpu"].fail_with = studio["cpu"].fail_with = 500
    with pytest.raises(engine.EngineError):
        job.run()
    assert [o["id"] for o in library.orphans()] == ["fail1"]
    assert (studio["out"] / "fail1").is_dir()  # listed, never deleted


def test_library_closes_its_connections(studio):
    fds = len(os.listdir("/proc/self/fd"))
    for i in range(200):
        library.record(
            f"r{i}", "image", f"cat {i}", "", {}, f"/outputs/r{i}/final.jpg", 1.0
        )
        library.search("cat")
        library.delete(f"r{i}")
    assert len(os.listdir("/proc/self/fd")) <= fds + 2


# -- through the API handlers -------------------------------------------------


@pytest.fixture
def api(studio, monkeypatch):
    import app as studio_app  # pyright: ignore[reportMissingImports]

    mm = studio_app.model_manager
    entry = {
        "steps": 2,
        "cfg_scale": 1.0,
        "sampler": "euler",
        "use_lcm": False,
        "default_width": 64,
        "default_height": 64,
    }
    monkeypatch.setattr(mm, "get_active_id", lambda: "stub-model")
    monkeypatch.setattr(mm, "ensure_running", lambda *a, **k: None)
    monkeypatch.setattr(mm, "get_active_entry", lambda *a, **k: entry)
    return studio_app


def test_api_image_jpg_and_png(api, studio):
    r = api.generate_image(
        api.ImageRequest(
            prompt="a lake", width=64, height=64, upscale=True, upscale_scale=2
        )
    )
    assert r["url"].endswith("final.jpg")
    assert Image.open(studio["out"] / r["id"] / "final.jpg").size == (128, 128)
    r2 = api.generate_image(
        api.ImageRequest(
            prompt="a lake",
            width=64,
            height=64,
            upscale=False,
            output_format="png",
            seed=5,
        )
    )
    assert Image.open(studio["out"] / r2["id"] / "final.png").size == (64, 64)
    found = {row["id"] for row in api.search_library(q="lake", kind="")}
    assert found == {r["id"], r2["id"]}
    served = api.get_output(r["id"], "final.jpg")
    assert Path(served.path) == (studio["out"] / r["id"] / "final.jpg").resolve()
    with pytest.raises(HTTPException):
        api.get_output("..", "library.db")


def test_api_image_batch_uses_both_backends(api, studio):
    r = api.generate_image(
        api.ImageRequest(
            prompt="a lake", width=64, height=64, upscale=False, batch_count=6, seed=10
        )
    )
    assert len(r["batch"]) == 6
    assert sorted(
        b["seed"]
        for b in studio["gpu"].bodies("/txt2img") + studio["cpu"].bodies("/txt2img")
    ) == list(range(10, 16))


def test_api_video_and_delete(api, studio):
    req = api.VideoRequest(
        prompt="a road",
        keyframes=3,
        motion="zoom-in",
        width=64,
        height=64,
        upscale=False,
        hold_frames=2,
        fps=8,
        wait=True,
    )
    r = api.generate_video(req)
    info = ffprobe(studio["out"] / r["id"] / "final.mp4")
    assert int(info["nb_read_frames"]) == (3 - 1) * 2 + 1
    assert api.job_state(r["id"])["status"] == "done"
    assert api.delete_generation(r["id"]) == {"deleted": r["id"]}
    assert not (studio["out"] / r["id"]).exists()
    assert api.search_library(q="road", kind="") == []
