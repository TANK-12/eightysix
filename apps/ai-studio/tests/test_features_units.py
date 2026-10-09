"""Audit 2026-10-08: camera motion, colour coherence and the GPU+CPU
scheduler, checked as sweeps over every preset / case (no GPU, no model)."""

# PIL's getpixel() is typed as float | tuple | None; these tests read RGB images.
# pyright: reportIndexIssue=false, reportOptionalSubscript=false, reportArgumentType=false

import io
import sys
import threading
import time
from pathlib import Path

import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import motion  # noqa: E402  # pyright: ignore[reportMissingImports]
import hybrid  # noqa: E402  # pyright: ignore[reportMissingImports]

Cancelled, HybridScheduler = hybrid.Cancelled, hybrid.HybridScheduler


def png(img):
    out = io.BytesIO()
    img.save(out, format="PNG")
    return out.getvalue()


def load(data):
    return Image.open(io.BytesIO(data)).convert("RGB")


def bar_image(w=96, h=64):
    """Red frame with a blue vertical bar at x 40-49 and a green horizontal
    bar at y 20-27: nothing in it is near black."""
    img = Image.new("RGB", (w, h), (200, 50, 50))
    img.paste((40, 40, 230), (40, 0, 50, h))
    img.paste((40, 220, 40), (0, 20, w, 28))
    return img


def dark_fraction(img):
    px = img.get_flattened_data()
    return sum(1 for p in px if sum(p) < 60) / len(px)


# -- motion ------------------------------------------------------------------


@pytest.mark.parametrize("name", list(motion.PRESETS))
@pytest.mark.parametrize("size", [(64, 64), (96, 64), (64, 96)])
def test_every_preset_every_step_has_no_black_edges(name, size):
    """Old code: pans left a black strip growing 3% a step (90% black after
    30) and zoom-out raised ValueError. Sweep steps 1-60 and 1-60 chained."""
    src = png(bar_image(*size))
    for steps in range(1, 61):
        out = load(motion.warp(src, name, steps=steps))
        assert out.size == size
        assert dark_fraction(out) == 0.0, (name, steps)
    cur = src
    for i in range(30):
        cur = motion.apply_motion(cur, name)
        assert dark_fraction(load(cur)) == 0.0, (name, "chained", i)


def test_static_and_zero_strength_are_identity():
    src = bar_image()
    for name in motion.PRESETS:
        assert load(motion.warp(png(src), name, strength=0)).tobytes() == src.tobytes()
    assert load(motion.warp(png(src), "static", steps=50)).tobytes() == src.tobytes()


@pytest.mark.parametrize("name, sign", [("pan-right", -1), ("pan-left", 1)])
def test_pan_moves_content_against_the_camera(name, sign):
    w = 100
    src = png(bar_image(w, 64))
    out = load(motion.warp(src, name, steps=5))  # 15 px
    blue = [
        x
        for x in range(w)
        if out.getpixel((x, 5))[2] > 150 and out.getpixel((x, 5))[0] < 100
    ]
    # the bar was 40-49; it moves 15 px the other way (mirror copies may show too)
    assert any(abs(x - (40 + sign * 15)) <= 1 for x in blue), blue
    assert not any(40 <= x <= 49 for x in blue if abs(x - (40 + sign * 15)) > 10)


def test_pan_down_moves_content_up():
    src = png(bar_image(64, 100))
    out = load(motion.warp(src, "pan-down", steps=5))  # 15 px of 100
    green = [y for y in range(100) if out.getpixel((5, y))[1] > 150]
    assert any(abs(y - 5) <= 1 for y in green), green  # bar was at y 20-27


def test_zoom_in_magnifies_and_zoom_out_shrinks():
    src = png(bar_image(100, 100))

    def bar_width(img):
        return sum(
            1
            for x in range(100)
            if img.getpixel((x, 5))[2] > 150 and img.getpixel((x, 5))[0] < 100
        )

    assert bar_width(load(motion.warp(src, "zoom-in", steps=10))) > 12
    assert bar_width(load(motion.warp(src, "zoom-out", steps=10))) < 9


def test_rotation_matches_pillow_direction():
    src = bar_image(100, 100)
    ours = load(motion.warp(png(src), "orbit-cw", steps=10, strength=1.0))
    zoom = motion.camera("orbit-cw", 10)[2]
    ref = src.rotate(6.0, resample=Image.Resampling.BICUBIC)
    ref = ref.resize(
        (100, 100), box=(50 - 50 / zoom, 50 - 50 / zoom, 50 + 50 / zoom, 50 + 50 / zoom)
    )
    diffs = [
        sum(abs(a - b) for a, b in zip(ours.getpixel((x, y)), ref.getpixel((x, y))))
        for x in range(30, 70, 3)
        for y in range(30, 70, 3)
    ]
    assert sum(diffs) / len(diffs) < 40


def test_unknown_motion_is_static():
    src = bar_image()
    assert (
        load(motion.warp(png(src), "spin-wildly", steps=3)).tobytes() == src.tobytes()
    )


def test_color_match_fixes_colour_without_ghosting():
    ref = bar_image(100, 64)
    panned = load(motion.warp(png(ref), "pan-right", steps=8))  # bar moved to x 16-25
    tinted = Image.blend(panned, Image.new("RGB", panned.size, (255, 255, 0)), 0.3)
    fixed = load(motion.color_match(png(tinted), png(ref), 1.0))
    # colours: mean pulled back to the reference's
    from PIL import ImageStat

    want, got, before = (
        ImageStat.Stat(ref).mean,
        ImageStat.Stat(fixed).mean,
        ImageStat.Stat(tinted).mean,
    )
    assert (
        sum(abs(a - b) for a, b in zip(want, got))
        < sum(abs(a - b) for a, b in zip(want, before)) / 3
    )
    # no ghost: the reference's bar position (x 40-49) gets no blue in it
    assert all(fixed.getpixel((x, 5))[2] < 120 for x in range(42, 48))
    assert motion.color_match(png(tinted), png(ref), 0) == png(tinted)


# -- hybrid scheduler ---------------------------------------------------------


def timed(seconds_by_url, log=None, fail_urls=()):
    def make(i):
        def fn(url):
            if url in fail_urls:
                raise RuntimeError(f"down: {url}")
            time.sleep(seconds_by_url[url])
            if log is not None:
                log.append((i, url))
            return i

        return fn

    return make


def sched(use_cpu=True):
    return HybridScheduler(use_cpu=use_cpu, gpu_url="gpu", cpu_url="cpu")


def test_results_in_order_across_many_calls():
    s = sched()
    s.start()
    try:
        make = timed({"gpu": 0.01, "cpu": 0.03})
        for n in (1, 5, 9):
            out = s.run_all([make(i) for i in range(n)])
            assert [r[0] for r in out] == list(range(n))
    finally:
        s.shutdown()


def test_tail_rule_keeps_last_frames_off_the_slow_cpu():
    s = sched()
    s.gpu.avg_seconds, s.cpu.avg_seconds = 0.05, 0.5
    s.start()
    try:
        out = s.run_all([timed({"gpu": 0.05, "cpu": 0.5})(i) for i in range(4)])
    finally:
        s.shutdown()
    # GPU does 4 in 0.2 s, before the CPU could do one: CPU takes none
    assert [w for _r, w, _e in out] == ["gpu"] * 4


def test_cpu_still_helps_with_a_long_queue():
    s = sched()
    s.gpu.avg_seconds, s.cpu.avg_seconds = 0.05, 0.15
    s.start()
    try:
        out = s.run_all([timed({"gpu": 0.05, "cpu": 0.15})(i) for i in range(20)])
    finally:
        s.shutdown()
    workers = [w for _r, w, _e in out]
    assert workers.count("cpu") >= 2 and workers.count("gpu") >= 10


def test_dead_cpu_server_slows_the_job_but_does_not_fail_it():
    s = sched()
    s.cpu.avg_seconds = 0.01  # make the CPU look fast so it grabs work
    s.start()
    try:
        out = s.run_all(
            [timed({"gpu": 0.01, "cpu": 0.01}, fail_urls=("cpu",))(i) for i in range(8)]
        )
    finally:
        s.shutdown()
    assert [r[0] for r in out] == list(range(8))
    assert {w for _r, w, _e in out} == {"gpu"}
    assert s.stats()["cpu"]["retired"] is True


def test_error_on_every_backend_is_raised():
    s = sched()
    s.start()
    try:
        with pytest.raises(RuntimeError, match="down"):
            s.run_all([timed({}, fail_urls=("gpu", "cpu"))(0)])
    finally:
        s.shutdown()


def test_gpu_only_error_is_raised_after_the_rest_finish():
    s = sched(use_cpu=False)
    s.start()
    calls = []

    def bad(_url):
        raise ValueError("bad frame")

    def good(url):
        calls.append(url)
        return 1

    try:
        with pytest.raises(ValueError):
            s.run_all([good, bad, good])
    finally:
        s.shutdown()
    assert len(calls) == 2


def test_cancel_drops_waiting_tasks():
    s = sched(use_cpu=False)
    s.start()
    ran = []

    def slow(url):
        ran.append(url)
        time.sleep(0.1)

    threading.Timer(0.05, s.cancel).start()
    try:
        with pytest.raises(Cancelled):
            s.run_all([slow] * 10)
        with pytest.raises(Cancelled):
            s.run_all([slow])
    finally:
        s.shutdown()
    assert len(ran) <= 2
