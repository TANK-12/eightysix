"""
A PulseForge project: one song plus the scene, assets and format chosen for it.

Layout under ~/PulseForgeData/projects/<slug>/:
    project.json     name, audio filename, scene id + params, asset list, format id
    audio.<ext>      the imported song (copied in)
    assets/          uploaded background images; a clips folder lives here too
    cache/           features_<fps>.npz  (a few MB)
    renders/         finished MP4s
"""

import json
import os
import re
import shutil
import time
from pathlib import Path

from . import config, formats

PROJECTS_DIR = config.PROJECTS_DIR


def slugify(name):
    s = re.sub(r"[^a-zA-Z0-9._ -]", "", name).strip().replace(" ", "-").lower()
    return s or f"project-{int(time.time())}"


class Project:
    def __init__(self, slug):
        self.slug = slug
        self.dir = PROJECTS_DIR / slug
        self.data = {
            "name": slug,
            "audio": "",  # basename inside self.dir
            "scene": "living",  # the flagship; see scenes/living.py
            "params": {},
            "assets": [],  # basenames inside assets/ (files) or "clips/" dir
            # v3: a project is a playlist of songs and a list of shots. The
            # single-song "audio" field above still works and is treated as a
            # one-entry playlist, so older projects open unchanged.
            "playlist": [],  # basenames inside the project dir, in play order
            "cards": [],  # per-song {title, subtitle}, parallel to playlist
            "song_gap": 0.0,  # silence between songs, seconds
            "song_crossfade": 0.0,  # or overlap them by this many seconds
            "shots": [],  # see scenes/living.py for a shot's shape
            # repeat the playlist until the video reaches this many seconds
            # (0 = play it once). Six tracks -> three hours, no new files.
            "target_seconds": 0.0,
            "song_gain": [],  # per-song dB trim, parallel to the playlist
            "fade_in": 0.0,  # seconds of fade at the very start
            "fade_out": 0.0,  # and at the end
            # a generated bed under the music: see ambience.py
            "ambience": {"bed": "", "level": 0.25},
            # drawn over the finished video in the assembly pass
            "overlay": {
                "now_playing": False,
                "progress": False,
                "position": "bottom-left",
                "opacity": 0.8,
            },
            "format": formats.DEFAULT_FORMAT,
            "title_text": "",  # drawn over the finished video
            "subtitle_text": "",
            "text_position": "bottom-left",  # bottom-left|bottom-center|top-left|center
            "text_size": "m",  # s|m|l
            "created": time.time(),
        }
        if self.path().exists():
            try:
                self.data.update(json.loads(self.path().read_text("utf-8")))
            except Exception:
                pass

    # ---- paths ----
    def path(self):
        return self.dir / "project.json"

    def assets_dir(self):
        d = self.dir / "assets"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def cache_dir(self):
        d = self.dir / "cache"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def renders_dir(self):
        d = self.dir / "renders"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def masks_dir(self):
        """Brush masks painted in the Scenery editor, one PNG per region."""
        d = self.dir / "masks"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def thumbs_dir(self):
        d = self.dir / "renders" / "thumbs"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def audio_path(self):
        if not self.data.get("audio"):
            return None
        return str(self.dir / self.data["audio"])

    def asset_paths(self):
        out = []
        for a in self.data.get("assets", []):
            p = self.assets_dir() / a
            if p.exists():
                out.append(str(p))
        return out

    def features_path(self, fps):
        return self.cache_dir() / f"features_{int(fps)}.npz"

    # ---- playlist ----
    def playlist_paths(self):
        """Every song in order, absolute. Falls back to the single `audio`
        field so a project made before the playlist existed still renders."""
        out = []
        for name in self.data.get("playlist") or []:
            p = self.dir / name
            if p.exists():
                out.append(str(p))
        if not out:
            one = self.audio_path()
            if one and os.path.exists(one):
                out.append(one)
        return out

    def add_song(self, src_path, original_name):
        ext = os.path.splitext(original_name)[1].lower() or ".mp3"
        stem = slugify(os.path.splitext(original_name)[0]) or "song"
        dst = self.dir / f"{stem}{ext}"
        n = 2
        while dst.exists():
            dst = self.dir / f"{stem}-{n}{ext}"
            n += 1
        self.dir.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src_path, dst)
        self.data.setdefault("playlist", []).append(dst.name)
        self.data.setdefault("cards", []).append(
            {"title": os.path.splitext(original_name)[0], "subtitle": ""}
        )
        if not self.data.get("audio"):
            self.data["audio"] = dst.name
        self.invalidate_analysis()
        self.save()
        return dst.name

    def remove_song(self, name):
        pl = self.data.get("playlist") or []
        if name in pl:
            i = pl.index(name)
            pl.pop(i)
            cards = self.data.get("cards") or []
            if i < len(cards):
                cards.pop(i)
        f = self.dir / name
        if f.exists() and f.is_file() and f.parent == self.dir:
            f.unlink()
        if self.data.get("audio") == name:
            self.data["audio"] = pl[0] if pl else ""
        self.invalidate_analysis()
        self.save()

    def reorder_playlist(self, order):
        """`order` is the new list of basenames; cards follow their song."""
        pl = self.data.get("playlist") or []
        cards = self.data.get("cards") or []
        by_name = {n: (cards[i] if i < len(cards) else {}) for i, n in enumerate(pl)}
        keep = [n for n in order if n in by_name]
        keep += [n for n in pl if n not in keep]
        self.data["playlist"] = keep
        self.data["cards"] = [by_name.get(n, {}) for n in keep]
        self.save()

    def invalidate_analysis(self):
        for f in self.cache_dir().glob("features_*.npz"):
            f.unlink(missing_ok=True)

    # ---- mutation ----
    def save(self):
        self.dir.mkdir(parents=True, exist_ok=True)
        self.path().write_text(
            json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def set_audio(self, src_path, original_name):
        ext = os.path.splitext(original_name)[1].lower() or ".mp3"
        dst = self.dir / f"audio{ext}"
        self.dir.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src_path, dst)
        self.invalidate_analysis()
        self.data["audio"] = dst.name
        if not self.data.get("playlist"):
            self.data["playlist"] = [dst.name]
            self.data["cards"] = [{"title": "", "subtitle": ""}]
        self.save()

    def add_asset(self, src_path, original_name):
        safe = (
            slugify(os.path.splitext(original_name)[0])
            + os.path.splitext(original_name)[1].lower()
        )
        dst = self.assets_dir() / safe
        shutil.copyfile(src_path, dst)
        if safe not in self.data["assets"]:
            self.data["assets"].append(safe)
        self.save()
        return safe

    def link_clips_folder(self, folder_path):
        """Register an external folder of video clips for the montage scene.
        Stored as an absolute path entry (not copied -- clip libraries are big)."""
        folder_path = str(Path(folder_path).expanduser())
        if os.path.isdir(folder_path) and folder_path not in self.data["assets"]:
            self.data["assets"].append(folder_path)
            self.save()
        return folder_path

    def remove_asset(self, name):
        if name in self.data["assets"]:
            self.data["assets"].remove(name)
        p = self.assets_dir() / name
        if p.exists() and p.is_file():
            p.unlink()
        self.save()

    def resolved_assets(self):
        """Absolute paths for the render: copied files under assets/, plus any
        registered absolute clip-folder paths."""
        out = []
        for a in self.data.get("assets", []):
            if os.path.isabs(a) and os.path.isdir(a):
                out.append(a)
            else:
                p = self.assets_dir() / a
                if p.exists():
                    out.append(str(p))
        return out

    def summary(self):
        ap = self.audio_path()
        return {
            "slug": self.slug,
            "name": self.data.get("name", self.slug),
            "scene": self.data.get("scene"),
            "format": self.data.get("format"),
            "has_audio": bool(self.playlist_paths()),
            "songs": len(self.playlist_paths()),
            "shots": len(self.data.get("shots") or []),
            "assets": self.data.get("assets", []),
            "renders": sorted(p.name for p in self.renders_dir().glob("*.mp4")),
        }


def list_projects():
    if not PROJECTS_DIR.exists():
        return []
    return sorted(
        p.name
        for p in PROJECTS_DIR.iterdir()
        if p.is_dir() and (p / "project.json").exists()
    )


# a project folder name; longer names keep their full text in project.json
SLUG_MAX = 80


def create(name, unique=False):
    """Make (or, for a name already in use, reopen) a project.

    `unique` always makes a new folder, adding -2, -3 ... to a slug in use, so
    a copy can never land on top of another project. Without it, only the very
    same name reopens: "Song!" and "Song?" share a slug but are two projects."""
    slug = slugify(name)[:SLUG_MAX]
    if not slug.strip("."):  # "." and ".." would point outside projects/
        slug = f"project-{int(time.time())}"
    if not unique and (PROJECTS_DIR / slug).exists():
        unique = Project(slug).data.get("name") != name
    if unique:
        base, n = slug, 2
        while (PROJECTS_DIR / slug).exists():
            slug, n = f"{base}-{n}", n + 1
    p = Project(slug)
    p.data["name"] = name
    p.save()
    return p


def delete(slug):
    if not slug.strip(".") or "/" in slug or "\\" in slug:
        return  # never anything but a folder directly inside projects/
    d = PROJECTS_DIR / slug
    if d.exists():
        shutil.rmtree(d, ignore_errors=True)
