"""
Autopilot: a folder of songs in, a folder of upload-ready packages out.

A run picks a recipe (see `pulseforge/recipes/`), builds one ordinary project per
song, renders them one after another inside a single job, and for each finished
render writes `<AUTOPILOT_DIR>/ready/<slug>/` holding the video, a thumbnail, the
upload text and a checklist. Nothing is uploaded -- publishing stays a person's
decision.

State lives in two small JSON files beside the packages:

* `packages.json` -- one record per song+recipe, so a second run over the same
  inbox skips what is already queued, ready or uploaded (a failed one is retried);
* `ledger.json` -- the views and revenue typed in from YouTube Studio, one entry
  per video per month. Nothing is estimated; the ledger only adds up what it is
  given.

The renderer is passed in (`render_fn`) rather than imported, so the web app
supplies the real one and the tests can too without a server.
"""

import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import threading
import time

from pulseforge import config
from pulseforge import ffrunner as ffmod
from pulseforge import jan as janmod
from pulseforge import project as projmod
from pulseforge import render as rendermod
from pulseforge.recipes import get_recipe

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
# a mix named after one of these folders gets the recipe's name instead
GENERIC_FOLDERS = {
    "inbox",
    "songs",
    "music",
    "audio",
    "tracks",
    "new",
    "mix",
    "downloads",
}
_lock = threading.Lock()


def root():
    """Read at call time so tests can point it somewhere else."""
    return config.AUTOPILOT_DIR


def _load(name, default):
    f = root() / name
    try:
        return json.loads(f.read_text())
    except (OSError, ValueError):
        return default


def _save(name, data):
    root().mkdir(parents=True, exist_ok=True)
    f = root() / name
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2))
    tmp.replace(f)


def packages():
    return _load("packages.json", {})


def _update_package(slug, **fields):
    with _lock:
        pk = packages()
        pk.setdefault(slug, {"slug": slug}).update(fields)
        _save("packages.json", pk)
        return pk[slug]


# --------------------------------------------------------------------------
# inbox
# --------------------------------------------------------------------------
def _files(folder, exts):
    return sorted(
        os.path.join(folder, f)
        for f in os.listdir(folder)
        if os.path.splitext(f)[1].lower() in exts
        and os.path.isfile(os.path.join(folder, f))
    )


def song_title(path):
    """'03 - lazy_sunday-FINAL.mp3' -> 'Lazy Sunday'."""
    stem = os.path.splitext(os.path.basename(path))[0]
    stem = re.sub(r"^\s*\d{1,3}\s*[-_. ]\s*", "", stem)
    stem = re.sub(r"[-_ ](final|master|mix|v\d+)$", "", stem, flags=re.I)
    stem = re.sub(r"[_]+", " ", stem).strip(" -.")
    if stem and (stem.islower() or stem.isupper()):
        stem = stem.title()
    return stem or "Untitled"


def plan_run(inbox, recipe_id, art=None):
    """What a run would do: ([item, ...], [skipped names]).

    An item is one video: `{"songs", "images", "slug", "title", "key"}`. A
    recipe with `"per": "song"` (the default) makes one item per song, each with
    one picture from the rotation; `"per": "folder"` makes a single mix of every
    song with every picture. A folder item's key includes the song names, so
    adding a song to the inbox makes a new mix rather than being skipped.

    Raises ValueError for a bad folder or recipe, LookupError for an empty inbox.
    """
    inbox = os.path.expanduser(inbox or "")
    if not os.path.isdir(inbox):
        raise ValueError("that inbox is not a folder")
    try:
        recipe = get_recipe(recipe_id)
    except KeyError:
        raise ValueError(f"no recipe called {recipe_id!r}")
    songs = _files(inbox, config.AUDIO_EXTS)
    if not songs:
        raise LookupError("there are no audio files in that folder")
    images = []
    if art:
        art = os.path.expanduser(art)
        if not os.path.isdir(art):
            raise ValueError("that pictures folder is not a folder")
        images = _files(art, IMAGE_EXTS)
    if recipe.get("needs_art") and not images:
        raise ValueError(f"{recipe['label']} needs a pictures folder")

    done = {
        rec.get("key")
        for rec in packages().values()
        if rec.get("status") in ("queued", "rendering", "ready", "uploaded")
    }
    if recipe.get("per") == "folder":
        folder = os.path.basename(os.path.abspath(inbox)) or "mix"
        title = song_title(folder)
        if folder.lower() in GENERIC_FOLDERS:
            title = recipe["label"]
        names = "+".join(os.path.basename(x) for x in songs)
        digest = hashlib.sha1(names.encode()).hexdigest()[:8]
        wanted = [
            {
                "songs": songs,
                "images": images,
                "slug": projmod.slugify(f"autopilot {recipe['id']} {folder} {digest}"),
                "title": title,
                "key": f"{os.path.abspath(inbox)}|{recipe['id']}|{digest}",
            }
        ]
    else:
        wanted = [
            {
                "songs": [song],
                "images": [images[i % len(images)]] if images else [],
                "slug": projmod.slugify(f"autopilot {recipe['id']} {song_title(song)}"),
                "title": song_title(song),
                "key": f"{os.path.abspath(song)}|{recipe['id']}",
            }
            for i, song in enumerate(songs)
        ]
    todo, skipped = [], []
    for item in wanted:
        if item["key"] in done:
            skipped.append(_label(item))
        else:
            todo.append(item)
    return todo, skipped


def _label(item):
    songs = item["songs"]
    return os.path.basename(songs[0]) if len(songs) == 1 else f"{len(songs)} songs"


def new_project(name, audio, scene, fmt, params, images=()):
    """One ready-to-render project. Shared with the album batch route.

    `audio` is one path, or a list that becomes the playlist in order."""
    p = projmod.create(name)
    p.data["scene"] = scene
    p.data["format"] = fmt
    p.data["params"] = dict(params)
    p.save()
    if isinstance(audio, (list, tuple)):
        p.data["playlist"], p.data["cards"], p.data["audio"] = [], [], None
        for a in audio:
            p.add_song(a, os.path.basename(a))
        # the now-playing caption and the chapters read these
        p.data["cards"] = [{"title": song_title(a), "subtitle": ""} for a in audio]
        p.save()
    else:
        p.set_audio(audio, os.path.basename(audio))
    for img in images:
        p.add_asset(img, os.path.basename(img))
    return p


# --------------------------------------------------------------------------
# the run
# --------------------------------------------------------------------------
def queue_songs(todo, recipe_id):
    """Record the plan as 'queued' so the page shows it straight away."""
    for item in todo:
        _update_package(
            item["slug"],
            key=item["key"],
            song=_label(item),
            recipe=recipe_id,
            title=item["title"],
            status="queued",
            created=time.strftime("%Y-%m-%dT%H:%M:%S"),
            url=None,
            error=None,
        )


def run(
    todo,
    recipe_id,
    render_fn,
    log=print,
    progress=None,
    should_stop=None,
    prepare_fn=None,
    chapters_fn=None,
):
    """Render and package each item in turn. Returns the slugs that finished.

    `render_fn(project, scene, params, fmt, out_path, log, progress, should_stop)`
    renders one video and returns the renderer's result dict.
    `prepare_fn(project, recipe)` finishes setting a project up before it
    renders (the living-still scenes need shots and a look) and returns the
    project reloaded. `chapters_fn(project)` returns the chapter list for the
    description, or "".
    """
    recipe = get_recipe(recipe_id)
    finished = []
    n = len(todo)
    for i, item in enumerate(todo):
        slug, title = item["slug"], item["title"]
        if should_stop and should_stop():
            _update_package(slug, status="failed", error="stopped")
            continue
        log(f"[{i + 1}/{n}] {title}")
        _update_package(slug, status="rendering")

        def sub_progress(frac, i=i):
            if progress:
                progress((i + max(0.0, min(1.0, frac))) / n)

        try:
            songs = item["songs"]
            p = new_project(
                slug,
                songs if recipe.get("per") == "folder" else songs[0],
                recipe["scene"],
                recipe["format"],
                recipe.get("params") or {},
                item["images"],
            )
            if prepare_fn:
                p = prepare_fn(p, recipe)
            out = p.renders_dir() / f"{p.slug}_{recipe['format']}.mp4"
            params = dict(recipe.get("params") or {})
            params["_assets"] = p.resolved_assets()
            res = render_fn(
                p,
                recipe["scene"],
                params,
                recipe["format"],
                str(out),
                log,
                sub_progress,
                should_stop or (lambda: False),
            )
            if recipe.get("minutes"):
                # render the playlist once, then repeat the finished file
                # without re-encoding: an hour costs one pass plus a copy
                one = out.with_name(out.stem + "_pass.mp4")
                out.replace(one)
                res["duration"] = repeat_video(
                    str(one), str(out), float(recipe["minutes"]) * 60.0
                )
                one.unlink()
            chapters = chapters_fn(p) if chapters_fn and len(songs) > 1 else ""
            make_package(
                slug,
                str(out),
                recipe,
                title,
                res.get("duration") or 0.0,
                log,
                tracks=[song_title(x) for x in songs],
                chapters=chapters,
            )
            finished.append(slug)
        except Exception as e:  # noqa: BLE001 - one bad item must not stop the rest
            log(f"  failed: {e}")
            _update_package(slug, status="failed", error=str(e))
    if progress:
        progress(1.0)
    return finished


def repeat_video(src, dst, seconds):
    """`src` played round and round to `seconds`, stream-copied. Returns the
    real length. Safe because a pass has no fade in or out by default."""
    ff = config.ffmpeg_caps()
    one = ffmod.probe_media(src)["duration"] or 1.0
    loops = max(0, math.ceil(seconds / one) - 1)
    r = subprocess.run(
        [
            ff["ffmpeg"],
            "-y",
            "-v",
            "error",
            "-stream_loop",
            str(loops),
            "-i",
            src,
            "-t",
            f"{seconds:.3f}",
            "-c",
            "copy",
            "-movflags",
            "+faststart",
            dst,
        ],
        capture_output=True,
        text=True,
    )
    if r.returncode != 0:
        raise RuntimeError(f"could not repeat the video: {r.stderr[-300:]}")
    return ffmod.probe_media(dst)["duration"] or seconds


# --------------------------------------------------------------------------
# the package
# --------------------------------------------------------------------------
def package_dir(slug):
    return root() / "ready" / slug


def length_words(seconds):
    """3540 -> '1 hour', 5400 -> '1.5 hours', 180 -> '3 minutes'."""
    if seconds >= 3000:
        hours = round(seconds / 1800.0) / 2
        n = f"{hours:g}"
        return f"{n} hour" if hours == 1 else f"{n} hours"
    m = max(1, round(seconds / 60.0))
    return "1 minute" if m == 1 else f"{m} minutes"


def subtitle(recipe, seconds):
    return recipe.get("thumb_subtitle", "").replace("{length}", length_words(seconds))


def tagline(recipe, seconds):
    """The half of a template title after the '|'; `{length}` filled in."""
    return recipe.get("tagline", "").replace("{length}", length_words(seconds))


def upload_text(title, recipe, minutes, tracks=None):
    """Title, description and tags. Jan drafts them when it is up; a plain
    template stands in when it is not, so a run never stalls on the model."""
    try:
        d = janmod.write_upload_text(
            tracks or [title], minutes, mood=recipe.get("mood", "")
        )
        if d.get("title"):
            return {
                "title": d["title"],
                "blurb": d["blurb"],
                "tags": d["tags"],
                "by": "jan",
            }
    except Exception:  # noqa: BLE001 - Jan down, busy or off-script
        pass
    sub = subtitle(recipe, minutes * 60.0) or recipe["label"].lower()
    return {
        "title": f"{title} | {tagline(recipe, minutes * 60.0) or sub}",
        "blurb": (
            f"{title}, set to a {recipe['label'].lower()} visual. "
            f"{recipe.get('mood', '').capitalize()}. "
            "Put it on while you study, work or wind down."
        ).replace(" . ", " "),
        "tags": [w for w in re.split(r"[,/]\s*|\s+", sub.lower()) if len(w) > 2][:6]
        + [title.lower(), "music", "visualizer"],
        "by": "template",
    }


CHECKLIST = """Before you upload {title}

1. Rights: the music and any pictures in this video must be yours, licensed to
   you, or free for commercial use. Otherwise YouTube's Content ID will claim
   it and the money goes to the owner, not you.
2. Watch the whole video once. Check the start, the end and the loudest part.
3. Upload video.mp4. Paste the title, description and tags from upload.txt.
4. Set thumb.jpg as the custom thumbnail.
5. Choose "No, it's not made for kids" unless it is, and turn on monetisation
   if the channel is in the Partner Programme.
6. Back in PulseForge, press "Mark uploaded" and paste the video link, then
   type the views and revenue from YouTube Studio each month in Earnings.
"""


def make_package(
    slug, video, recipe, title, duration, log=print, tracks=None, chapters=""
):
    d = package_dir(slug)
    d.mkdir(parents=True, exist_ok=True)
    dst = d / "video.mp4"
    if dst.exists():
        dst.unlink()
    try:
        os.link(video, dst)  # same disk: no second copy of the video
    except OSError:
        shutil.copyfile(video, dst)

    fmt_w, fmt_h = (720, 1280) if "shorts" in recipe["format"] else (1280, 720)
    thumb = d / "thumb.jpg"
    rendermod.grab_thumbnail(
        str(dst),
        str(thumb),
        t_seconds=max(0.0, min(duration * 0.4, duration - 0.5)),
        width=fmt_w,
        height=fmt_h,
        title=title,
        subtitle=subtitle(recipe, duration),
        position="bottom-left",
        pop=0.2,
    )

    text = upload_text(title, recipe, duration / 60.0, tracks)
    blurb = text["blurb"] + (f"\n\n{chapters.strip()}" if chapters else "")
    (d / "upload.txt").write_text(
        f"Title\n{text['title']}\n\nDescription\n{blurb}\n\n"
        f"Tags\n{', '.join(text['tags'])}\n"
    )
    (d / "CHECKLIST.txt").write_text(CHECKLIST.format(title=title))
    log(f"  ready: {d}  (text by {text['by']})")
    return _update_package(
        slug,
        status="ready",
        title=text["title"],
        dir=str(d),
        error=None,
        text={"title": text["title"], "description": blurb, "tags": text["tags"]},
    )


def upload_text_of(slug):
    """{title, description, tags} for a package, for the copy buttons.

    Packages made before the text was stored read it back from upload.txt."""
    rec = packages().get(slug)
    if rec is None:
        raise KeyError(slug)
    if rec.get("text"):
        return rec["text"]
    f = package_dir(slug) / "upload.txt"
    if not f.exists():
        raise KeyError(slug)
    parts = re.split(r"^(Title|Description|Tags)\n", f.read_text(), flags=re.M)
    got = {parts[i]: parts[i + 1].strip() for i in range(1, len(parts) - 1, 2)}
    return {
        "title": got.get("Title", ""),
        "description": got.get("Description", ""),
        "tags": [t.strip() for t in got.get("Tags", "").split(",") if t.strip()],
    }


# --------------------------------------------------------------------------
# helpers for the Autopilot page: folder browser, folder scan, look previews
# --------------------------------------------------------------------------
def _count(folder):
    songs = pictures = 0
    try:
        for f in os.listdir(folder):
            ext = os.path.splitext(f)[1].lower()
            songs += ext in config.AUDIO_EXTS
            pictures += ext in IMAGE_EXTS
    except OSError:
        pass
    return songs, pictures


def browse(path=None):
    """One level of folders under the home directory, each with its counts.

    Refuses anything outside home: the page only ever needs music and picture
    folders, and a folder picker has no business listing the whole disk."""
    home = os.path.realpath(os.path.expanduser("~"))
    path = os.path.realpath(os.path.expanduser(path or "~"))
    if path != home and not path.startswith(home + os.sep):
        raise ValueError("only folders inside your home folder can be browsed")
    if not os.path.isdir(path):
        raise ValueError("that is not a folder")
    dirs = []
    for name in sorted(os.listdir(path), key=str.lower):
        full = os.path.join(path, name)
        if name.startswith(".") or not os.path.isdir(full):
            continue
        songs, pictures = _count(full)
        dirs.append({"name": name, "path": full, "songs": songs, "pictures": pictures})
    songs, pictures = _count(path)
    first = _files(path, IMAGE_EXTS)[:1]
    return {
        "first_picture": first[0] if first else None,
        "path": path,
        "parent": None if path == home else os.path.dirname(path),
        "home": home,
        "dirs": dirs,
        "songs": songs,
        "pictures": pictures,
    }


def scan(inbox, art, recipe_id):
    """What the Make button would do, in words the page can show as-is."""
    from pulseforge import sequence

    out = {"songs": 0, "minutes": 0.0, "pictures": 0, "to_make": 0, "skipped": 0}
    out["first_picture"] = None
    out["problem"] = None
    if inbox:
        folder = os.path.expanduser(inbox)
        if os.path.isdir(folder):
            songs = _files(folder, config.AUDIO_EXTS)
            out["songs"] = len(songs)
            out["minutes"] = round(sum(sequence.song_durations(songs)) / 60.0, 1)
    if art:
        folder = os.path.expanduser(art)
        if os.path.isdir(folder):
            pics = _files(folder, IMAGE_EXTS)
            out["pictures"] = len(pics)
            out["first_picture"] = pics[0] if pics else None
    try:
        todo, skipped = plan_run(inbox, recipe_id, art or None)
        out["to_make"], out["skipped"] = len(todo), len(skipped)
    except (ValueError, LookupError) as e:
        out["problem"] = str(e)
    return out


def preview_path(recipe_id, image, width):
    """Where a look preview is cached: keyed on the picture's mtime too, so
    replacing a picture refreshes its preview."""
    stamp = os.path.getmtime(image) if image and os.path.exists(image) else 0
    key = f"{recipe_id}|{image}|{stamp}|{width}"
    name = hashlib.sha1(key.encode()).hexdigest()[:16] + ".png"
    return root() / "previews" / name


def sample_features(n=30, bands=12):
    """A made-up bar of music: steady mid energy, a bass-heavy spectrum that
    breathes a little, one beat. Enough for a frame scene to look like itself
    without analysing a real song."""
    import numpy as np

    t = np.arange(n)
    shape = np.linspace(0.95, 0.35, bands) ** 1.3
    wobble = 0.12 * np.sin(t[:, None] * 0.7 + np.arange(bands)[None, :])
    return {
        "energy": np.full(n, 0.6),
        "sub": np.full(n, 0.7),
        "centroid": np.full(n, 0.4),
        "bands": np.clip(shape[None, :] + wobble, 0, 1),
        "onset": np.zeros(n),
        "beat": np.zeros(n, dtype=bool),
    }


def preview_frame(recipe, image, width=480):
    """One frame of a frame-based recipe (drift, bars) as an RGB array."""
    from pulseforge import formats
    from pulseforge.scenes.registry import SceneContext, get_scene

    meta, frame_fn = get_scene(recipe["scene"])
    fmt = formats.get(recipe["format"])
    w = int(round(width / 2) * 2)
    h = int(round(w * fmt["h"] / fmt["w"] / 2) * 2)
    params = {sp["key"]: sp.get("default") for sp in meta.get("params", [])}
    params.update(recipe.get("params") or {})
    n = 24
    ctx = SceneContext(
        w,
        h,
        fmt["fps"],
        n,
        n / fmt["fps"],
        sample_features(n),
        params,
        [image] if image else [],
        None,
        None,
        fast=True,
    )
    frame = None
    for i, frame in enumerate(frame_fn(ctx)):
        if i >= n - 1:
            break
    if frame is None:
        raise RuntimeError("the scene drew nothing")
    return frame


def package_list():
    out = []
    for slug, rec in packages().items():
        d = package_dir(slug)
        out.append(
            {
                "slug": slug,
                "song": rec.get("song"),
                "recipe": rec.get("recipe"),
                "title": rec.get("title"),
                "status": rec.get("status"),
                "error": rec.get("error"),
                "dir": str(d),
                "video": (d / "video.mp4").exists(),
                "thumb": (
                    f"/api/autopilot/thumb/{slug}"
                    if (d / "thumb.jpg").exists()
                    else None
                ),
                "created": rec.get("created"),
                "url": rec.get("url"),
            }
        )
    out.sort(key=lambda r: r.get("created") or "", reverse=True)
    return out


# --------------------------------------------------------------------------
# earnings ledger
# --------------------------------------------------------------------------
MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


def mark_uploaded(slug, url):
    if slug not in packages():
        raise KeyError(slug)
    _update_package(slug, status="uploaded", url=(url or "").strip() or None)


def record_figures(slug, month, views, revenue):
    if slug not in packages():
        raise KeyError(slug)
    if not MONTH_RE.match(str(month)):
        raise ValueError("month must look like 2026-09")
    views, revenue = int(views), round(float(revenue), 2)
    if views < 0 or revenue < 0:
        raise ValueError("views and revenue cannot be negative")
    with _lock:
        led = _load("ledger.json", {"entries": []})
        led["entries"] = [
            e for e in led["entries"] if not (e["slug"] == slug and e["month"] == month)
        ]
        led["entries"].append(
            {"slug": slug, "month": month, "views": views, "revenue": revenue}
        )
        led["entries"].sort(key=lambda e: (e["month"], e["slug"]))
        _save("ledger.json", led)


def ledger():
    pk = packages()
    entries = _load("ledger.json", {"entries": []})["entries"]
    per_video = {}
    for slug, rec in pk.items():
        if rec.get("status") == "uploaded" or any(e["slug"] == slug for e in entries):
            per_video[slug] = {
                "slug": slug,
                "title": rec.get("title") or rec.get("song"),
                "recipe": rec.get("recipe"),
                "url": rec.get("url"),
                "views": 0,
                "revenue": 0.0,
            }
    for e in entries:
        v = per_video.get(e["slug"])
        if v:
            v["views"] += e["views"]
            v["revenue"] = round(v["revenue"] + e["revenue"], 2)
    per_recipe = {}
    for v in per_video.values():
        r = per_recipe.setdefault(
            v["recipe"],
            {"recipe": v["recipe"], "videos": 0, "views": 0, "revenue": 0.0},
        )
        r["videos"] += 1
        r["views"] += v["views"]
        r["revenue"] = round(r["revenue"] + v["revenue"], 2)
    vids = sorted(per_video.values(), key=lambda v: -v["revenue"])
    return {
        "per_video": vids,
        "per_recipe": sorted(per_recipe.values(), key=lambda r: -r["revenue"]),
        "total": {
            "views": sum(v["views"] for v in vids),
            "revenue": round(sum(v["revenue"] for v in vids), 2),
        },
        "entries": entries,
    }
