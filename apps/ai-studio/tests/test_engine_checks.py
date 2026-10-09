"""engine.py refuses to report success when a tool wrote nothing, and video
assembly copes with odd frame sizes. The upscaler/RIFE are fake scripts that
exit 0 without output (what the real ones do on bad input); ffmpeg is real."""

import json
import shutil
import subprocess
import sys

import pytest
from PIL import Image

import studio_fakes  # noqa: F401  (puts src/ on the path)
import config  # pyright: ignore[reportMissingImports]
import engine  # pyright: ignore[reportMissingImports]


def _fake_tool(path, body="pass"):
    path.write_text(f"#!{sys.executable}\nimport sys\n{body}\n")
    path.chmod(0o755)
    return path


def test_upscale_that_writes_nothing_is_an_engine_error(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "REALESRGAN_BIN", _fake_tool(tmp_path / "esr"))
    with pytest.raises(engine.EngineError, match="made no picture"):
        engine.upscale(str(tmp_path / "in.png"), str(tmp_path / "out.png"), "m")


def test_upscale_that_writes_an_empty_file_is_an_engine_error(tmp_path, monkeypatch):
    body = "o = sys.argv[sys.argv.index('-o') + 1]\nopen(o, 'wb').close()"
    monkeypatch.setattr(config, "REALESRGAN_BIN", _fake_tool(tmp_path / "esr", body))
    with pytest.raises(engine.EngineError):
        engine.upscale(str(tmp_path / "in.png"), str(tmp_path / "out.png"), "m")


def test_upscale_with_output_passes(tmp_path, monkeypatch):
    body = "o = sys.argv[sys.argv.index('-o') + 1]\nopen(o, 'wb').write(b'png')"
    monkeypatch.setattr(config, "REALESRGAN_BIN", _fake_tool(tmp_path / "esr", body))
    out = tmp_path / "out.png"
    assert engine.upscale(str(tmp_path / "in.png"), str(out), "m") == str(out)


def test_interpolate_refuses_an_empty_folder_without_running_rife(
    tmp_path, monkeypatch
):
    ran = tmp_path / "ran"
    monkeypatch.setattr(
        config, "RIFE_BIN", _fake_tool(tmp_path / "rife", f"open({str(ran)!r}, 'w')")
    )
    (tmp_path / "in").mkdir()
    with pytest.raises(engine.EngineError, match="no frames"):
        engine.interpolate(tmp_path / "in", tmp_path / "out", 5)
    assert not ran.exists()


def test_interpolate_that_makes_too_few_frames_is_an_engine_error(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(config, "RIFE_BIN", _fake_tool(tmp_path / "rife"))
    (tmp_path / "in").mkdir()
    Image.new("RGB", (8, 8)).save(tmp_path / "in" / "00000001.png")
    with pytest.raises(engine.EngineError, match="made 0 of 5"):
        engine.interpolate(tmp_path / "in", tmp_path / "out", 5)


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="needs ffmpeg")
@pytest.mark.parametrize("size", [(65, 63), (64, 64), (33, 80), (1, 1)])
def test_encode_video_pads_odd_sizes(tmp_path, size):
    frames = tmp_path / "f"
    frames.mkdir()
    for i in range(1, 4):
        Image.new("RGB", size, (i * 60, 0, 0)).save(frames / f"{i:08d}.png")
    out = tmp_path / "v.mp4"
    engine.encode_video(frames, out, 8)
    probe = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height",
            "-of",
            "json",
            str(out),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    s = json.loads(probe.stdout)["streams"][0]
    assert (s["width"], s["height"]) == (size[0] + size[0] % 2, size[1] + size[1] % 2)
