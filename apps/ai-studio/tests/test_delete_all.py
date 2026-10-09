""" "Delete all models": the list it shows, and deleting only what was ticked."""

import pytest

from studio_fakes import entry, put, studio  # noqa: F401
import model_manager  # pyright: ignore[reportMissingImports]


def _part(role, name, size):
    return {
        "role": role,
        "url": "https://x/" + name,
        "filename": name,
        "size_bytes": size,
    }


@pytest.fixture
def setup(studio, monkeypatch):
    tmp = studio.root
    shared_vae = _part("vae", "v.st", 30)
    studio.use(
        [
            entry("a", [_part("checkpoint", "a.safetensors", 100)]),
            entry("b", [_part("checkpoint", "b.safetensors", 200), shared_vae]),
            entry("c", [_part("checkpoint", "c.st", 1)]),
            entry("d", [_part("diffusion", "d.gguf", 40), shared_vae]),
        ],
        default="a",
    )
    monkeypatch.setattr(
        model_manager,
        "EXTRA_MODELS",
        [
            ("lora", "Speed-up add-on", studio.lora, True, "back"),
            ("upscale", "Upscale models", tmp / "models/upscale", False, "keep"),
        ],
    )
    put(studio.legacy / "a.safetensors", 100)  # a pre-rebuild file
    put(studio.parts / "b.safetensors", 200)
    put(studio.parts / "v.st", 30)
    put(studio.parts / "old.gguf.part", 7)
    put(studio.legacy / "old.safetensors.part", 3)
    put(studio.lora / "lcm.safetensors", 10)
    put(tmp / "models/upscale/x4.bin", 5)
    shared = put(tmp / "elsewhere/shared.gguf", 999)
    (studio.parts / "linked.gguf").symlink_to(shared)
    model_manager.set_active_id("b")
    return tmp, studio.fake


def test_plan_lists_every_model_file_with_sizes_and_ticks(setup):
    plan = {i["id"]: i for i in model_manager.delete_all_plan()}
    assert set(plan) == {"model:a", "model:b", "other", "lora", "upscale"}
    assert plan["model:b"]["bytes"] == 230 and plan["model:b"]["active"]
    assert plan["model:a"]["label"] == "A"
    assert plan["other"]["bytes"] == 10  # leftover downloads; the symlink is not listed
    assert [i for i, v in plan.items() if not v["default"]] == ["upscale"]
    assert all("shared" not in f for v in plan.values() for f in v["files"])


def test_delete_all_ticked_removes_them_and_leaves_none_active(setup, studio):
    tmp, fake = setup
    ticked = [i["id"] for i in model_manager.delete_all_plan() if i["default"]]
    got = model_manager.delete_all(ticked)
    assert got["freed_bytes"] == 100 + 230 + 10 + 10
    assert sorted(p.name for p in studio.parts.iterdir()) == ["linked.gguf"]
    assert list(studio.legacy.iterdir()) == []
    assert (tmp / "elsewhere/shared.gguf").stat().st_size == 999
    assert (tmp / "models/upscale/x4.bin").exists()
    assert fake.calls == ["stop"]
    assert model_manager.get_active_id() is None


def test_unknown_ids_are_ignored_and_a_kept_model_stays_active(setup):
    _, fake = setup
    got = model_manager.delete_all(["model:a", "../../etc", "model:zzz"])
    assert got == {"deleted": ["model:a"], "freed_bytes": 100}
    assert fake.calls == []
    assert model_manager.get_active_id() == "b"


def test_deleting_the_active_model_only_switches_to_one_that_is_kept(setup):
    _, fake = setup
    model_manager.delete_all(["model:b"])
    assert fake.calls == ["stop", ("switch", "a")]


def test_a_part_shared_with_a_model_that_stays_is_kept(setup, studio):
    put(studio.parts / "d.gguf", 40)  # d is installed too and shares v.st with b
    got = model_manager.delete_all(["model:b"])
    assert got["freed_bytes"] == 200
    assert (studio.parts / "v.st").exists() and model_manager.is_installed("d")


def test_a_linked_checkpoint_and_its_vae_are_never_listed(setup, studio):
    tmp, _ = setup
    (studio.parts / "b.safetensors").unlink()
    (studio.parts / "b.safetensors").symlink_to(tmp / "elsewhere/shared.gguf")
    plan = {i["id"]: i for i in model_manager.delete_all_plan()}
    assert "model:b" not in plan
    assert all("v.st" not in f for v in plan.values() for f in v["files"])
