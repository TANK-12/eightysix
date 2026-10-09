"""Find the fastest Jan settings for one model by measuring, not guessing.

A test starts a scratch llama-server from Jan's own Vulkan build on a spare
port (never Jan's own instance), sends one fixed ~1,500-token prompt, asks for
128 tokens, and reads llama.cpp's own timings. The search starts from the
model's current settings and tunes one knob at a time, holding the others at
the best found so far. The winner is the fastest generation; within 3%, the
faster prompt read breaks the tie.

Two things are never varied, on Emerson's instruction: the KV cache type
(copied from Jan's own preset, q8_0, because lower costs answer quality) and
the context size (copied from the model's model.yml; he and the apps set it).

Knobs live in KNOBS. Adding one is one entry there. A knob with apply=False
(threads, which is Jan-wide and not per model) is measured last on the winner
and only reported.

  python tune.py                     list the models
  python tune.py MODEL [--apply]     tune one, optionally write the winner
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import socket
import struct
import subprocess
import sys
import threading
import time
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parent
SHARED_DIR = Path(os.environ.get("FORGE_SHARED_DIR") or ROOT.parent.parent / "shared")
CREW_DIR = Path(os.environ.get("CREW_SKILL_DIR") or Path.home() / ".claude/skills/crew")
sys.path.insert(0, str(SHARED_DIR))
sys.path.insert(0, str(CREW_DIR))

import forge_jan  # noqa: E402

JAN_DATA = Path(
    os.environ.get("JAN_DATA_DIR") or Path.home() / ".var/app/ai.jan.Jan/data/Jan/data"
)
DATA_DIR = Path(os.environ.get("JAN_TUNE_DATA") or ROOT / "data")
BOARD_NAME = "jan-tune"
TIE = 0.03  # generation speeds within 3% count as a tie
RAM_MARGIN = 1.5 * 1024**3  # this laptop has no swap
N_PREDICT = 128


# --- knobs -------------------------------------------------------------------


def _layer_steps(model: "Model") -> list:
    n = model.layers or 32
    return sorted({0, round(n * 0.25), round(n * 0.5), round(n * 0.75), n})


@dataclass(frozen=True)
class Knob:
    name: str  # model.yml key
    flag: str  # llama-server flag
    values: Callable[["Model"], list]
    apply: bool = True  # False: Jan-wide, measured and reported only
    when: Callable[["Model"], bool] = lambda m: True


KNOBS: list[Knob] = [
    Knob("n_gpu_layers", "--n-gpu-layers", _layer_steps),
    Knob("batch_size", "--batch-size", lambda m: [512, 1024, 2048]),
    Knob("ubatch_size", "--ubatch-size", lambda m: [128, 256, 512]),
    Knob("cpu_moe", "--cpu-moe", lambda m: [False, True], when=lambda m: m.moe),
    Knob("threads", "--threads", lambda m: [4, 6, 8], apply=False),
]
KNOB_BY_NAME = {k.name: k for k in KNOBS}
# llama-server's own defaults, for keys a model.yml leaves out.
SERVER_DEFAULTS = {"batch_size": 2048, "ubatch_size": 512, "cpu_moe": False}


# --- models ------------------------------------------------------------------


@dataclass
class Model:
    id: str
    name: str
    path: Path
    yml: Path
    size: int
    layers: int | None
    moe: bool
    settings: dict = field(default_factory=dict)


def read_yml(path: Path) -> dict:
    """model.yml is flat `key: value`; comments and blank lines are skipped."""
    out: dict = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith("#") or ":" not in line:
            continue
        if line[0] in " \t-":
            continue
        key, _, raw = line.partition(":")
        raw = raw.split(" #")[0].strip()
        if raw in ("true", "false"):
            out[key.strip()] = raw == "true"
        else:
            try:
                out[key.strip()] = int(raw)
            except ValueError:
                out[key.strip()] = raw
    return out


_GGUF_SIZES = {0: 1, 1: 1, 2: 2, 3: 2, 4: 4, 5: 4, 6: 4, 7: 1, 10: 8, 11: 8, 12: 8}
_GGUF_FMT = {0: "<B", 1: "<b", 2: "<H", 3: "<h", 4: "<I", 5: "<i", 6: "<f"}
_GGUF_FMT.update({7: "<?", 10: "<Q", 11: "<q", 12: "<d"})


def gguf_info(path: Path) -> dict:
    """Layer count and expert count from a GGUF header (metadata only)."""
    found: dict = {}
    with open(path, "rb") as f:
        if f.read(4) != b"GGUF":
            return found
        f.read(4)
        _tensors, n_kv = struct.unpack("<QQ", f.read(16))

        def string() -> str:
            (n,) = struct.unpack("<Q", f.read(8))
            return f.read(n).decode(errors="replace")

        def value(t: int):
            if t == 8:
                return string()
            if t == 9:
                et, n = struct.unpack("<IQ", f.read(12))
                if et in _GGUF_SIZES:
                    f.seek(_GGUF_SIZES[et] * n, 1)
                else:
                    for _ in range(n):
                        value(et)
                return None
            return struct.unpack(_GGUF_FMT[t], f.read(_GGUF_SIZES[t]))[0]

        for _ in range(n_kv):
            key = string()
            (t,) = struct.unpack("<I", f.read(4))
            v = value(t)
            if key.endswith(".block_count"):
                found["layers"] = v
            elif key.endswith(".expert_count"):
                found["experts"] = v
    return found


def discover_models(jan_data: Path | None = None) -> list[Model]:
    base = jan_data or JAN_DATA
    out = []
    for yml in sorted((base / "llamacpp/models").glob("*/model.yml")):
        s = read_yml(yml)
        if s.get("embedding"):
            continue
        path = base / str(s.get("model_path", ""))
        if not path.is_file():
            continue
        try:
            info = gguf_info(path)
        except (OSError, struct.error, KeyError):
            info = {}
        out.append(
            Model(
                id=yml.parent.name,
                name=str(s.get("name") or yml.parent.name),
                path=path,
                yml=yml,
                size=path.stat().st_size,
                layers=info.get("layers"),
                moe=bool(info.get("experts")),
                settings=s,
            )
        )
    return out


def find_model(model_id: str, jan_data: Path | None = None) -> Model:
    for m in discover_models(jan_data):
        if m.id == model_id:
            return m
    raise KeyError(f"no Jan model called {model_id}")


def jan_globals(jan_data: Path | None = None) -> dict:
    """The [*] section of Jan's router preset: cache type, threads, flash-attn."""
    preset = (jan_data or JAN_DATA) / "llamacpp/router.preset.ini"
    out = {"cache-type-k": "q8_0", "cache-type-v": "q8_0", "threads": 4}
    out["flash-attn"] = "on"
    section = None
    try:
        lines = preset.read_text(encoding="utf-8").splitlines()
    except OSError:
        return out
    for line in lines:
        line = line.strip()
        if line.startswith("["):
            section = line
        elif section == "[*]" and "=" in line:
            k, _, v = line.partition("=")
            out[k.strip()] = int(v) if v.strip().isdigit() else v.strip()
    return out


def baseline(model: Model, globals_: dict) -> dict:
    s = model.settings
    config = {
        "n_gpu_layers": min(int(s.get("n_gpu_layers", model.layers or 99)), 999),
        "batch_size": s.get("batch_size", SERVER_DEFAULTS["batch_size"]),
        "ubatch_size": s.get("ubatch_size", SERVER_DEFAULTS["ubatch_size"]),
        "threads": globals_.get("threads", 4),
    }
    if model.moe:
        config["cpu_moe"] = bool(s.get("cpu_moe", False))
    if model.layers:
        config["n_gpu_layers"] = min(config["n_gpu_layers"], model.layers)
    return config


# --- one measurement ---------------------------------------------------------


def backend_bin(jan_data: Path | None = None) -> Path:
    found = sorted(
        (jan_data or JAN_DATA).glob(
            "llamacpp/backends/*/linux-vulkan-x64/build/bin/llama-server"
        )
    )
    if not found:
        raise FileNotFoundError("Jan's Vulkan llama-server was not found")
    return found[-1]


def prompt_text() -> str:
    """A fixed prompt of about 1,500 tokens. Its content does not matter for
    speed, only that it is identical in every test."""
    para = (
        "Section {n}. The forge keeps a ledger of every blade it tempers: the "
        "steel, the heat, the quench, the hours at the anvil, and who asked "
        "for it. Apprentices copy the ledger each evening so that nothing is "
        "lost if the workshop burns. The master reads the copies at dawn and "
        "marks any figure that disagrees with the original in red ink.\n"
    )
    body = "".join(para.format(n=i) for i in range(1, 25))
    return body + "\nSummarise the ledger rules above in one paragraph."


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def server_args(model: Model, config: dict, globals_: dict, port: int) -> list[str]:
    args = [
        "--model",
        str(model.path),
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
        "--no-webui",
        "--parallel",
        "1",
        "--fit",
        "off",
        "--no-mmproj",
        "--ctx-size",
        str(model.settings.get("ctx_size", 8192)),
        "--cache-type-k",
        str(globals_.get("cache-type-k", "q8_0")),
        "--cache-type-v",
        str(globals_.get("cache-type-v", "q8_0")),
        "--flash-attn",
        str(globals_.get("flash-attn", "on")),
    ]
    for name, value in config.items():
        knob = KNOB_BY_NAME[name]
        if isinstance(value, bool):
            if value:
                args.append(knob.flag)
        else:
            args += [knob.flag, str(value)]
    return args


def _post(url: str, body: dict, timeout: float) -> dict:
    req = urllib.request.Request(
        url, json.dumps(body).encode(), {"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def measure(
    model: Model,
    config: dict,
    globals_: dict,
    repeats: int,
    stop: threading.Event,
    log: Path | None = None,
) -> list[dict]:
    """Start a scratch server with `config`, time `repeats` requests, stop it."""
    binary = backend_bin()
    port = free_port()
    env = {**os.environ, "LD_LIBRARY_PATH": str(binary.parent)}
    out = open(log, "ab") if log else subprocess.DEVNULL
    proc = subprocess.Popen(
        [str(binary), *server_args(model, config, globals_, port)],
        env=env,
        stdout=out,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    try:
        deadline = time.time() + 300
        while True:
            if proc.poll() is not None:
                raise RuntimeError(f"llama-server exited with {proc.returncode}")
            if stop.is_set():
                raise InterruptedError("stopped")
            try:
                with urllib.request.urlopen(
                    f"http://127.0.0.1:{port}/health", timeout=2
                ) as r:
                    if r.status == 200:
                        break
            except OSError:
                pass
            if time.time() > deadline:
                raise TimeoutError("llama-server did not load in 5 minutes")
            time.sleep(0.5)
        runs = []
        for _ in range(repeats):
            if stop.is_set():
                raise InterruptedError("stopped")
            t = _post(
                f"http://127.0.0.1:{port}/completion",
                {
                    "prompt": prompt_text(),
                    "n_predict": N_PREDICT,
                    "cache_prompt": False,
                    "temperature": 0,
                    "ignore_eos": True,
                },
                timeout=900,
            )["timings"]
            runs.append(
                {
                    "gen": round(t["predicted_per_second"], 2),
                    "prompt": round(t["prompt_per_second"], 1),
                    "prompt_tokens": t.get("prompt_n"),
                }
            )
        return runs
    finally:
        try:
            os.killpg(proc.pid, signal.SIGTERM)
            proc.wait(timeout=20)
        except (ProcessLookupError, subprocess.TimeoutExpired):
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        if log and not isinstance(out, int):
            out.close()


# --- is it safe to test right now? --------------------------------------------


def mem_available(meminfo: str = "/proc/meminfo") -> int:
    with open(meminfo, encoding="utf-8") as f:
        for line in f:
            if line.startswith("MemAvailable:"):
                return int(line.split()[1]) * 1024
    return 0


def board_claims(crew_home: Path | None = None) -> list[dict]:
    """Live jan: claims on the crew board, read without taking the lock."""
    root = crew_home or Path(os.environ.get("CREW_HOME", Path.home() / ".claude/crew"))
    try:
        board = json.loads((root / "jan" / "board.json").read_text())
    except (OSError, ValueError):
        return []
    stale_after = float(os.environ.get("CREW_STALE_HOURS", "4")) * 3600
    live = []
    for c in board.get("claims", []):
        seen = board.get("members", {}).get(c["owner"], {}).get("last_seen", 0)
        if (
            c["path"].startswith("jan:")
            and c["owner"] != BOARD_NAME
            and time.time() - seen <= stale_after
        ):
            live.append(c)
    return live


def blockers(
    model: Model, proc_dir: str = "/proc", sample: float = 2.0, meminfo: str = ""
) -> list[str]:
    """Reasons not to start a test now. Empty means go."""
    reasons = []
    before = forge_jan.cpu_ticks(proc_dir)
    if before:
        time.sleep(sample)
        after = forge_jan.cpu_ticks(proc_dir)
        busy = [m for m, t in after.items() if before.get(m) not in (None, t)]
        if busy:
            reasons.append("Jan is working on " + ", ".join(busy))
    claims = board_claims()
    if claims:
        reasons.append(
            "claimed on the jan board: "
            + ", ".join(f"{c['path'][4:]} by {c['owner']}" for c in claims)
        )
    need = model.size + RAM_MARGIN
    have = mem_available(meminfo or "/proc/meminfo")
    if have < need:
        reasons.append(
            f"not enough free memory ({have / 1024**3:.1f} GB free, "
            f"{need / 1024**3:.1f} GB needed)"
        )
    return reasons


def free_idle_jan_models(proc_dir: str = "/proc") -> list[str]:
    """Unload Jan models nobody is using, so the iGPU numbers are clean."""
    claimed = {c["path"][4:] for c in board_claims()}
    freed = []
    for m in forge_jan.loaded_models(proc_dir):
        if m not in claimed and forge_jan.release(m, proc_dir):
            freed.append(m)
    return freed


# --- the board ---------------------------------------------------------------


def _board(fn: Callable) -> None:
    """Run fn(crew_module, board) on the jan board; never fail a tuning run."""
    try:
        import crew  # pyright: ignore[reportMissingImports]

        with crew.open_board("jan") as b:
            crew.touch(b, BOARD_NAME)
            fn(crew, b)
    except Exception:
        pass


def board_claim(model_id: str) -> None:
    _board(lambda c, b: c.claim_paths(b, BOARD_NAME, [f"jan:{model_id}"], False))


def board_release() -> None:
    _board(lambda c, b: c.release_paths(b, BOARD_NAME, []))


def board_post(text: str) -> None:
    def post(c, b):
        c.cmd_post(b, c.parser().parse_args(["post", "jan", BOARD_NAME, text]))

    _board(post)


# --- the search --------------------------------------------------------------


def config_key(config: dict) -> str:
    return json.dumps(config, sort_keys=True)


def better(a: dict, b: dict | None) -> bool:
    """Is result a faster than b? Generation first; within 3%, prompt read."""
    if b is None or b.get("gen") is None:
        return a.get("gen") is not None
    if a.get("gen") is None:
        return False
    if abs(a["gen"] - b["gen"]) <= TIE * max(a["gen"], b["gen"]):
        return a["prompt"] > b["prompt"]
    return a["gen"] > b["gen"]


def median(xs: list[float]) -> float:
    s = sorted(xs)
    mid = len(s) // 2
    return s[mid] if len(s) % 2 else (s[mid - 1] + s[mid]) / 2


class Tuner:
    """One tuning run. `measure_fn` and `wait_fn` are swappable for tests."""

    def __init__(
        self,
        model: Model,
        repeats: int = 2,
        interval: float = 10.0,
        knobs: dict[str, list] | None = None,
        free_idle: bool = True,
        measure_fn: Callable | None = None,
        wait_fn: Callable[[Model], list[str]] | None = None,
        sleep: Callable[[float], None] = time.sleep,
        data_dir: Path | None = None,
    ):
        self.model = model
        self.repeats = max(1, repeats)
        self.interval = max(0.0, interval)
        self.overrides = knobs or {}
        self.free_idle = free_idle
        self.measure_fn = measure_fn or measure
        self.wait_fn = wait_fn or blockers
        self.sleep = sleep
        self.stop = threading.Event()
        self.globals = jan_globals()
        self.dir = (data_dir or DATA_DIR) / "results"
        self.path = self.dir / f"{model.id}.json"
        self.state = self._load()
        self.lock = threading.Lock()

    # results file ------------------------------------------------------------

    def _load(self) -> dict:
        try:
            old = json.loads(self.path.read_text())
        except (OSError, ValueError):
            old = {}
        return {
            "model": self.model.id,
            "name": self.model.name,
            "layers": self.model.layers,
            "moe": self.model.moe,
            "jan": {k: self.globals.get(k) for k in ("cache-type-k", "threads")},
            "ctx_size": self.model.settings.get("ctx_size"),
            # a run that was stopped, failed or cut off by a crash resumes
            "status": (
                "stopped"
                if old.get("status") in ("running", "stopped", "failed")
                else old.get("status", "idle")
            ),
            "message": "",
            "tests": old.get("tests", []),
            "best": old.get("best"),
            "baseline": old.get("baseline"),
            "threads_report": old.get("threads_report"),
            "planned": 0,
            "started": None,
            "finished": old.get("finished"),
        }

    def _save(self) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.state, indent=1))
        tmp.replace(self.path)

    def _set(self, **kw) -> None:
        with self.lock:
            self.state.update(kw)
            self._save()

    def snapshot(self) -> dict:
        with self.lock:
            return json.loads(json.dumps(self.state))

    # searching ---------------------------------------------------------------

    def knob_values(self, knob: Knob) -> list:
        return list(self.overrides.get(knob.name) or knob.values(self.model))

    def active_knobs(self) -> list[Knob]:
        return [
            k
            for k in KNOBS
            if k.when(self.model) and (not self.overrides or k.name in self.overrides)
        ]

    def _cached(self, config: dict) -> dict | None:
        key = config_key(config)
        for t in self.state["tests"]:
            if t["key"] == key and t.get("repeats") == self.repeats:
                return t
        return None

    def test(self, config: dict, knob: str) -> dict:
        hit = self._cached(config)
        if hit:
            return hit
        while True:
            if self.stop.is_set():
                raise InterruptedError("stopped")
            reasons = self.wait_fn(self.model)
            if not reasons:
                break
            self._set(message="waiting: " + "; ".join(reasons))
            self.sleep(15)
        self._set(message=f"testing {knob} = {config.get(knob)}", current=config)
        result = {"key": config_key(config), "config": config, "knob": knob}
        result["repeats"] = self.repeats
        try:
            runs = self.measure_fn(
                self.model, config, self.globals, self.repeats, self.stop
            )
            result["runs"] = runs
            result["gen"] = round(median([r["gen"] for r in runs]), 2)
            result["prompt"] = round(median([r["prompt"] for r in runs]), 1)
        except InterruptedError:
            raise
        except Exception as e:  # a setting that does not load is a result too
            result["error"] = str(e)[:300]
            result["gen"] = None
        with self.lock:
            self.state["tests"].append(result)
            self._save()
        if self.interval:
            self.sleep(self.interval)
        return result

    def run(self) -> dict:
        resume = self.state["status"] == "stopped"
        self._set(
            status="running",
            started=time.time(),
            message="resuming" if resume else "starting",
            tests=self.state["tests"] if resume else [],
            best=None,
            threads_report=None,
        )
        board_claim(self.model.id)
        try:
            if self.free_idle:
                freed = free_idle_jan_models()
                if freed:
                    self._set(message="freed idle Jan models: " + ", ".join(freed))
            best_cfg = baseline(self.model, self.globals)
            knobs = self.active_knobs()
            applied = [k for k in knobs if k.apply]
            reported = [k for k in knobs if not k.apply]
            self._set(
                baseline=best_cfg,
                planned=1 + sum(len(self.knob_values(k)) for k in knobs),
            )
            best = self.test(best_cfg, "baseline")
            for knob in applied:
                for v in self.knob_values(knob):
                    cfg = {**best_cfg, knob.name: v}
                    r = self.test(cfg, knob.name)
                    if better(r, best):
                        best, best_cfg = r, cfg
                self._set(best=best)
            report = {}
            for knob in reported:
                for v in self.knob_values(knob):
                    r = self.test({**best_cfg, knob.name: v}, knob.name)
                    report[str(v)] = r.get("gen")
            self._set(
                status="done",
                best=best,
                threads_report=report or None,
                finished=time.time(),
                message="done",
                current=None,
            )
            if best and best.get("gen"):
                board_post(
                    f"Tuned {self.model.id}: fastest is {best['gen']} tok/s "
                    f"generation, {best['prompt']} tok/s prompt, with "
                    f"{summary(best['config'])}. Apply it from the Jan Tune app."
                )
        except InterruptedError:
            self._set(status="stopped", message="stopped", current=None)
        except Exception as e:
            self._set(status="failed", message=str(e)[:300], current=None)
        finally:
            board_release()
        return self.snapshot()


def summary(config: dict) -> str:
    return ", ".join(f"{k} {v}" for k, v in config.items())


# --- applying the winner -----------------------------------------------------


def apply(model: Model, config: dict, data_dir: Path | None = None) -> dict:
    """Write the per-model winners into model.yml; back it up first. Only
    knobs with apply=True are written; cache type and ctx are left alone."""
    backups = (data_dir or DATA_DIR) / "backups"
    backups.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    shutil.copy2(model.yml, backups / f"{model.id}-{stamp}.yml")
    wanted = {
        k: v for k, v in config.items() if k in KNOB_BY_NAME and KNOB_BY_NAME[k].apply
    }
    lines = model.yml.read_text(encoding="utf-8").splitlines()
    done = set()
    for i, line in enumerate(lines):
        key = line.partition(":")[0].strip()
        if key in wanted and line[:1] not in " \t#-":
            lines[i] = f"{key}: {_yml(wanted[key])}"
            done.add(key)
    lines += [f"{k}: {_yml(v)}" for k, v in wanted.items() if k not in done]
    model.yml.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return wanted


def _yml(v) -> str:
    return ("true" if v else "false") if isinstance(v, bool) else str(v)


# --- command line ------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Find the fastest Jan settings.")
    p.add_argument("model", nargs="?")
    p.add_argument("--repeats", type=int, default=2)
    p.add_argument("--interval", type=float, default=10)
    p.add_argument("--keep-jan-models", action="store_true")
    p.add_argument("--apply", action="store_true")
    a = p.parse_args(argv)
    if not a.model:
        for m in discover_models():
            print(f"{m.id}  ({m.layers} layers{', MoE' if m.moe else ''})")
        return 0
    tuner = Tuner(
        find_model(a.model),
        repeats=a.repeats,
        interval=a.interval,
        free_idle=not a.keep_jan_models,
    )
    shown = 0

    def watch():
        nonlocal shown
        while not tuner.stop.wait(3):
            s = tuner.snapshot()
            for t in s["tests"][shown:]:
                gen = t.get("gen")
                print(
                    f"{t['knob']:>12}  {summary(t['config'])}  ->  "
                    + (f"{gen} gen, {t['prompt']} prompt" if gen else t["error"]),
                    flush=True,
                )
            shown = len(s["tests"])

    threading.Thread(target=watch, daemon=True).start()
    result = tuner.run()
    tuner.stop.set()
    print(f"status: {result['status']}  {result['message']}")
    best = result.get("best")
    if best and best.get("gen"):
        print(
            f"best: {summary(best['config'])}  {best['gen']} gen, {best['prompt']} prompt"
        )
        if result.get("threads_report"):
            print(f"threads (Jan-wide, not applied): {result['threads_report']}")
        if a.apply:
            print("applied:", apply(tuner.model, best["config"]))
    return 0 if result["status"] == "done" else 1


if __name__ == "__main__":
    sys.exit(main())
