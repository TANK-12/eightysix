"""whisper_cpp engine: a cut audio context for short clips, full when it loops."""

import numpy as np

from engines import whisper_cpp as w

FAKE = """#!/bin/sh
echo "$@" >> "{log}"
case "$*" in
  *" -ac "*) echo "{short}" ;;
  *) echo "{full}" ;;
esac
"""


def engine(tmp_path, monkeypatch, short="What time is it?", full="FULL", cut=True):
    log = tmp_path / "calls.log"
    cli = tmp_path / "whisper-cli"
    cli.write_text(FAKE.format(log=log, short=short, full=full))
    cli.chmod(0o755)
    model = tmp_path / "m.bin"
    model.write_bytes(b"x")
    monkeypatch.setenv("FORGE_WHISPER_CLI", str(cli))
    return w.Engine({"short_ctx": cut}, {"model": model}, 4), log


def calls(log):
    return log.read_text().splitlines() if log.exists() else []


def secs(n):
    return np.zeros(int(n * 16000), np.float32)


def test_short_clip_is_read_with_a_cut_context(tmp_path, monkeypatch):
    e, log = engine(tmp_path, monkeypatch)
    assert e.transcribe(secs(1.1)) == "What time is it?"
    (only,) = calls(log)
    assert only.endswith("-ac 512")


def test_a_looping_answer_is_read_again_in_full(tmp_path, monkeypatch):
    loop = "Nor is his manner less interesting. Nor is his manner less interesting."
    e, log = engine(tmp_path, monkeypatch, short=loop, full="Nor is his manner.")
    assert e.transcribe(secs(10)) == "Nor is his manner."
    first, second = calls(log)
    assert first.endswith("-ac 756") and "-ac" not in second


def test_full_context_without_the_flag_or_for_a_long_clip(tmp_path, monkeypatch):
    e, log = engine(tmp_path, monkeypatch, cut=False)
    assert e.transcribe(secs(1)) == "FULL"
    (tmp_path / "b").mkdir()
    e, log2 = engine(tmp_path / "b", monkeypatch)
    assert e.transcribe(secs(25)) == "FULL"
    assert ["-ac" in c for c in calls(log) + calls(log2)] == [False, False]


def test_short_ctx_sizes():
    assert w.short_ctx(1.1) == 512 and w.short_ctx(9.24) == 718
    assert w.short_ctx(40) == 1500


def test_looped():
    assert not w.looped("What time is it?", 1.1)
    assert w.looped("What time is it? What time is it?", 1.1)
    assert not w.looped("Stop. Stop.", 1.0)
    assert w.looped(" ".join(["word"] * 20), 2.0)
    assert not w.looped("Open the files app and then play some music.", 3.0)
