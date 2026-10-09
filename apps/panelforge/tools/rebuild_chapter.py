"""Re-run the whole chapter pipeline through a running PanelForge server.

    .venv/bin/python tools/rebuild_chapter.py --port 8460 bad-born-blood 0001 \
        --out lookie-04 --max-seconds 90 [--from STEP] [--to STEP] [--no-llm]

Each step posts to the API, waits for the job and prints its last log lines,
so it is safe to run unattended in the background and read the log later.
Voices use the temporary preview voice for characters without one, exactly as
the earlier look-see renders did; nothing is written to cast.json.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request

STEPS = ["detect", "analyze", "script", "llm", "voice", "audio", "timeline", "render"]


def call(base: str, method: str, path: str, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        base + path,
        data=data,
        method=method,
        headers={"content-type": "application/json"} if data else {},
    )
    with urllib.request.urlopen(req, timeout=600) as r:
        return json.loads(r.read() or b"null")


def wait(base: str, job_id: str, label: str) -> dict:
    t0 = time.time()
    last = 0
    while True:
        j = call(base, "GET", f"/api/jobs/{job_id}")
        if j["state"] not in ("queued", "running"):
            break
        if time.time() - last > 30:
            print(f"[{label}] {j['state']} {j.get('progress', 0):.0%}", flush=True)
            last = time.time()
        time.sleep(3)
    for line in j.get("log", [])[-6:]:
        print(f"[{label}]   {line}", flush=True)
    print(f"[{label}] {j['state']} after {time.time() - t0:.0f}s", flush=True)
    if j["state"] != "done":
        print(json.dumps(j.get("error") or j.get("result"), indent=1)[:2000])
        sys.exit(1)
    return j


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("series")
    ap.add_argument("chapter")
    ap.add_argument("--port", type=int, default=8460)
    ap.add_argument("--out", default="rebuild")
    ap.add_argument("--max-seconds", type=float, default=0)
    ap.add_argument("--style", default="depth3d")
    ap.add_argument("--preview-voice", default="am_michael")
    ap.add_argument("--from", dest="start", choices=STEPS, default="detect")
    ap.add_argument("--to", dest="stop", choices=STEPS, default="render")
    ap.add_argument("--no-llm", action="store_true", help="skip the model page reading")
    a = ap.parse_args()
    base = f"http://127.0.0.1:{a.port}"
    ch = f"/api/chapters/{a.series}/{a.chapter}"
    todo = STEPS[STEPS.index(a.start) : STEPS.index(a.stop) + 1]

    if "detect" in todo:
        wait(base, call(base, "POST", f"{ch}/detect")["job_id"], "detect")
        print(json.dumps(call(base, "GET", f"{ch}/detect/stats")), flush=True)
    if "analyze" in todo:
        wait(base, call(base, "POST", f"{ch}/analyze")["job_id"], "analyze")
    if "script" in todo:
        r = call(base, "POST", f"{ch}/script/build")
        if isinstance(r, dict) and "job_id" in r:
            wait(base, r["job_id"], "script")
        else:
            print(f"[script] {json.dumps(r)[:300]}", flush=True)
    if "llm" in todo and not a.no_llm:
        r = call(base, "POST", f"{ch}/script/llm")
        wait(base, r["job_id"], "llm")
    if "voice" in todo:
        r = call(base, "POST", f"{ch}/voice", {"preview_voice": a.preview_voice})
        wait(base, r["job_id"], "voice")
    if "audio" in todo:
        wait(base, call(base, "POST", f"{ch}/audio/auto")["job_id"], "audio")
    if "timeline" in todo:
        r = call(base, "POST", f"{ch}/timeline/auto", {"settings": {"style": a.style}})
        if isinstance(r, dict) and "job_id" in r:
            wait(base, r["job_id"], "timeline")
        else:
            print(f"[timeline] {json.dumps(r)[:300]}", flush=True)
    if "render" in todo:
        body = {
            "aspect": "16:9",
            "bubbles": "keep",
            "style": a.style,
            "out_name": a.out,
            "backdrop": "auto",
        }
        if a.max_seconds:
            body["max_seconds"] = a.max_seconds
        wait(base, call(base, "POST", f"{ch}/render", body)["job_id"], "render")


if __name__ == "__main__":
    main()
