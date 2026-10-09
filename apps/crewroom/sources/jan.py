"""Jan's models, from process information only.

Jan runs llama-server as a router (it has --models-preset) that starts one
child llama-server per loaded model. Each child is a character; the router
only says whether Jan is up. Nothing here talks to Jan's HTTP port, so reading
the room can never load, unload or restart a model.
"""

from __future__ import annotations

import os
import re

from context import Context, read_cmdline, read_comm, read_stat

NAME = "jan"
ORDER = 40
PROCESS_NAME = "llama-server"
PAGE_KB = 4

# (proc_dir, pid, start ticks) -> (cpu ticks, wall time) from the previous poll
_previous: dict[tuple[str, int, str], tuple[int, float]] = {}


def arg_value(args: list[str], *flags: str) -> str | None:
    for i, arg in enumerate(args):
        for flag in flags:
            if arg == flag and i + 1 < len(args):
                return args[i + 1]
            if arg.startswith(flag + "="):
                return arg.split("=", 1)[1]
    return None


def model_name(args: list[str]) -> str | None:
    alias = arg_value(args, "--alias", "-a")
    if alias:
        return alias
    path = arg_value(args, "--model", "-m")
    if not path:
        return None
    base = os.path.basename(path)
    if base.lower() in ("model.gguf",):
        return os.path.basename(os.path.dirname(path)) or base
    return re.sub(r"\.gguf$", "", base, flags=re.I)


def short_name(name: str) -> str:
    """Qwen3_5-9B-Q4_K_M -> Qwen3.5 9B: family and size, no quantisation."""
    parts = re.sub(r"(\d)_(\d)", r"\1.\2", name).split("-")
    keep = [parts[0]]
    for part in parts[1:]:
        if re.fullmatch(r"(A?\d+(\.\d+)?[BbMm])", part):
            keep.append(part)
    return " ".join(keep)


def cpu_percent(ctx: Context, pid: int, stat: list[str]) -> float | None:
    """Percent of one core since the last poll; None on the first sight."""
    try:
        ticks = int(stat[11]) + int(stat[12])
    except (IndexError, ValueError):
        return None
    key = (ctx.proc_dir, pid, stat[19] if len(stat) > 19 else "")
    before = _previous.get(key)
    _previous[key] = (ticks, ctx.now)
    if before is None or ctx.now <= before[1]:
        return None
    seconds = (ticks - before[0]) / ctx.clock_ticks
    return round(max(0.0, seconds / (ctx.now - before[1]) * 100), 1)


def collect(ctx: Context) -> dict:
    router = None
    models = []
    try:
        pids = [int(n) for n in os.listdir(ctx.proc_dir) if n.isdigit()]
    except OSError:
        pids = []
    for pid in sorted(pids):
        if read_comm(ctx.proc_dir, pid) != PROCESS_NAME:
            continue
        args = read_cmdline(ctx.proc_dir, pid)
        stat = read_stat(ctx.proc_dir, pid)
        if not stat:
            continue
        if "--models-preset" in args or "--models-dir" in args:
            router = pid
            continue
        name = model_name(args) or f"model {pid}"
        cpu = cpu_percent(ctx, pid, stat)
        try:
            rss_mb = round(int(stat[21]) * PAGE_KB / 1024)
        except (IndexError, ValueError):
            rss_mb = None
        models.append(
            {
                "id": f"jan-{pid}",
                "pid": pid,
                "name": name,
                "short": short_name(name),
                "cpu": cpu,
                "share": (
                    None if cpu is None else round(cpu / max(1, ctx.cpu_count), 1)
                ),
                "rss_mb": rss_mb,
            }
        )
    live = {(ctx.proc_dir, m["pid"]) for m in models}
    for key in [k for k in _previous if (k[0], k[1]) not in live]:
        del _previous[key]
    return {
        "running": router is not None or bool(models),
        "router_pid": router,
        "models": models,
    }
