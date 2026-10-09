"""Lower the CPU scheduling priority of processes marked as background,
never touching ones marked as protected. Config is edited from the Power
tab and applied continuously by priority_watch.py (a user service, so
lowering your own processes' niceness needs no root)."""

from __future__ import annotations

import json
import os
import subprocess

CONFIG_PATH = os.path.expanduser("~/.config/forge-power/priority.json")
PRESETS_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "background_presets.json"
)
DEFAULT = {"nice": 10, "background": ["claude"], "protected": []}
NICE_RANGE = (1, 19)
ECORES_PATH = "/sys/devices/cpu_atom/cpus"


def load_presets(path: str = PRESETS_PATH) -> list[dict]:
    """Suggested Background groups from background_presets.json."""
    try:
        with open(path, encoding="utf-8") as handle:
            groups = json.load(handle)["groups"]
    except (OSError, ValueError, KeyError, TypeError):
        return []
    return [
        g
        for g in groups
        if isinstance(g, dict)
        and isinstance(g.get("name"), str)
        and isinstance(g.get("patterns"), list)
        and all(isinstance(p, str) and p for p in g["patterns"])
    ]


def preset_patterns(groups: list[dict]) -> list[str]:
    out: list[str] = []
    for group in groups:
        out.extend(p for p in group["patterns"] if p not in out)
    return out


def _default() -> dict:
    cfg = {k: list(v) if isinstance(v, list) else v for k, v in DEFAULT.items()}
    cfg["background"] += [
        p for p in preset_patterns(load_presets()) if p not in cfg["background"]
    ]
    return cfg


def load_config(path: str = CONFIG_PATH) -> dict:
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return _default()
    return data if _is_valid(data) else _default()


def _is_valid(cfg: object) -> bool:
    if not isinstance(cfg, dict) or set(cfg) != set(DEFAULT):
        return False
    lo, hi = NICE_RANGE
    if type(cfg["nice"]) is not int or not lo <= cfg["nice"] <= hi:
        return False
    for key in ("background", "protected"):
        value = cfg[key]
        if not isinstance(value, list) or not all(
            isinstance(p, str) and p for p in value
        ):
            return False
    if set(cfg["background"]) & set(cfg["protected"]):
        return False
    return True


def save_config(path: str, cfg: dict) -> None:
    if not _is_valid(cfg):
        raise ValueError(
            "priority config needs: nice (int 1-19), background (list of "
            "non-empty strings), protected (list of non-empty strings), "
            "with no pattern in both lists"
        )
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(cfg, handle)
    os.replace(tmp, path)


def matches(name: str, patterns: list[str]) -> bool:
    lowered = name.lower()
    return any(pattern.lower() in lowered for pattern in patterns)


def parse_cpus(text: str) -> set[int]:
    """A kernel CPU list such as "0,4-11" as a set of CPU numbers."""
    cpus: set[int] = set()
    for part in text.strip().split(","):
        if "-" in part:
            lo, hi = part.split("-")
            cpus.update(range(int(lo), int(hi) + 1))
        elif part:
            cpus.add(int(part))
    return cpus


def squeeze_for(mode: dict, ecores_path: str = ECORES_PATH) -> dict | None:
    """What a mode's optional `background_tasks` block asks for: a nice level
    and, when efficiency_cores_only is set and the CPU has them, those cores."""
    block = mode.get("background_tasks")
    if not block:
        return None
    out: dict = {"nice": block["nice"]}
    if block.get("efficiency_cores_only"):
        try:
            with open(ecores_path, encoding="ascii") as handle:
                cpus = parse_cpus(handle.read())
        except (OSError, ValueError):
            cpus = set()
        if cpus:
            out["cpus"] = cpus
    return out


def plan(cfg: dict, processes: list[dict], squeeze: dict | None = None) -> list[dict]:
    nice = max(cfg["nice"], squeeze["nice"]) if squeeze else cfg["nice"]
    out = []
    for proc in processes:
        name = proc["name"]
        if matches(name, cfg["background"]) and not matches(name, cfg["protected"]):
            entry = {"pid": proc["pid"], "name": name, "nice": nice}
            if squeeze and "cpus" in squeeze:
                entry["cpus"] = squeeze["cpus"]
            out.append(entry)
    return out


def all_processes() -> list[dict]:
    # Only our own processes: the watcher runs unprivileged, so renicing
    # anyone else's would just fail every cycle.
    proc = subprocess.run(
        ["ps", "-u", str(os.getuid()), "-o", "pid=,comm="],
        capture_output=True,
        text=True,
        timeout=10,
    )
    rows = []
    for line in proc.stdout.splitlines():
        parts = line.split(maxsplit=1)
        if len(parts) == 2 and parts[0].isdigit():
            rows.append({"pid": int(parts[0]), "name": parts[1]})
    return rows


def _default_run(pid: int, nice: int, cpus: set[int] | None = None) -> None:
    if cpus is not None and os.sched_getaffinity(pid) != cpus:
        os.sched_setaffinity(pid, cpus)
    # Already this low (or lower): nothing to do, and an unprivileged process
    # could not raise it back anyway. This also keeps ionice from being spawned
    # for every matching process every cycle.
    if os.getpriority(os.PRIO_PROCESS, pid) >= nice:
        return
    os.setpriority(os.PRIO_PROCESS, pid, nice)
    subprocess.run(
        ["ionice", "-c", "3", "-p", str(pid)],
        capture_output=True,
        timeout=5,
        check=False,
    )


def unpin(pids: set[int]) -> None:
    """Give pinned processes every CPU back (used when leaving a squeezing mode)."""
    everyone = os.sched_getaffinity(0)
    for pid in pids:
        try:
            os.sched_setaffinity(pid, everyone)
        except OSError:
            pass


def apply(entries: list[dict], run=_default_run) -> list[dict]:
    results = []
    for entry in entries:
        try:
            if "cpus" in entry:
                run(entry["pid"], entry["nice"], entry["cpus"])
            else:
                run(entry["pid"], entry["nice"])
            results.append({"pid": entry["pid"], "name": entry["name"], "ok": True})
        except (ProcessLookupError, PermissionError, OSError) as exc:
            results.append(
                {
                    "pid": entry["pid"],
                    "name": entry["name"],
                    "ok": False,
                    "error": str(exc),
                }
            )
    return results
