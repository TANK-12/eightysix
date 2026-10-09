"""Bulk runs: every step for a range of chapters, as one job.

Emerson (2026-09-19): "do bulk, like full all-chapter runs, and select at
least from chapter 1 to chapter 10 to 100". A batch job walks the chapters
in order and, for each, runs the chosen steps through the app's own API,
exactly as `tools/rebuild_chapter.py` does from the shell -- one sequencing,
used from both places. Steps that need a chapter's pages fetch it first
when it is missing. Progress is per chapter and per step; a failed step
stops that chapter and the batch moves on, saying so in the log.
"""

from __future__ import annotations

import json
import time
import urllib.request
from typing import Callable

STEPS = (
    "fetch",
    "detect",
    "analyze",
    "script",
    "llm",
    "voice",
    "audio",
    "timeline",
    "render",
)
# The first phase runs for every chapter before the second starts: the cast
# is only complete once every chapter is analysed, and the voices are cast
# (by the model, from the pictures) between the phases, so chapter 1's
# lines are voiced knowing who turns up in chapter 40.
GATHER_STEPS = ("fetch", "detect", "analyze")


def api_call(base: str, method: str, path: str, body=None, timeout: float = 600.0):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        base + path,
        data=data,
        method=method,
        headers={"content-type": "application/json"} if data else {},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read() or b"null")


def wait_job(base: str, job_id: str, check: Callable[[], None] | None = None) -> dict:
    while True:
        j = api_call(base, "GET", f"/api/jobs/{job_id}")
        if j["state"] not in ("queued", "running"):
            return j
        if check:
            check()
        time.sleep(2.0)


def chapter_steps(
    base: str,
    series: str,
    chapter: str,
    steps: list[str],
    opts: dict,
    log: Callable[[str], None],
    check: Callable[[], None] | None = None,
    call=api_call,
    wait=wait_job,
) -> bool:
    """Run `steps` for one chapter through the API at `base`. True on success."""
    ch = f"/api/chapters/{series}/{chapter}"
    number = float(int(chapter)) if chapter.isdigit() else None

    def run(label: str, method: str, path: str, body=None) -> bool:
        r = call(base, method, path, body)
        if isinstance(r, dict) and "job_id" in r:
            j = wait(base, r["job_id"], check)
            tail = (j.get("log") or [""])[-1]
            log(f"[{chapter}] {label}: {j['state']} -- {tail[:100]}")
            return j["state"] == "done"
        log(f"[{chapter}] {label}: done")
        return True

    for step in steps:
        if check:
            check()
        if step == "fetch":
            if number is None:
                log(f"[{chapter}] fetch: chapter name is not a number, skipped")
                continue
            body = {"series": series, "chapters": [number]}
            if opts.get("group"):
                body["group"] = opts["group"]
            ok = run("fetch", "POST", "/api/fetch/chapters", body)
        elif step == "detect":
            ok = run("detect", "POST", f"{ch}/detect")
        elif step == "analyze":
            ok = run("analyze", "POST", f"{ch}/analyze")
        elif step == "script":
            ok = run("script", "POST", f"{ch}/script/build")
        elif step == "llm":
            ok = run("llm", "POST", f"{ch}/script/llm")
        elif step == "voice":
            body = (
                {"preview_voice": opts["preview_voice"]}
                if opts.get("preview_voice")
                else None
            )
            ok = run("voice", "POST", f"{ch}/voice", body)
        elif step == "audio":
            ok = run("audio", "POST", f"{ch}/audio/auto")
        elif step == "timeline":
            ok = run(
                "timeline",
                "POST",
                f"{ch}/timeline/auto",
                {"settings": opts.get("timeline") or {}},
            )
        elif step == "render":
            ok = run("render", "POST", f"{ch}/render", opts.get("render") or {})
        else:
            log(f"[{chapter}] unknown step {step!r}, skipped")
            ok = True
        if not ok:
            log(f"[{chapter}] stopped at {step}")
            return False
    return True


def run_batch(
    base: str,
    series: str,
    chapters: list[str],
    steps: list[str],
    opts: dict,
    job,
    call=api_call,
    wait=wait_job,
) -> dict:
    done, failed = [], []
    gather = [s for s in steps if s in GATHER_STEPS]
    build = [s for s in steps if s not in GATHER_STEPS]
    phases = [p for p in (gather, build) if p]
    total = max(1, len(chapters) * len(phases))
    n = 0
    for phase in phases:
        if phase is build and "voice" in build and opts.get("cast", True):
            job.log("casting voices from the character pictures")
            r = call(base, "POST", f"/api/series/{series}/cast/voices/auto", {})
            if isinstance(r, dict) and "job_id" in r:
                j = wait(base, r["job_id"], job.check)
                job.log(f"casting: {j['state']} -- {(j.get('log') or [''])[-1][:100]}")
        for chapter in chapters:
            if chapter in failed:
                continue
            job.progress(n / total)
            n += 1
            job.log(f"chapter {chapter}: {', '.join(phase)}")
            ok = chapter_steps(
                base, series, chapter, phase, opts, job.log, job.check, call, wait
            )
            if not ok:
                failed.append(chapter)
    done = [c for c in chapters if c not in failed]
    job.log(
        f"batch finished: {len(done)} chapters done, {len(failed)} failed{': ' + ', '.join(failed) if failed else ''}"
    )
    return {"done": done, "failed": failed}
