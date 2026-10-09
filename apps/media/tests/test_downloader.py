"""The YouTube downloader end to end through the real API, with a fake yt-dlp
on PATH so nothing touches the network, plus a check that the page only
calls helpers that exist.

The page check is here because the downloader broke (2026-09-25) in a way no
backend test could see: app.js called streamJob(), a helper that only ever
lived inside MediaForge's own page, so Find threw and hung on "asking
YouTube...". The API underneath was fine the whole time."""

import re
import sys
import time
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))

FAKE_YTDLP = r"""#!/usr/bin/env python3
import json, sys
args = sys.argv[1:]
url = args[-1]
if "-J" in args:
    print(json.dumps({"id": "abc123", "title": "Tiny clip", "duration": 19,
                      "uploader": "someone", "webpage_url": url}))
    sys.exit(0)
if "fail" in url:
    print("ERROR: [youtube] fail: Video unavailable")
    sys.exit(1)
out = args[args.index("-o") + 1]
path = out.replace("%(title).150s", "Tiny clip").replace("%(id)s", "abc123")
path = path.replace("%(ext)s", "mp3" if "-x" in args else "mp4")
for pct in ("10.0", "55.5", "100.0"):
    print(f"[download]  {pct}% of 1.00MiB", flush=True)
open(path, "wb").write(b"ID3fake")
print(f"[ExtractAudio] Destination: {path}")
"""


@pytest.fixture
def client(tmp_path, monkeypatch):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake = bin_dir / "yt-dlp"
    fake.write_text(FAKE_YTDLP)
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}:/usr/bin:/bin")
    monkeypatch.setenv("FORGE_MEDIA_DATA", str(tmp_path / "data"))
    from fastapi.testclient import TestClient

    import web_app

    return TestClient(web_app.app)


def wait_job(client, job_id, timeout=15.0):
    end = time.time() + timeout
    while time.time() < end:
        j = client.get(f"/api/jobs/{job_id}").json()
        if j["status"] != "running":
            return j
        time.sleep(0.05)
    raise AssertionError(f"job {job_id} still running after {timeout}s")


def test_list_a_video_link(client):
    r = client.post(
        "/api/yt/list", json={"text": "https://www.youtube.com/watch?v=abc123"}
    )
    assert r.status_code == 200
    j = wait_job(client, r.json()["job_id"])
    assert j["status"] == "done", j
    assert [e["title"] for e in j["result"]["entries"]] == ["Tiny clip"]
    assert j["result"]["entries"][0]["url"] == "https://www.youtube.com/watch?v=abc123"


def test_download_saves_the_file_and_reports_progress(client, tmp_path):
    folder = tmp_path / "Music"
    r = client.post(
        "/api/yt/download",
        json={
            "urls": ["https://www.youtube.com/watch?v=abc123"],
            "kind": "audio",
            "folder": str(folder),
        },
    )
    assert r.status_code == 200
    job_id = r.json()["job_id"]
    j = wait_job(client, job_id)
    assert j["status"] == "done", j
    assert j["result"] == {"done": 1, "failed": 0, "folder": str(folder)}
    assert (folder / "Tiny clip [abc123].mp3").read_bytes() == b"ID3fake"
    events = client.get(f"/api/jobs/{job_id}/events").text
    assert '"frac": 1.0' in events
    assert "finished: 1 saved, 0 failed" in events


def test_one_failed_video_does_not_stop_the_batch(client, tmp_path):
    folder = tmp_path / "Music"
    r = client.post(
        "/api/yt/download",
        json={
            "urls": [
                "https://www.youtube.com/watch?v=fail",
                "https://www.youtube.com/watch?v=abc123",
            ],
            "folder": str(folder),
        },
    )
    j = wait_job(client, r.json()["job_id"])
    assert j["result"]["done"] == 1 and j["result"]["failed"] == 1


# --------------------------------------------------------------------------
# the page calls only what exists

JS_NAMES = {
    # keywords that look like calls
    "if", "for", "while", "switch", "catch", "function", "return", "typeof",
    "async", "await", "new", "of", "in",
    # browser and language globals
    "fetch", "setTimeout", "clearTimeout", "setInterval", "clearInterval",
    "requestAnimationFrame", "cancelAnimationFrame", "parseInt", "parseFloat",
    "encodeURIComponent", "decodeURIComponent", "isNaN", "isFinite", "String",
    "Number", "Boolean", "Array", "Object", "Promise", "Date", "alert",
    "confirm", "prompt", "structuredClone", "queueMicrotask", "Error",
    "ResizeObserver", "addEventListener", "getComputedStyle",
}  # fmt: skip


def defined_names(js: str) -> set[str]:
    pats = [
        r"\bfunction\s+([A-Za-z_$][\w$]*)",
        r"\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)",
        r"\b(?:const|let|var)\s*\{([^}]*)\}",
        r"\bclass\s+([A-Za-z_$][\w$]*)",
    ]
    names: set[str] = set()
    for p in pats:
        for m in re.finditer(p, js):
            names.update(n.split(":")[-1].strip() for n in m.group(1).split(","))
    # arrow-function and callback parameters: (a, b) => / x =>
    for m in re.finditer(r"\(([^()]*)\)\s*=>|([A-Za-z_$][\w$]*)\s*=>", js):
        params = m.group(1) if m.group(1) is not None else m.group(2)
        names.update(n.split("=")[0].strip(" .{}") for n in params.split(","))
    return {n for n in names if n}


def called_names(js: str) -> set[str]:
    js = re.sub(r"//[^\n]*|/\*.*?\*/", "", js, flags=re.S)
    js = re.sub(r"`(?:\\.|[^`])*`|\"(?:\\.|[^\"])*\"|'(?:\\.|[^'])*'", '""', js)
    return set(re.findall(r"(?<![\w$.])([A-Za-z_$][\w$]*)\s*\(", js))


def test_every_helper_app_js_calls_is_loaded():
    html = (APP / "static" / "index.html").read_text()
    shared = APP.parent.parent / "shared"
    known = set(JS_NAMES)
    for src in re.findall(r'<script src="([^"]+)"', html):
        path = (
            shared / src[len("/shared/") :]
            if src.startswith("/shared/")
            else APP / "static" / src
        )
        known |= defined_names(path.read_text())
    missing = called_names((APP / "static" / "app.js").read_text()) - known
    assert (
        not missing
    ), f"app.js calls functions no loaded script defines: {sorted(missing)}"


def test_page_has_the_toast_box_errors_are_shown_in():
    # shared toast() writes into #toast and silently does nothing without it,
    # which hid every "Search failed" / "Download failed" message
    assert 'id="toast"' in (APP / "static" / "index.html").read_text()
