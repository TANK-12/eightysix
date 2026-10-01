#!/usr/bin/env python3
"""Download the sound library listed in library_sources.json (lane B4 part 2).

Files land in ~/Forge/shared/sound_library/<source>/ and library.json beside them lists each one
(id, title, tags, licence, path, seconds). Already downloaded files are skipped, so a rerun only
fetches what is new. Run: tools/audio/fetch_library.py [--only mixkit|kenney|opengameart|bigsoundbank]
"""

import argparse
import io
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import wave
import zipfile
from concurrent.futures import ThreadPoolExecutor
from html import unescape
from pathlib import Path

HERE = Path(__file__).resolve().parent
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) Firefox/140.0"}
AUDIO = (".wav", ".ogg", ".mp3", ".flac")


def get(url: str) -> bytes:
    """Fetch with retries; on HTTP 429 (too many requests) wait longer each time."""
    for attempt in range(6):
        try:
            with urllib.request.urlopen(
                urllib.request.Request(url, headers=UA), timeout=60
            ) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if attempt == 5 or e.code not in (429, 500, 502, 503):
                raise
            time.sleep(15 * (attempt + 1))
        except Exception:
            if attempt == 5:
                raise
            time.sleep(3)
    return b""


def seconds(path: Path) -> float:
    if path.suffix != ".wav":
        return 0.0
    try:
        with wave.open(str(path)) as w:
            return round(w.getnframes() / float(w.getframerate()), 2)
    except Exception:
        return 0.0


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")[:60]


def index_mixkit_files(spec: dict, root: Path, entries: dict) -> None:
    """Lists Mixkit files already on disk (named <id>_<title>.wav). Mixkit's listing pages sit
    behind a Cloudflare bot check since 2026-10-01, so a rerun may not be able to list them again.
    """
    for path in sorted((root / "mixkit").glob("*.wav")):
        sid, _, name = path.stem.partition("_")
        entries.setdefault(
            f"mixkit_{sid}",
            {
                "title": name.replace("_", " "),
                "source": "mixkit",
                "licence": spec["licence"],
                "tags": [],
                "path": str(path),
                "seconds": seconds(path) or probe_seconds(path),
            },
        )


def fetch_mixkit(spec: dict, root: Path, entries: dict) -> None:
    out = root / "mixkit"
    out.mkdir(parents=True, exist_ok=True)
    index_mixkit_files(spec, root, entries)
    card = re.compile(
        r'data-audio-player-item-id-value="(\d+)".*?item-grid-card__title">\s*([^<]+?)\s*<',
        re.S,
    )
    wanted: dict = {}
    for tag in spec["tags"]:
        for page in range(1, 20):
            try:
                html = get(spec["url"].format(tag=tag, page=page)).decode(
                    "utf-8", "replace"
                )
            except Exception as e:
                print(f"mixkit {tag} page {page}: {e}", flush=True)
                break
            found = card.findall(html)
            fresh = [
                sid
                for sid, _ in found
                if f"mixkit_{sid}" not in wanted and f"mixkit_{sid}" not in entries
            ]
            if not found or (page > 1 and not fresh):
                break
            time.sleep(1.5)
            for sid, title in found:
                key = f"mixkit_{sid}"
                entry = entries.get(key) or wanted.get(key)
                if entry is not None:
                    if tag not in entry["tags"]:
                        entry["tags"].append(tag)
                    continue
                title = unescape(title)
                wanted[key] = {
                    "title": title,
                    "source": "mixkit",
                    "licence": spec["licence"],
                    "tags": [tag],
                    "path": str(out / f"{sid}_{slug(title)}.wav"),
                    "id": sid,
                }
        print(f"mixkit {tag}: listed, {len(wanted)} new so far", flush=True)

    def download(item: tuple) -> None:
        key, entry = item
        path = Path(entry["path"])
        if not path.exists():
            try:
                path.write_bytes(get(spec["file"].format(id=entry.pop("id"))))
            except Exception as e:
                print(f"mixkit {key}: {e}", flush=True)
                return
        entry.pop("id", None)
        entry["seconds"] = seconds(path)
        entries[key] = entry

    with ThreadPoolExecutor(4) as pool:
        list(pool.map(download, wanted.items()))


def fetch_opengameart(spec: dict, root: Path, entries: dict) -> None:
    out = root / "opengameart"
    out.mkdir(parents=True, exist_ok=True)
    seen: set = set()
    for q in spec["queries"]:
        for page in range(spec["pages"]):
            url = spec["search"].format(q=urllib.parse.quote(q), page=page)
            try:
                html = get(url).decode("utf-8", "replace")
            except Exception as e:
                print(f"opengameart {q}: {e}", flush=True)
                break
            items = sorted(
                set(re.findall(r'href="/content/([a-z0-9-]+)"', html)) - {"faq"}
            )
            for item in items:
                if item in seen:
                    continue
                seen.add(item)
                fetch_oga_item(spec, out / item, item, q, entries)
        print(f"opengameart {q}: done ({len(seen)} items seen)", flush=True)


def fetch_oga_item(spec: dict, out: Path, item: str, q: str, entries: dict) -> None:
    """One OpenGameArt item: checks the page says CC0, then takes its audio files and zips."""
    if not out.exists():
        try:
            page = get("https://opengameart.org/content/" + item).decode(
                "utf-8", "replace"
            )
        except Exception:
            return
        lic = re.search(r"License\(s\):(.{0,600})", page, re.S)
        if not lic or "CC0" not in lic.group(1):
            return
        links = re.findall(
            r'href="(https://opengameart\.org/sites/default/files/[^"]+)"', page
        )
        files = [u for u in links if u.lower().endswith(AUDIO + (".zip",))]
        if not files:
            return
        out.mkdir(parents=True, exist_ok=True)
        for u in files:
            try:
                data = get(u)
            except Exception:
                continue
            if len(data) > spec["max_mb_per_item"] * 1e6:
                continue
            name = urllib.parse.unquote(u.rsplit("/", 1)[-1])
            if name.lower().endswith(".zip"):
                try:
                    with zipfile.ZipFile(io.BytesIO(data)) as z:
                        for n in z.namelist():
                            if n.lower().endswith(AUDIO) and not n.startswith(
                                "__MACOSX"
                            ):
                                (out / Path(n).name).write_bytes(z.read(n))
                except zipfile.BadZipFile:
                    continue
            else:
                (out / name).write_bytes(data)
    if not out.exists():
        return
    title = item.replace("-", " ")
    for path in sorted(out.iterdir()):
        if path.suffix.lower() not in AUDIO:
            continue
        key = f"oga_{item}_{slug(path.stem)}"
        entry = entries.setdefault(
            key,
            {
                "title": f"{title}: {path.stem.replace('_', ' ')}",
                "source": "opengameart",
                "licence": spec["licence"],
                "tags": [],
                "path": str(path),
                "seconds": seconds(path) or probe_seconds(path),
                "page": "https://opengameart.org/content/" + item,
            },
        )
        if q not in entry["tags"]:
            entry["tags"].append(q)


def probe_seconds(path: Path) -> float:
    import subprocess

    r = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "csv=p=0",
            str(path),
        ],
        capture_output=True,
        text=True,
    )
    try:
        return round(float(r.stdout.strip()), 2)
    except ValueError:
        return 0.0


def fetch_kenney(spec: dict, root: Path, entries: dict) -> None:
    for pack in spec["packs"]:
        out = root / "kenney" / pack
        if not out.exists():
            html = get(spec["page"].format(pack=pack)).decode("utf-8", "replace")
            zips = re.findall(r'https://kenney\.nl/media/pages/assets/[^"]+\.zip', html)
            if not zips:
                print(f"kenney {pack}: no zip link")
                continue
            with zipfile.ZipFile(io.BytesIO(get(zips[0]))) as z:
                for name in z.namelist():
                    if name.lower().endswith(AUDIO) or name.lower().endswith(
                        ("license.txt",)
                    ):
                        target = out / Path(name).name
                        target.parent.mkdir(parents=True, exist_ok=True)
                        target.write_bytes(z.read(name))
        for path in sorted(out.iterdir()):
            if path.suffix.lower() not in AUDIO:
                continue
            entries[f"kenney_{pack}_{path.stem}"] = {
                "title": path.stem.replace("_", " "),
                "source": "kenney",
                "licence": spec["licence"],
                "tags": [pack],
                "path": str(path),
                "seconds": seconds(path) or probe_seconds(path),
            }
        print(f"kenney {pack}: done")


def fetch_bigsoundbank(spec: dict, root: Path, entries: dict) -> None:
    """Each search result's page must carry the CC0 line; its Ogg file is downloaded as is."""
    out = root / "bigsoundbank"
    out.mkdir(parents=True, exist_ok=True)
    for q in spec["queries"]:
        html = get(spec["search"].format(q=urllib.parse.quote(q))).decode(
            "utf-8", "replace"
        )
        for href in sorted(set(re.findall(r"href='(/[a-z0-9-]+-s(\d+)\.html)'", html))):
            sound_id = f"bigsoundbank_{href[1]}"
            target = out / f"{href[1]}.ogg"
            if sound_id in entries and target.exists():
                if q not in entries[sound_id]["tags"]:
                    entries[sound_id]["tags"].append(q)
                continue
            page = get(spec["page"].format(href=href[0])).decode("utf-8", "replace")
            if "CC0 (public domain)" not in page:
                print(f"bigsoundbank {href[0]}: not CC0, skipped")
                continue
            title = re.search(r"<title>(.*?) —", page)
            name = unescape(title.group(1)) if title else href[0]
            if re.search(spec.get("skip_title", "^$"), name.lower()):
                continue  # search noise (music boxes, cameras, cars...), see library_sources.json
            if not target.exists():
                target.write_bytes(get(spec["file"].format(id=href[1])))
            entries[sound_id] = {
                "title": name,
                "source": "bigsoundbank",
                "licence": spec["licence"],
                "tags": [q],
                "path": str(target),
                "seconds": probe_seconds(target),
            }
            if entries[sound_id]["seconds"] > spec.get("max_s", 1e9):
                target.unlink()  # a long ambience recording: too big for the disk it would earn
                del entries[sound_id]
        print(f"bigsoundbank {q}: done")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--only", choices=["mixkit", "kenney", "opengameart", "bigsoundbank", "index"]
    )
    args = ap.parse_args()
    spec = json.loads((HERE / "library_sources.json").read_text())
    root = Path(spec["library_dir"]).expanduser()
    root.mkdir(parents=True, exist_ok=True)
    index = root / "library.json"
    entries = json.loads(index.read_text())["entries"] if index.exists() else {}
    if args.only in (None, "kenney"):
        fetch_kenney(spec["kenney"], root, entries)
    if args.only == "index":
        index_mixkit_files(spec["mixkit"], root, entries)
    if args.only in (None, "opengameart"):
        fetch_opengameart(spec["opengameart"], root, entries)
    if args.only in (None, "bigsoundbank"):
        fetch_bigsoundbank(spec["bigsoundbank"], root, entries)
    if args.only in (None, "mixkit"):
        fetch_mixkit(spec["mixkit"], root, entries)
    if index.exists():  # another run may have added entries meanwhile: keep them
        entries = {**json.loads(index.read_text())["entries"], **entries}
    index.write_text(
        json.dumps(
            {"_about": spec["_about"], "entries": entries}, indent=1, sort_keys=True
        )
    )
    size = sum(p.stat().st_size for p in root.rglob("*") if p.is_file()) / 1e6
    print(f"{len(entries)} sounds, {size:.0f} MB in {root}")


if __name__ == "__main__":
    main()
