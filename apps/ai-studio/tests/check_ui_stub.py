"""A stand-in AI Studio backend for the page checks (stdlib only).

    python3 tests/check_ui_stub.py 9011

Serves the real static/ and ~/Forge/shared/ plus the HTTP API from
docs/2026-10-08-rebuild-plan.md with made-up models, so the page can be
checked without the real backend, any model file, any download or any GPU
work. Pictures are small SVGs drawn on the fly.

Test-only routes: GET /__stats (request counts), POST /__reset,
POST /__offline?on=1 (API calls get the connection dropped, as if the
server were down).
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from collections import Counter
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

APP = Path(__file__).resolve().parents[1]
STATIC = APP / "static"
SHARED = APP.parents[1] / "shared"
GB = 1_000_000_000
FREE = 81 * GB


def fixture_models() -> list[dict]:
    def card(id_, kind, label, blurb, total, **kw):
        c = {
            "id": id_,
            "kind": kind,
            "label": label,
            "blurb": blurb,
            "tier": "compact",
            "installed": False,
            "active": False,
            "can_run": True,
            "run_note": "",
            "download": None,
            "default_width": 512,
            "default_height": 512,
            "_total": total,
        }
        c.update(kw)
        return c

    return [
        card(
            "meina",
            "image",
            "Anime -- General",
            "Clean, bright anime pictures of almost anything.",
            2 * GB,
            installed=True,
            active=True,
        ),
        card(
            "realistic",
            "image",
            "Realistic",
            "Photo-like pictures of people, places and things.",
            2 * GB,
            installed=True,
        ),
        card(
            "z-image-turbo",
            "image",
            "Fast and Detailed",
            "Sharp, detailed pictures in a few seconds, good at following long descriptions.",
            int(9.4 * GB),
            default_width=1024,
            default_height=1024,
        ),
        card(
            "qwen-image",
            "image",
            "Best at Words in Pictures",
            "Draws signs, posters and labels with the words spelled right.",
            21 * GB,
            tier="big",
            can_run=False,
            run_note="Needs an engine update",
        ),
        card(
            "flux-huge",
            "image",
            "Studio Quality",
            "The most detailed pictures, slowly.",
            120 * GB,
            tier="big",
        ),
        card(
            "wan-small",
            "video",
            "Short Clips",
            "Turns a sentence or a picture into a few seconds of moving video.",
            int(6.2 * GB),
            installed=True,
        ),
        card(
            "anim-2d",
            "video",
            "2D Animation",
            "Hand-drawn style animation from a picture and a few words.",
            8 * GB,
            download={
                "state": "running",
                "done_bytes": int(3.36 * GB),
                "total_bytes": 8 * GB,
                "message": "",
            },
        ),
        card(
            "wan-big",
            "video",
            "Cinema Clips",
            "Longer, smoother clips with real camera moves.",
            28 * GB,
            tier="big",
            download={
                "state": "failed",
                "done_bytes": GB,
                "total_bytes": 28 * GB,
                "message": "The connection dropped",
            },
        ),
        card(
            "world-walk",
            "world",
            "Walk-Through Worlds",
            "Builds a place around you as you walk through it, from a picture or a sentence.",
            5 * GB,
            installed=True,
        ),
        card(
            "world-big",
            "world",
            "Explorable Worlds, Large",
            "Bigger, more detailed worlds you can move through freely.",
            40 * GB,
            tier="big",
            can_run=False,
            run_note="Needs the 3D world runtime, not set up yet",
        ),
    ]


class State:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.reset()

    def reset(self) -> None:
        self.models = fixture_models()
        self.library: list[dict] = [
            self.item(f"seed{i}", "image" if i % 3 else "video", p)
            for i, p in enumerate(
                [
                    "a fox reading under a lantern",
                    "harbour town at sunset",
                    "mossy forest path in the mist",
                    "neon city street in the rain",
                    "a cat asleep on a stack of books",
                    "mountain lake at dawn",
                ]
            )
        ]
        self.library[-1]["missing"] = True  # its file was deleted by hand
        self.counts: Counter[str] = Counter()
        self.offline = False
        self.busy = ""  # another window's heavy job: the 409 detail
        self.report_busy = True  # False: /api/busy keeps quiet (a job that just began)
        self.sessions: dict[str, dict] = {}
        self.jobs: dict[str, dict] = {}
        self.delay = 0.4

    @staticmethod
    def item(id_: str, kind: str, prompt: str) -> dict:
        return {
            "id": id_,
            "kind": kind,
            "prompt": prompt,
            "negative_prompt": "",
            "params": "{}",
            "url": (
                "/fixture/clip.webm" if kind == "video" else f"/fixture/pic/{id_}.svg"
            ),
            "created_at": time.time(),
            "total_seconds": 3.2,
            "thumb_url": f"/fixture/pic/{id_}.svg",
            "missing": False,
        }


S = State()
CLIP = Path(tempfile.gettempdir()) / "ai-studio-check-ui-clip.webm"


def make_clip() -> None:
    """A two-second test video, so video results play in the checks."""
    if CLIP.is_file() or not shutil.which("ffmpeg"):
        return
    subprocess.run(
        [
            "ffmpeg",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc=size=480x320:rate=12",
            "-t",
            "2",
            "-c:v",
            "libvpx",
            "-b:v",
            "300k",
            str(CLIP),
        ],
        check=False,
        timeout=60,
    )


def svg_picture(seed: str, label: str = "", w: int = 640, h: int = 640) -> bytes:
    hue = sum(map(ord, seed)) * 37 % 360
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">
<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
<stop offset="0" stop-color="hsl({hue},60%,55%)"/><stop offset="1" stop-color="hsl({(hue + 80) % 360},55%,25%)"/></linearGradient></defs>
<rect width="100%" height="100%" fill="url(#g)"/>
<circle cx="{w * 0.7}" cy="{h * 0.3}" r="{w * 0.12}" fill="hsl({(hue + 40) % 360},80%,80%)" opacity=".8"/>
<path d="M0 {h * 0.75} Q {w * 0.3} {h * 0.55} {w * 0.6} {h * 0.72} T {w} {h * 0.68} V {h} H 0 Z" fill="rgba(0,0,0,.35)"/>
<text x="24" y="{h - 24}" font-family="sans-serif" font-size="28" fill="#fff">{label}</text></svg>""".encode()


def svg_world(
    sid: str, step: int, x: float, yaw: float, pitch: float, z: float = 0.0
) -> bytes:
    w, h = 960, 540
    horizon = h * 0.5 + pitch * 200
    shift = (yaw * 400) % w
    trees = "".join(
        f'<rect x="{(i * 137 - shift + x * 30) % (w + 100) - 50:.0f}" y="{horizon - 120 - (i % 3) * 30:.0f}" width="26" height="{140 + (i % 3) * 30}" fill="#1d3b2a"/>'
        f'<circle cx="{(i * 137 - shift + x * 30) % (w + 100) - 37:.0f}" cy="{horizon - 130 - (i % 3) * 30:.0f}" r="{48 + (z * 6) % 30:.0f}" fill="#2f6b45"/>'
        for i in range(9)
    )
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">
<rect width="{w}" height="{horizon:.0f}" fill="#9cc6e8"/><rect y="{horizon:.0f}" width="{w}" height="{h}" fill="#5d7f3e"/>
{trees}<text x="20" y="40" font-family="sans-serif" font-size="26" fill="#102">world {sid} · frame {step}</text></svg>""".encode()


def public(card: dict) -> dict:
    return {k: v for k, v in card.items() if not k.startswith("_")}


class Handler(SimpleHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, format: str, *args) -> None:  # quiet
        pass

    # ---- plumbing ----
    def reply(self, code: int, body, ctype: str = "application/json") -> None:
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def body(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        if not n:
            return {}
        try:
            return json.loads(self.rfile.read(n) or b"{}")
        except ValueError:
            return {}

    def route(self, method: str) -> None:
        url = urlparse(self.path)
        path = url.path
        q = parse_qs(url.query)
        if path.startswith("/api/"):
            with S.lock:
                S.counts[f"{method} {path}"] += 1
                offline = S.offline
            if offline:
                self.close_connection = True
                self.connection.shutdown(2)
                return
            return self.api(method, path, q)
        if path == "/__stats":
            with S.lock:
                return self.reply(200, dict(S.counts))
        if path == "/__reset" and method == "POST":
            S.reset()
            return self.reply(200, {"ok": True})
        if path == "/__offline" and method == "POST":
            S.offline = q.get("on", ["1"])[0] == "1"
            return self.reply(200, {"offline": S.offline})
        if path == "/__busy" and method == "POST":
            S.busy = q.get("text", [""])[0]
            S.report_busy = q.get("report", ["1"])[0] == "1"
            return self.reply(200, {"busy": S.busy})
        if path == "/__delay" and method == "POST":
            S.delay = float(q.get("s", ["0.4"])[0])
            return self.reply(200, {"delay": S.delay})
        if path.startswith("/fixture/pic/"):
            name = path.rsplit("/", 1)[-1].removesuffix(".svg")
            return self.reply(200, svg_picture(name), "image/svg+xml")
        if path == "/fixture/clip.webm":
            return self.reply(
                200, CLIP.read_bytes() if CLIP.is_file() else b"", "video/webm"
            )
        if method != "GET":
            return self.reply(405, {"detail": "no"})
        if path.startswith("/shared/"):
            self.directory = str(SHARED)
            self.path = path[len("/shared") :]
        else:
            self.directory = str(STATIC)
        return super().do_GET()

    def translate_path(self, path: str) -> str:
        rel = urlparse(path).path.lstrip("/")
        return str(Path(self.directory) / (rel or "index.html"))

    def do_GET(self) -> None:
        self.route("GET")

    def do_POST(self) -> None:
        self.route("POST")

    def do_DELETE(self) -> None:
        self.route("DELETE")

    # ---- the API ----
    def find(self, mid: str) -> dict | None:
        return next((m for m in S.models if m["id"] == mid), None)

    def api(self, method: str, path: str, q: dict) -> None:
        heavy_start = method == "POST" and (
            path.startswith("/api/generate/")
            and not path.endswith("/cancel")
            or path.endswith("/activate")
            or path.startswith("/api/worlds/")
            and path.endswith("/start")
        )
        if S.busy and heavy_start:
            return self.reply(409, {"detail": S.busy})
        parts = path.strip("/").split("/")[1:]  # after "api"
        if parts == ["busy"] and method == "GET":
            return self.reply(200, {"busy": self.busy_now()})
        if parts == ["models"] and method == "GET":
            with S.lock:
                for m in S.models:
                    d = m["download"]
                    if d and d["state"] == "running":
                        d["done_bytes"] = min(
                            d["total_bytes"], d["done_bytes"] + d["total_bytes"] // 25
                        )
                        if d["done_bytes"] >= d["total_bytes"]:
                            m["download"], m["installed"] = None, True
                return self.reply(
                    200,
                    {
                        "models": [public(m) for m in S.models],
                        "disk": {"free_bytes": FREE},
                        "busy": self.busy_now(),
                    },
                )
        if parts == ["models", "delete-all"]:
            if method == "GET":
                return self.reply(
                    200,
                    [
                        {
                            "id": m["id"],
                            "label": m["label"],
                            "active": m["active"],
                            "bytes": m["_total"],
                            "files": [f"models/parts/{m['id']}.gguf"],
                            "note": "",
                            "default": True,
                        }
                        for m in S.models
                        if m["installed"]
                    ],
                )
            ids = set(self.body().get("ids", []))
            freed = 0
            for m in S.models:
                if m["id"] in ids and m["installed"]:
                    freed += m["_total"]
                    m["installed"] = m["active"] = False
            return self.reply(200, {"freed_bytes": freed})
        if len(parts) >= 2 and parts[0] == "models":
            m = self.find(parts[1])
            if not m:
                return self.reply(404, {"detail": "No such model."})
            action = parts[2] if len(parts) > 2 else ""
            need = 0 if m["installed"] else m["_total"]
            if action == "quote" and method == "GET":
                fits = FREE - need >= 5 * GB
                return self.reply(
                    200,
                    {
                        "total_bytes": m["_total"],
                        "needed_bytes": need,
                        "free_bytes": FREE,
                        "fits": fits,
                        "message": "" if fits else "Not enough free space.",
                    },
                )
            if action == "download" and method == "POST":
                if m["download"] and m["download"]["state"] == "running":
                    return self.reply(409, {"detail": "Already downloading."})
                if FREE - need < 5 * GB:
                    return self.reply(
                        507, {"detail": f"{m['label']} needs more space than is free."}
                    )
                done = (m["download"] or {}).get("done_bytes", 0)
                m["download"] = {
                    "state": "running",
                    "done_bytes": done,
                    "total_bytes": m["_total"],
                    "message": "",
                }
                return self.reply(200, {"status": "started"})
            if action == "cancel" and method == "POST":
                if m["download"]:
                    m["download"]["state"] = "cancelled"
                return self.reply(200, {"status": "cancelled"})
            if action == "activate" and method == "POST":
                if not m["installed"]:
                    return self.reply(409, {"detail": "Download it first."})
                for o in S.models:
                    if o["kind"] == m["kind"]:
                        o["active"] = o is m
                return self.reply(200, {"active": m["id"]})
            if action == "" and method == "DELETE":
                if not m["installed"]:
                    return self.reply(404, {"detail": "It isn't downloaded."})
                m["installed"] = m["active"] = False
                return self.reply(200, {"deleted": m["id"], "freed_bytes": m["_total"]})
        if parts[:1] == ["generate"] and parts[1:2] == ["model-video"]:
            return self.model_video(method, parts[2:])
        if parts[:1] == ["jobs"] and len(parts) == 3:
            return self.warp_job(method, parts[1], parts[2])
        if parts == ["generate", "video"] and method == "POST":
            body = self.body()
            if not (body.get("prompt") or body.get("scenes")):
                return self.reply(
                    422,
                    {"detail": [{"loc": ["body", "prompt"], "msg": "Field required"}]},
                )
            jid = f"w{len(S.jobs) + 1}"
            S.jobs[jid] = {
                "status": "running",
                "phase": "keyframes",
                "completed_frames": 0,
                "total_frames": 6,
                "error": "",
                "url": "/fixture/clip.webm",
                "prompt": body.get("prompt") or "story",
            }
            return self.reply(200, {"id": jid, "status": "running", "url": None})
        if parts[:1] == ["generate"] and method == "POST":
            body = self.body()
            time.sleep(S.delay)
            kind = "image" if parts[1] in ("image", "edit") else "video"
            if not (body.get("prompt") or body.get("scenes")):
                return self.reply(
                    422,
                    {"detail": [{"loc": ["body", "prompt"], "msg": "Field required"}]},
                )
            if parts[1] == "edit" and not (
                body.get("start_image") or body.get("start_image_url")
            ):
                return self.reply(400, {"detail": "Choose a picture to change."})
            n = max(1, int(body.get("batch_count") or 1)) if kind == "image" else 1
            batch = []
            for _ in range(n):
                jid = f"j{int(time.time() * 1000) % 10**9}{len(S.library)}"
                it = S.item(jid, kind, body.get("prompt") or "story")
                S.library.insert(0, it)
                batch.append(
                    {
                        "id": jid,
                        "url": it["url"],
                        "gen_seconds": 2.1,
                        "upscale_seconds": 1.1,
                        "total_seconds": 3.2,
                    }
                )
            out = dict(batch[-1])
            if n > 1:
                out.update(
                    batch=batch,
                    wall_seconds=7.5,
                    workers={"gpu": {"frames_done": n - 1}, "cpu": {"frames_done": 1}},
                )
            return self.reply(200, out)
        if parts == ["library"] and method == "GET":
            text = (q.get("q") or [""])[0].lower()
            kind = (q.get("kind") or [""])[0]
            rows = [
                r
                for r in S.library
                if (not kind or r["kind"] == kind) and text in r["prompt"].lower()
            ]
            return self.reply(200, rows)
        if parts[:1] == ["library"] and method == "DELETE":
            S.library = [r for r in S.library if r["id"] != parts[1]]
            return self.reply(200, {"deleted": parts[1]})
        if parts[:1] == ["worlds"]:
            return self.worlds(method, parts[1:])
        return self.reply(404, {"detail": "Not found"})

    @staticmethod
    def busy_now() -> dict | None:
        """What GET /api/busy (and GET /api/models) report as running."""
        if S.busy and S.report_busy:
            return {"kind": "video", "id": "elsewhere", "detail": S.busy}
        running = next(
            (j for j in S.jobs.values() if j.get("state") == "running"), None
        )
        if running:
            return {
                "kind": "video",
                "id": running["id"],
                "detail": "A video is being made. Wait for it or cancel it first.",
            }
        return None

    def warp_job(self, method: str, jid: str, what: str) -> None:
        job = S.jobs.get(jid)
        if job is None or "phase" not in job:
            return self.reply(404, {"detail": "no such job"})
        if what == "cancel" and method == "POST":
            if job["status"] == "running":
                job["status"] = "cancelled"
            return self.reply(200, {"id": jid, "cancel_requested": True})
        if what == "state" and method == "GET":
            if job["status"] == "running":
                job["completed_frames"] += 2
                if job["completed_frames"] >= job["total_frames"]:
                    job.update(
                        status="done",
                        phase="done",
                        gen_seconds=4.0,
                        upscale_seconds=1.0,
                        interpolate_seconds=1.0,
                        total_seconds=6.0,
                        frame_count=24,
                    )
                    it = S.item(jid, "video", job["prompt"])
                    S.library.insert(0, it)
            return self.reply(200, {k: v for k, v in job.items() if k != "prompt"})
        return self.reply(404, {"detail": "Not found"})

    def model_video(self, method: str, parts: list[str]) -> None:
        if not parts and method == "POST":
            body = self.body()
            active = next(
                (
                    m
                    for m in S.models
                    if m["kind"] == "video" and m["active"] and m["installed"]
                ),
                None,
            )
            if active is None:
                return self.reply(
                    409,
                    {
                        "detail": "no video model installed -- download one from the Models panel first"
                    },
                )
            jid = f"v{len(S.jobs) + 1}"
            S.jobs[jid] = {
                "id": jid,
                "model_id": active["id"],
                "state": "running",
                "message": "",
                "step": 0,
                "steps": 8,
                "url": None,
                "seconds": 0,
                "prompt": body.get("prompt", ""),
            }
            return self.reply(200, S.jobs[jid])
        job = S.jobs.get(parts[0]) if parts else None
        if job is None:
            return self.reply(404, {"detail": "no such video job"})
        if parts[1:] == ["cancel"] and method == "POST":
            if job["state"] == "running":
                job["state"], job["message"] = "cancelled", "Cancelled."
            return self.reply(200, job)
        if job["state"] == "running":
            job["step"] += 2
            job["seconds"] += 2
            if job["step"] >= job["steps"]:
                it = S.item(job["id"], "video", job["prompt"])
                it["url"] = "/fixture/clip.webm"
                S.library.insert(0, it)
                job.update(state="done", message="Done.", url=it["url"])
        return self.reply(200, job)

    LABELS = {
        "forward": "Walk forward",
        "back": "Walk back",
        "left": "Step left",
        "right": "Step right",
        "rise": "Go up",
        "sink": "Go down",
        "turn_left": "Turn left",
        "turn_right": "Turn right",
        "look_up": "Look up",
        "look_down": "Look down",
        "stay": "Stay and look",
    }
    MOVES = {
        "forward": (0, 1, 0, 0),
        "back": (0, -1, 0, 0),
        "left": (-1, 0, 0, 0),
        "right": (1, 0, 0, 0),
        "rise": (0, 0, 0, 0),
        "sink": (0, 0, 0, 0),
        "turn_left": (0, 0, -0.08, 0),
        "turn_right": (0, 0, 0.08, 0),
        "look_up": (0, 0, 0, -0.05),
        "look_down": (0, 0, 0, 0.05),
        "stay": (0, 0, 0, 0),
    }

    @staticmethod
    def advance(sess: dict) -> None:
        """The fake world model: a few pictures per move, one move per 0.5 s."""
        now = time.time()
        if sess["state"] == "starting" and now - sess["created"] > 0.8:
            sess["state"], sess["message"] = "waiting", ""
            sess["frames"] += [dict(sess["pose"]) for _ in range(4)]
            sess["last"] = now
        if sess["state"] == "waiting" and sess["queue"]:
            sess["state"], sess["last"] = "working", now
        while (
            sess["state"] == "working" and sess["queue"] and now - sess["last"] >= 0.5
        ):
            dx, dz, yaw, pitch = Handler.MOVES[sess["queue"].pop(0)]
            for _ in range(4):
                p = sess["pose"]
                p.update(
                    x=p["x"] + dx / 4,
                    z=p["z"] + dz / 4,
                    yaw=p["yaw"] + yaw / 4,
                    pitch=p["pitch"] + pitch / 4,
                )
                sess["frames"].append(dict(p))
            sess["last"] += 0.5
        if sess["state"] == "working" and not sess["queue"]:
            sess["state"] = "waiting"

    @staticmethod
    def payload(sid: str, sess: dict, since: int = 0) -> dict:
        names = [f"{i + 1:06d}.png" for i in range(len(sess["frames"]))]
        return {
            "id": sid,
            "model_id": sess["model_id"],
            "state": sess["state"],
            "message": sess["message"],
            "chunk": 0,
            "frame_count": len(names),
            "frames": names[since:],
            "since": since,
            "fps": 8,
            "queued_steps": len(sess["queue"]),
            "created": sess["created"],
        }

    def worlds(self, method: str, parts: list[str]) -> None:
        if parts == ["actions"] and method == "GET":
            return self.reply(200, self.LABELS)
        if not parts and method == "GET":
            return self.reply(
                200,
                {
                    "sessions": [
                        k
                        for k, v in S.sessions.items()
                        if v["state"] not in ("stopped", "done", "failed")
                    ],
                    "actions": self.LABELS,
                },
            )
        if len(parts) == 2 and parts[1] == "start" and method == "POST":
            m = self.find(parts[0])
            if not m or not m["installed"]:
                return self.reply(
                    409, {"detail": "that world model is not downloaded yet"}
                )
            if any(
                v["state"] not in ("stopped", "done", "failed")
                for v in S.sessions.values()
            ):
                return self.reply(
                    409, {"detail": "A world is already running. Stop it first."}
                )
            sid = f"20261008-s{len(S.sessions) + 1}"
            S.sessions[sid] = {
                "model_id": m["id"],
                "state": "starting",
                "message": "Getting the world ready",
                "created": time.time(),
                "last": 0.0,
                "queue": [],
                "frames": [],
                "pose": {"x": 0.0, "z": 0.0, "yaw": 0.0, "pitch": 0.0},
            }
            return self.reply(200, self.payload(sid, S.sessions[sid]))
        if len(parts) >= 2 and parts[0] == "sessions":
            sid = parts[1]
            sess = S.sessions.get(sid)
            if not sess:
                return self.reply(404, {"detail": "No such world session"})
            self.advance(sess)
            rest = parts[2:]
            if not rest and method == "GET":
                since = int(
                    (parse_qs(urlparse(self.path).query).get("since") or ["0"])[0]
                )
                return self.reply(200, self.payload(sid, sess, since))
            if rest == ["step"] and method == "POST":
                acts = self.body().get("actions") or []
                bad = [a for a in acts if a not in self.MOVES]
                if not acts or bad:
                    return self.reply(
                        400,
                        {
                            "detail": (
                                f"Unknown move: {bad[0]}"
                                if bad
                                else "Pick at least one move"
                            )
                        },
                    )
                if sess["state"] in ("stopped", "done", "failed"):
                    return self.reply(
                        400, {"detail": "This world has stopped. Start a new one."}
                    )
                sess["queue"] += acts
                return self.reply(200, self.payload(sid, sess))
            if rest == ["stop"] and method == "POST":
                sess["state"], sess["message"] = "stopped", "Stopped"
                return self.reply(200, self.payload(sid, sess))
            if rest == ["clip"] and method == "POST":
                return self.reply(200, {"url": "/fixture/clip.webm"})
            if len(rest) == 2 and rest[0] == "frames":
                i = int(rest[1].split(".")[0]) - 1
                if not 0 <= i < len(sess["frames"]):
                    return self.reply(404, {"detail": "No such frame"})
                p = sess["frames"][i]
                return self.reply(
                    200,
                    svg_world(sid[-2:], i + 1, p["x"], p["yaw"], p["pitch"], p["z"]),
                    "image/svg+xml",
                )
        return self.reply(404, {"detail": "Not found"})


def main(port: int) -> None:
    make_clip()
    ThreadingHTTPServer.daemon_threads = True
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 9011)
