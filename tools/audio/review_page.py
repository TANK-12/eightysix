#!/usr/bin/env python3
"""The sound review page (lane B4): assets/audio/review/index.html lists every candidate sound
(the synth takes in synth/ and any other .wav/.ogg/.mp3 dropped in a subfolder) with a player,
keep/drop and a note. Decisions go to assets/audio/review/review.json, which tools/audio/promote.py
reads to put the kept sounds in the game.

  tools/audio/review_page.py            rebuild index.html (the list is baked in, so it opens from disk)
  tools/audio/review_page.py --serve    also serve it on http://127.0.0.1:8687/ so Save writes review.json
                                        directly (opened from disk, Save downloads the file instead)
"""

import http.server
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
REVIEW = ROOT / "assets/audio/review"
RECIPES = ROOT / "tools/audio/recipes.json"
PORT = 8687
EXTS = {".wav", ".ogg", ".mp3", ".flac"}


def candidates() -> list[dict]:
    labels = {
        rid: r.get("label", rid)
        for rid, r in json.loads(RECIPES.read_text())["entries"].items()
    }
    buses = {
        rid: r.get("bus", "")
        for rid, r in json.loads(RECIPES.read_text())["entries"].items()
    }
    out = []
    for f in sorted(REVIEW.rglob("*")):
        if f.suffix.lower() not in EXTS or f.parent == REVIEW:
            continue
        rel = f.relative_to(REVIEW).as_posix()
        stem = f.stem.rsplit("_", 1)[0]
        out.append(
            {
                "file": rel,
                "group": labels.get(stem, stem.replace("_", " ")),
                "bus": buses.get(stem, f.parent.name),
                "source": f.parent.name,
            }
        )
    return out


PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Eighty Six sound review</title>
<style>
:root { --bg: #11151a; --panel: #1b222b; --line: #2c3642; --text: #e6e9ec; --dim: #9aa6b2;
  --keep: #5fbf7a; --drop: #d9655b; --accent: #d9a441; }
* { box-sizing: border-box; }
body { margin: 0; font: 15px/1.45 system-ui, sans-serif; background: var(--bg); color: var(--text); }
header { position: sticky; top: 0; background: var(--panel); border-bottom: 1px solid var(--line);
  padding: 12px 20px; display: flex; gap: 16px; align-items: center; z-index: 2; }
h1 { font-size: 18px; margin: 0; font-weight: 600; }
.count { color: var(--dim); }
button { background: #26303b; color: var(--text); border: 1px solid var(--line); border-radius: 6px;
  padding: 6px 12px; font: inherit; cursor: pointer; }
button:hover, button:focus-visible { border-color: var(--accent); outline: none; }
button.save { background: var(--accent); color: #1a1407; border-color: var(--accent); font-weight: 600; }
main { padding: 12px 20px 60px; max-width: 1100px; }
section { margin: 18px 0; }
h2 { font-size: 15px; margin: 0 0 6px; color: var(--accent); font-weight: 600; }
h2 small { color: var(--dim); font-weight: 400; margin-left: 8px; }
.row { display: grid; grid-template-columns: 170px 1fr auto 1fr; gap: 12px; align-items: center;
  background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 6px 10px; margin: 4px 0; }
.row.keep { border-left: 4px solid var(--keep); }
.row.drop { border-left: 4px solid var(--drop); opacity: 0.7; }
.name { color: var(--dim); font-family: ui-monospace, monospace; font-size: 13px; }
audio { width: 100%; height: 32px; }
.pick button { min-width: 64px; }
.pick button.on.k { background: var(--keep); color: #0d1a10; border-color: var(--keep); }
.pick button.on.d { background: var(--drop); color: #1f0c0a; border-color: var(--drop); }
input[type=text] { width: 100%; background: #141a21; color: var(--text); border: 1px solid var(--line);
  border-radius: 6px; padding: 5px 8px; font: inherit; }
#status { color: var(--dim); margin-left: auto; }
</style></head><body>
<header><h1>Eighty Six sound review</h1><span class="count" id="count"></span>
<span id="status"></span><button class="save" id="save">Save review.json</button></header>
<main id="list"></main>
<script>
const FILES = __FILES__;
let review = __REVIEW__;
try { Object.assign(review, JSON.parse(localStorage.getItem("es86_review") || "{}")); } catch (e) {}
const list = document.getElementById("list");
const groups = {};
for (const f of FILES) (groups[f.group] = groups[f.group] || []).push(f);
for (const [g, files] of Object.entries(groups)) {
  const sec = document.createElement("section");
  sec.innerHTML = `<h2>${g}<small>${files[0].bus} · ${files[0].source}</small></h2>`;
  for (const f of files) {
    const row = document.createElement("div");
    row.className = "row";
    row.innerHTML = `<span class="name">${f.file.split("/").pop()}</span>
      <audio controls preload="none" src="${f.file}"></audio>
      <span class="pick"><button class="k">Keep</button> <button class="d">Drop</button></span>
      <input type="text" placeholder="Note (optional)">`;
    const [k, d] = row.querySelectorAll("button");
    const note = row.querySelector("input");
    const state = () => review[f.file] || "keep";
    const paint = () => {
      row.classList.toggle("keep", state() === "keep");
      row.classList.toggle("drop", state() === "drop");
      k.classList.toggle("on", state() === "keep");
      d.classList.toggle("on", state() === "drop");
      count();
    };
    k.onclick = () => { review[f.file] = "keep"; remember(); paint(); };
    d.onclick = () => { review[f.file] = "drop"; remember(); paint(); };
    note.value = review["note:" + f.file] || "";
    note.oninput = () => { review["note:" + f.file] = note.value; remember(); };
    paint();
    sec.appendChild(row);
  }
  list.appendChild(sec);
}
function remember() { localStorage.setItem("es86_review", JSON.stringify(review)); }
function count() {
  const drops = FILES.filter(f => (review[f.file] || "keep") === "drop").length;
  document.getElementById("count").textContent = `${FILES.length} takes · ${FILES.length - drops} kept · ${drops} dropped`;
}
document.getElementById("save").onclick = async () => {
  const body = JSON.stringify(review, null, 1);
  const status = document.getElementById("status");
  if (location.protocol.startsWith("http")) {
    const r = await fetch("review.json", { method: "POST", body });
    status.textContent = r.ok ? "Saved to assets/audio/review/review.json" : "Save failed";
  } else {
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([body], { type: "application/json" }));
    a.download = "review.json"; a.click();
    status.textContent = "Downloaded: move it to assets/audio/review/";
  }
};
</script></body></html>
"""


def build() -> pathlib.Path:
    path = REVIEW / "review.json"
    review = json.loads(path.read_text()) if path.exists() else {}
    page = PAGE.replace("__FILES__", json.dumps(candidates())).replace(
        "__REVIEW__", json.dumps(review)
    )
    out = REVIEW / "index.html"
    out.write_text(page)
    return out


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(REVIEW), **kwargs)

    def do_POST(self) -> None:
        if self.path.rstrip("/") != "/review.json":
            self.send_error(404)
            return
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        try:
            data = json.loads(body)
        except ValueError:
            self.send_error(400, "not JSON")
            return
        (REVIEW / "review.json").write_text(json.dumps(data, indent=1))
        self.send_response(200)
        self.end_headers()


def main() -> None:
    out = build()
    print(f"{out.relative_to(ROOT)}: {len(candidates())} takes")
    if "--serve" in sys.argv:
        print(f"http://127.0.0.1:{PORT}/")
        http.server.ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
