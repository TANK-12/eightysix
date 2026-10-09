"""The declarative catalog: schema, plain card text, and the sd command lines
built from parts (no process is started)."""

import re
from pathlib import Path

import pytest

import studio_fakes  # noqa: F401  (puts src/ on the path)
import catalog  # pyright: ignore[reportMissingImports]
import config  # pyright: ignore[reportMissingImports]
import engine_flags  # pyright: ignore[reportMissingImports]
from catalog import CATALOG  # pyright: ignore[reportMissingImports]

# Card words must be plain: no sizes, resolutions, file formats or jargon.
TECHNICAL = re.compile(
    r"\d+\s*(px|gb|mb|b)\b|\d+x\d+|\b(sd1\.5|sdxl|vae|lora|cfg|unet|gguf|"
    r"safetensors|fp8|fp16|bf16|int8|q\d(_k(_[sml])?|_0)?|i2v|t2v|dit|llm|"
    r"text encoder|vram)\b",
    re.I,
)
OLD_FILES = {
    "meinamix-v10": "meinamix_v10.safetensors",
    "meinahentai": "meinahentai.safetensors",
    "counterfeit-v3": "counterfeit_v3.safetensors",
    "realistic-vision-v6": "realisticVisionV60B1_fp16.safetensors",
    "segmind-vega": "segmind-vega.safetensors",
}
SD_ENTRIES = [e for e in CATALOG.values() if e["engine"] in ("sd", "sd-video")]


def test_every_entry_validates_and_has_a_known_kind():
    assert CATALOG, "catalog is empty"
    for e in CATALOG.values():
        catalog.validate(e)
    assert {e["kind"] for e in CATALOG.values()} >= {"image", "video"}


@pytest.mark.parametrize("eid", sorted(CATALOG))
def test_labels_and_blurbs_are_plain_words(eid):
    e = CATALOG[eid]
    assert not TECHNICAL.search(e["label"]), e["label"]
    assert not TECHNICAL.search(e["blurb"]), e["blurb"]


def test_the_old_checkpoints_keep_their_files_and_roles():
    for mid, filename in OLD_FILES.items():
        parts = CATALOG[mid]["parts"]
        assert parts[0]["role"] == "checkpoint"
        assert parts[0]["filename"] == filename
        assert CATALOG[mid]["engine_build"] == "current"
    rv = CATALOG["realistic-vision-v6"]
    assert rv["settings"]["use_lcm"] and {p["role"] for p in rv["parts"]} == {
        "checkpoint",
        "vae",
        "lora",
    }
    assert catalog.DEFAULT_MODEL_ID == "meinamix-v10"


def test_requested_new_models_are_listed_with_their_tiers():
    tiers = {eid: CATALOG[eid]["tier"] for eid in CATALOG}
    for eid in ("z-image-turbo", "flux2-klein-4b", "qwen-image-2.1", "wan2.2-ti2v-5b"):
        assert tiers[eid] == "compact", eid
    for eid in (
        "ideogram-4",
        "z-image-base",
        "flux2-klein-9b",
        "wan2.2-a14b",
        "ltx-2.5",
        "hunyuanvideo-1.5",
        "minimax-h3",
        "minimax-h3-small",
    ):
        assert tiers[eid] == "big", eid


def test_one_filename_always_means_one_download():
    seen = {}
    for e in CATALOG.values():
        for p in e["parts"]:
            assert seen.setdefault(p["filename"], (p["url"], p["size_bytes"])) == (
                p["url"],
                p["size_bytes"],
            )


def test_two_entries_claiming_one_filename_for_different_files_are_refused(
    monkeypatch,
):
    a = {"role": "vae", "url": "https://a/x", "filename": "x.st", "size_bytes": 1}
    b = dict(a, url="https://b/x")
    fake = {
        "image": [studio_fakes.entry("one", [a])],
        "video": [studio_fakes.entry("two", [b], kind="video")],
    }
    monkeypatch.setattr(catalog, "_load", lambda kind: fake.get(kind, []))
    with pytest.raises(ValueError, match="two different files"):
        catalog.build()


def test_a_missing_world_file_is_tolerated(monkeypatch):
    real = catalog.importlib.import_module

    def no_world(name):
        if name == "catalog.world":
            err = ModuleNotFoundError("no world")
            err.name = name
            raise err
        return real(name)

    monkeypatch.setattr(catalog.importlib, "import_module", no_world)
    built = catalog.build()
    assert all(e["kind"] != "world" for e in built.values())
    assert "z-image-turbo" in built


@pytest.mark.parametrize("eid", sorted(e["id"] for e in SD_ENTRIES))
def test_every_sd_role_has_a_flag_and_each_part_is_passed_once(eid):
    e = CATALOG[eid]
    paths = {p["filename"]: Path("/m") / p["filename"] for p in e["parts"]}
    args = engine_flags.part_args(e, paths)
    for p in e["parts"]:
        if p["role"] == "lora":
            continue
        flag = engine_flags.ROLE_FLAGS[p["role"]]
        i = args.index(str(paths[p["filename"]]))
        assert args[i - 1] == flag
    assert len(args) == 2 * sum(p["role"] != "lora" for p in e["parts"])


def test_the_sd15_server_command_is_the_one_it_always_was():
    e = CATALOG["realistic-vision-v6"]
    paths = {p["filename"]: Path("/m") / p["filename"] for p in e["parts"]}
    cmd = engine_flags.server_cmd(e, paths, 1234, engine_flags.GPU_BACKEND, "/lora")
    assert cmd == [
        str(config.BIN_DIR / "sd-server"),
        "-m",
        "/m/realisticVisionV60B1_fp16.safetensors",
        "--vae",
        "/m/vae-ft-mse-840000-ema-pruned.safetensors",
        "--lora-model-dir",
        "/lora",
        "--backend",
        "diffusion=vulkan0,vae=vulkan0,te=vulkan0",
        "--listen-ip",
        "127.0.0.1",
        "--listen-port",
        "1234",
        "--diffusion-conv-direct",
        "--vae-conv-direct",
        "--vae-tiling",
    ]


def test_only_small_opted_in_models_get_the_cpu_server():
    for e in CATALOG.values():
        if e["tier"] == "big" or e["kind"] != "image":
            assert not engine_flags.wants_cpu_helper(e), e["id"]
    assert engine_flags.wants_cpu_helper(CATALOG["meinamix-v10"])
    assert not engine_flags.wants_cpu_helper(CATALOG["z-image-turbo"])


def test_big_and_new_models_offload_weights_to_ram():
    for e in CATALOG.values():
        if e["engine"] in ("sd", "sd-video") and e["engine_build"] == "next":
            assert "--offload-to-cpu" in e["engine_flags"], e["id"]
            assert "--vae-tiling" in e["engine_flags"], e["id"]


def test_qwen_image_uses_the_newer_engine_build():
    assert engine_flags.build_name(CATALOG["qwen-image-2.1"]) == "next"
    nxt = config.ENGINE_BUILDS["next"]
    assert Path(nxt["dir"]) == config.BIN_DIR / "next"


def test_frame_counts_round_up_to_the_model_grid():
    # sweep: every count lands on the grid, never below the request
    for step, offset in ((4, 1), (17, 5)):
        for n in range(1, 200):
            got = engine_flags.round_frames(n, (step, offset))
            assert got >= n and (got - offset) % step == 0
            assert got - n < step or n <= offset
    assert engine_flags.round_frames(33, (4, 1)) == 33
    assert engine_flags.round_frames(50, (17, 5)) == 56
    assert engine_flags.round_frames(7, None) == 7


@pytest.mark.parametrize(
    "eid", sorted(e["id"] for e in SD_ENTRIES if e["engine"] == "sd-video")
)
def test_video_commands_carry_the_entry_settings(eid):
    e = CATALOG[eid]
    paths = {p["filename"]: Path("/m") / p["filename"] for p in e["parts"]}
    cmd = engine_flags.video_cmd(e, paths, "a cat", "/o/raw.webm", init_image="/s.png")
    s = e["settings"]
    assert cmd[0].endswith("/next/sd-cli") and cmd[1:3] == ["-M", "vid_gen"]

    def val(flag):
        return cmd[cmd.index(flag) + 1]

    assert val("-p") == "a cat" and val("-o") == "/o/raw.webm" and val("-i") == "/s.png"
    assert val("--cfg-scale") == str(s["cfg_scale"])
    assert val("-W") == str(s["width"]) and val("-H") == str(s["height"])
    assert int(val("--video-frames")) >= s["frames"]
    if s.get("high_noise"):
        assert val("--high-noise-steps") == str(s["high_noise"]["steps"])
    for flag in e["engine_flags"]:
        assert flag in cmd
