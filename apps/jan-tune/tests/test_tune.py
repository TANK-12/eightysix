import json
import struct
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import tune  # noqa: E402

YML_35B_STYLE = """name: Test 4B
model_path: llamacpp/models/test-4b/model.gguf
embedding: false
# Context. A comment Emerson or a session wrote, which must survive.
ctx_size: 20000
n_gpu_layers: 16
batch_size: 1024
cache_ram: 512
"""
PRESET = """[*]
fit = off
flash-attn = on
cache-type-k = q8_0
cache-type-v = q8_0
threads = 4
"""


def gguf(path: Path, layers: int, experts: int | None = None) -> None:
    def s(x: str) -> bytes:
        return struct.pack("<Q", len(x)) + x.encode()

    kv = [
        s("general.architecture") + struct.pack("<I", 8) + s("qwen35"),
        s("tokenizer.ggml.tokens") + struct.pack("<IIQ", 9, 8, 2) + s("a") + s("bb"),
        s("tokenizer.ggml.scores") + struct.pack("<IIQ", 9, 6, 2) + b"\0" * 8,
        s("qwen35.block_count") + struct.pack("<II", 4, layers),
    ]
    if experts:
        kv.append(s("qwen35.expert_count") + struct.pack("<II", 4, experts))
    path.write_bytes(b"GGUF" + struct.pack("<IQQ", 3, 0, len(kv)) + b"".join(kv))


@pytest.fixture
def jan(tmp_path, monkeypatch):
    d = tmp_path / "jan"
    m = d / "llamacpp/models/test-4b"
    m.mkdir(parents=True)
    (m / "model.yml").write_text(YML_35B_STYLE)
    gguf(m / "model.gguf", 32)
    e = d / "llamacpp/models/embed"
    e.mkdir(parents=True)
    (e / "model.yml").write_text(
        "model_path: llamacpp/models/embed/model.gguf\nembedding: true\n"
    )
    gguf(e / "model.gguf", 6)
    (d / "llamacpp/router.preset.ini").write_text(PRESET)
    monkeypatch.setattr(tune, "JAN_DATA", d)
    monkeypatch.setenv("CREW_HOME", str(tmp_path / "crews"))
    return d


def fake_speed(config):
    """iGPU helps up to 16 layers then hurts; 8 threads fastest; batch 512
    ties on generation (within 3%) but reads prompts faster."""
    ngl = config["n_gpu_layers"]
    gen = 8.0 + (ngl / 4 if ngl <= 16 else (32 - ngl) / 4)
    gen += {4: 0, 6: 0.3, 8: 0.6}[config["threads"]]
    gen += {512: 0.05, 1024: 0.0, 2048: -0.5}[config["batch_size"]]
    prompt = 80.0 + (20 if config["batch_size"] == 512 else 0)
    if config["ubatch_size"] == 128:
        raise RuntimeError("vk out of memory")
    return gen, prompt


def make_tuner(jan, tmp_path, calls=None, **kw):
    def measure_fn(model, config, globals_, repeats, stop):
        if calls is not None:
            calls.append(dict(config))
        gen, prompt = fake_speed(config)
        return [{"gen": gen, "prompt": prompt}] * repeats

    return tune.Tuner(
        tune.find_model("test-4b"),
        interval=0,
        free_idle=False,
        measure_fn=measure_fn,
        wait_fn=lambda m: [],
        sleep=lambda s: None,
        data_dir=tmp_path / "data",
        **kw,
    )


def test_models_are_scanned_with_layers_and_embeddings_skipped(jan):
    models = tune.discover_models()
    assert [m.id for m in models] == ["test-4b"]
    assert models[0].layers == 32 and models[0].moe is False
    assert models[0].settings["ctx_size"] == 20000


def test_moe_models_get_the_cpu_moe_knob(tmp_path):
    p = tmp_path / "moe.gguf"
    gguf(p, 40, experts=256)
    assert tune.gguf_info(p) == {"layers": 40, "experts": 256}


def test_layer_steps_are_quarters_of_the_model():
    m = tune.Model("x", "x", Path("x"), Path("x"), 1, 32, False)
    assert tune._layer_steps(m) == [0, 8, 16, 24, 32]


def test_search_finds_the_fastest_and_uses_the_tie_break(jan, tmp_path):
    result = make_tuner(jan, tmp_path).run()
    assert result["status"] == "done"
    best = result["best"]["config"]
    assert best["n_gpu_layers"] == 16
    assert best["batch_size"] == 512  # tie on generation, faster prompt read
    assert best["threads"] == 4  # threads is Jan-wide: reported, never adopted
    assert result["threads_report"] == {"4": 12.05, "6": 12.35, "8": 12.65}
    errors = [t for t in result["tests"] if t.get("error")]
    assert errors and "out of memory" in errors[0]["error"]


def test_kv_cache_and_context_are_never_varied(jan, tmp_path):
    calls = []
    make_tuner(jan, tmp_path, calls).run()
    for c in calls:
        assert not {"ctx_size", "cache-type-k", "cache-type-v"} & set(c)
    m = tune.find_model("test-4b")
    args = tune.server_args(m, calls[0], tune.jan_globals(), 9999)
    assert args[args.index("--cache-type-k") + 1] == "q8_0"
    assert args[args.index("--cache-type-v") + 1] == "q8_0"
    assert args[args.index("--ctx-size") + 1] == "20000"
    assert args[args.index("--fit") + 1] == "off"


def test_baseline_is_the_models_current_settings(jan):
    m = tune.find_model("test-4b")
    base = tune.baseline(m, tune.jan_globals())
    assert base == {
        "n_gpu_layers": 16,
        "batch_size": 1024,
        "ubatch_size": 512,
        "threads": 4,
    }


def test_apply_writes_only_per_model_keys_and_keeps_the_rest(jan, tmp_path):
    m = tune.find_model("test-4b")
    written = tune.apply(
        m,
        {"n_gpu_layers": 8, "batch_size": 512, "ubatch_size": 256, "threads": 8},
        data_dir=tmp_path / "data",
    )
    assert written == {"n_gpu_layers": 8, "batch_size": 512, "ubatch_size": 256}
    text = m.yml.read_text()
    assert "# Context. A comment Emerson" in text
    assert "ctx_size: 20000" in text and "cache_ram: 512" in text
    assert "n_gpu_layers: 8\n" in text and "ubatch_size: 256\n" in text
    assert "threads" not in text
    assert len(list((tmp_path / "data/backups").iterdir())) == 1


def test_it_waits_while_jan_is_busy(jan, tmp_path):
    answers = [["Jan is working on other-model"], []]
    t = make_tuner(jan, tmp_path)
    seen = []
    t.wait_fn = lambda m: answers.pop(0) if answers else []
    orig = t._set

    def spy(**kw):
        seen.append(kw.get("message"))
        orig(**kw)

    t._set = spy
    assert t.run()["status"] == "done"
    assert "waiting: Jan is working on other-model" in seen


def test_a_stopped_run_resumes_without_repeating_tests(jan, tmp_path):
    calls = []
    t = make_tuner(jan, tmp_path, calls)
    real = t.measure_fn

    def stop_after_three(model, config, g, repeats, stop):
        if len(calls) == 3:
            raise InterruptedError("stopped")
        return real(model, config, g, repeats, stop)

    t.measure_fn = stop_after_three
    assert t.run()["status"] == "stopped"
    saved = json.loads((tmp_path / "data/results/test-4b.json").read_text())
    assert len(saved["tests"]) == 3
    calls2 = []
    again = make_tuner(jan, tmp_path, calls2).run()
    assert again["status"] == "done"
    assert len(calls2) == len(again["tests"]) - 3


def test_blockers_report_busy_jan_claims_and_memory(jan, tmp_path, monkeypatch):
    proc = tmp_path / "proc"

    def fake(pid, ticks):
        d = proc / str(pid)
        d.mkdir(parents=True, exist_ok=True)
        argv = ["llama-server", "--alias", "busy-model"]
        (d / "cmdline").write_bytes(b"\0".join(a.encode() for a in argv))
        fields = ["S"] + ["0"] * 10 + [str(ticks), "0"] + ["0"] * 30
        (d / "stat").write_text(f"{pid} (llama-server) " + " ".join(fields))

    fake(5, 10)
    grow = iter([10, 50])
    real_ticks = tune.forge_jan.cpu_ticks
    monkeypatch.setattr(
        tune.forge_jan,
        "cpu_ticks",
        lambda p: (fake(5, next(grow)), real_ticks(p))[1],
    )
    import crew  # pyright: ignore[reportMissingImports]

    crew.main(["claim", "jan", "someone", "jan:test-4b"])
    meminfo = tmp_path / "meminfo"
    meminfo.write_text("MemTotal: 1 kB\nMemAvailable: 1000 kB\n")
    reasons = tune.blockers(
        tune.find_model("test-4b"), str(proc), sample=0, meminfo=str(meminfo)
    )
    assert any("working on busy-model" in r for r in reasons)
    assert any("test-4b by someone" in r for r in reasons)
    assert any("not enough free memory" in r for r in reasons)


def test_a_finished_run_leaves_a_note_and_no_claim(jan, tmp_path):
    make_tuner(jan, tmp_path).run()
    board = json.loads((tmp_path / "crews/jan/board.json").read_text())
    assert board["claims"] == []
    assert "Tuned test-4b" in board["notes"][-1]["text"]
