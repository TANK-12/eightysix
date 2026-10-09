"""Parts-based install: download (resume, progress, cancel), quote, delete."""

import threading
import time

import pytest

from studio_fakes import (
    entry,
    make_part,
    put,
    server,
    studio,
    wait_download,
)  # noqa: F401
import model_manager  # pyright: ignore[reportMissingImports]

GB = 1024**3


def two_models(server, studio):
    shared = make_part(server, "vae", "shared-vae.st", 3000)
    a = entry("a", [make_part(server, "diffusion", "a.gguf", 5000), shared])
    b = entry("b", [make_part(server, "diffusion", "b.gguf", 7000), shared])
    studio.use([a, b])
    return a, b


def test_download_fetches_every_part_into_the_parts_folder(server, studio):
    two_models(server, studio)
    assert model_manager.start_download("a")["state"] == "running"
    assert wait_download("a") is None  # finished jobs leave no download state
    assert model_manager.is_installed("a")
    assert sorted(p.name for p in studio.parts.iterdir()) == ["a.gguf", "shared-vae.st"]
    assert (studio.parts / "a.gguf").stat().st_size == 5000
    assert model_manager.get_active_id() == "a"  # first image model becomes active


def test_a_shared_part_is_stored_once_and_not_fetched_again(server, studio):
    two_models(server, studio)
    model_manager.start_download("a")
    wait_download("a")
    q = model_manager.quote("b")
    assert (q["total_bytes"], q["needed_bytes"]) == (10000, 7000)
    server.requests.clear()
    model_manager.start_download("b")
    wait_download("b")
    assert [p for p, _ in server.requests] == ["/b.gguf"]
    assert len(list(studio.parts.iterdir())) == 3


def test_resume_sends_a_range_request_and_finishes_the_file(server, studio):
    a, _ = two_models(server, studio)
    studio.parts.mkdir(parents=True)
    (studio.parts / "a.gguf.part").write_bytes(b"x" * 1234)
    assert model_manager.quote("a")["needed_bytes"] == 8000 - 1234
    model_manager.start_download("a")
    wait_download("a")
    assert ("/a.gguf", "bytes=1234-") in server.requests
    assert (studio.parts / "a.gguf").read_bytes() == server.files["/a.gguf"]
    assert not (studio.parts / "a.gguf.part").exists()


def test_a_server_that_ignores_range_restarts_the_file(server, studio):
    two_models(server, studio)
    server.ignore_range = True
    studio.parts.mkdir(parents=True)
    (studio.parts / "a.gguf.part").write_bytes(b"x" * 999)
    model_manager.start_download("a")
    assert wait_download("a") is None
    assert (studio.parts / "a.gguf").stat().st_size == 5000


def test_a_wrong_size_fails_in_plain_words_and_installs_nothing(server, studio):
    bad = make_part(server, "diffusion", "bad.gguf", 100)
    bad["size_bytes"] = 200  # catalog says 200, the server sends 100
    studio.use([entry("bad", [bad])])
    model_manager.start_download("bad")
    got = wait_download("bad")
    assert got["state"] == "failed" and "expected 200" in got["message"]
    assert not model_manager.is_installed("bad")


def test_cancel_keeps_the_part_file_and_a_new_download_resumes(
    server, studio, monkeypatch
):
    monkeypatch.setattr(model_manager, "CHUNK", 1024)  # small reads, so cancel lands
    big = make_part(server, "diffusion", "big.gguf", 50_000)
    studio.use([entry("big", [big])])
    server.gate = threading.Event()  # hold the response after its first chunk
    model_manager.start_download("big")
    deadline = time.time() + 5
    while not (studio.parts / "big.gguf.part").exists() and time.time() < deadline:
        time.sleep(0.01)
    model_manager._jobs["big"].cancel.set()
    server.gate.set()
    got = wait_download("big")
    assert got["state"] == "cancelled"
    left = (studio.parts / "big.gguf.part").stat().st_size
    assert 0 < left < 50_000
    server.gate = None
    model_manager.start_download("big")
    assert wait_download("big") is None
    assert ("/big.gguf", f"bytes={left}-") in server.requests
    assert (studio.parts / "big.gguf").stat().st_size == 50_000


def test_quote_keeps_five_gb_spare(server, studio):
    two_models(server, studio)
    assert model_manager.SPARE_BYTES == 5 * GB
    studio.free[0] = 5 * GB + 8000
    assert model_manager.quote("a")["fits"] is True
    studio.free[0] = 5 * GB + 7999
    q = model_manager.quote("a")
    assert q["fits"] is False and "Delete something first" in q["message"]
    with pytest.raises(model_manager.DownloadError) as e:
        model_manager.start_download("a")
    assert e.value.status == 507


def test_a_second_start_while_running_is_refused(server, studio):
    two_models(server, studio)
    server.gate = threading.Event()
    model_manager.start_download("a")
    with pytest.raises(model_manager.DownloadError) as e:
        model_manager.start_download("a")
    assert e.value.status == 409
    server.gate.set()
    wait_download("a")


def test_gated_parts_need_a_sign_in(server, studio, monkeypatch):
    p = make_part(server, "diffusion", "g.gguf", 10)
    p["gated"] = True
    studio.use([entry("g", [p])])
    monkeypatch.delenv("HF_TOKEN", raising=False)
    with pytest.raises(model_manager.DownloadError) as e:
        model_manager.start_download("g")
    assert e.value.status == 403
    assert model_manager.run_status(model_manager.CATALOG["g"])[0] is False


def test_delete_keeps_parts_another_installed_model_uses(server, studio):
    two_models(server, studio)
    for mid in ("a", "b"):
        model_manager.start_download(mid)
        wait_download(mid)
    freed = model_manager.delete_model("a")
    assert freed == 5000
    assert sorted(p.name for p in studio.parts.iterdir()) == ["b.gguf", "shared-vae.st"]
    assert model_manager.is_installed("b") and not model_manager.is_installed("a")
    assert model_manager.delete_model("b") == 10000
    assert list(studio.parts.iterdir()) == []


def test_delete_ignores_a_shared_part_of_a_model_that_is_not_installed(server, studio):
    two_models(server, studio)
    model_manager.start_download("a")
    wait_download("a")
    # b is not installed (its own file is missing), so the shared part goes
    assert model_manager.delete_model("a") == 8000


def test_delete_removes_unfinished_part_files_too(server, studio):
    two_models(server, studio)
    put(studio.parts / "a.gguf.part", 10)
    assert model_manager.delete_model("a") == 10
    assert not (studio.parts / "a.gguf.part").exists()


def test_old_files_in_the_legacy_folder_still_count_and_are_deleted(server, studio):
    old = make_part(server, "checkpoint", "meinamix_v10.safetensors", 100)
    studio.use([entry("old", [old])], default="old")
    put(studio.legacy / "meinamix_v10.safetensors", 100)
    assert model_manager.is_installed("old")
    assert model_manager.get_active_id() == "old"
    assert model_manager.quote("old")["needed_bytes"] == 0
    assert model_manager.start_download("old") is None
    assert model_manager.delete_model("old") == 100


def test_a_linked_part_is_used_but_never_deleted(server, studio):
    p = make_part(server, "diffusion", "linked.gguf", 50)
    studio.use([entry("l", [p])])
    target = put(studio.root / "elsewhere" / "linked.gguf", 50)
    studio.parts.mkdir(parents=True)
    (studio.parts / "linked.gguf").symlink_to(target)
    assert model_manager.is_installed("l")
    assert model_manager.delete_model("l") == 0
    assert target.exists()


def test_lora_parts_go_to_the_lora_folder(server, studio):
    lora = make_part(server, "lora", "lcm.safetensors", 64)
    studio.use([entry("r", [make_part(server, "checkpoint", "r.st", 32), lora])])
    model_manager.start_download("r")
    wait_download("r")
    assert (studio.lora / "lcm.safetensors").is_file()
    assert (studio.parts / "r.st").is_file()
