"""
The scene registry.

Adding a scene is one file in this folder that defines `SCENE` (metadata +
param schema) and `frames(ctx)` (a generator of (H, W, 3) uint8 frames at the
internal render size), plus one line in `_MODULES` below. Nothing else in the
app needs to change -- the API, the picker UI and the render pipeline are all
driven off this table.

Families: "visualizer" | "scenery" | "sprites" | "montage" | "amv".

"montage" and "amv" do not yield frames at all -- they define `build_edl(ctx)`
and the renderer assembles their shots with ffmpeg instead. The registry does
not care; `frames` raising is their contract.
"""

import importlib
from typing import Callable, Optional

_MODULES = [
    "pulseforge.scenes.bars",
    "pulseforge.scenes.living",
    "pulseforge.scenes.drift",
    "pulseforge.scenes.swarm",
    "pulseforge.scenes.aurora",
    "pulseforge.scenes.tunnel",
    "pulseforge.scenes.scope",
    "pulseforge.scenes.montage",
    "pulseforge.scenes.amv",
]

from .. import particles as _particles  # noqa: E402

# Frame-based families get the particle layer's params (pulseforge/particles.py).
_PARTICLE_FAMILIES = ("visualizer", "scenery", "sprites")

SCENES = {}
_FRAME_FNS = {}

for _mod_name in _MODULES:
    try:
        _m = importlib.import_module(_mod_name)
        if _m.SCENE.get("family") in _PARTICLE_FAMILIES:
            _m.SCENE["params"] = list(_m.SCENE.get("params", [])) + _particles.PARAMS
        SCENES[_m.SCENE["id"]] = _m.SCENE
        _FRAME_FNS[_m.SCENE["id"]] = _m.frames
    except Exception as e:  # pragma: no cover - a broken scene shouldn't kill the app
        print(f"[pulseforge] scene {_mod_name} failed to load: {e}")


class SceneContext:
    """Everything a scene's frames() generator needs.

    `progress` is set by the renderer for scenes whose *planning* is slow --
    the AMV scene has to look at every clip before it can decide anything, and
    that is the part worth a progress bar. Frame-generating scenes leave it
    alone."""

    def __init__(
        self,
        w,
        h,
        fps,
        n_frames,
        duration,
        feat,
        params,
        assets,
        art_pack,
        tmpdir,
        fast=False,
    ):
        self.w = w
        self.h = h
        self.fps = fps
        self.n_frames = n_frames
        self.duration = duration
        self.feat = feat  # dict of numpy arrays from analyze.analyze()
        self.params = params or {}
        self.assets = assets or []  # absolute paths: images and/or a clips dir
        self.art_pack = art_pack  # loaded ForgeArtData pack dict, or None
        self.tmpdir = tmpdir
        self.fast = fast  # draft quality -> scenes may use cheaper resampling
        # Set by the renderer for scenes whose planning is slow enough to be
        # worth reporting; takes a 0..1 fraction. None means nobody is watching.
        self.progress: Optional[Callable[[float], None]] = None

    def p(self, key, default=None):
        return self.params.get(key, default)

    def frame_feat(self, name, i):
        """Safe per-frame lookup that clamps to the array's length."""
        arr = self.feat.get(name)
        if arr is None or len(arr) == 0:
            return 0.0
        return arr[min(i, len(arr) - 1)]


def get_scene(scene_id):
    if scene_id not in SCENES:
        raise KeyError(f"no such scene: {scene_id}")
    return SCENES[scene_id], _FRAME_FNS[scene_id]


def scenes_as_list():
    order = {"visualizer": 0, "scenery": 1, "sprites": 2, "montage": 3}
    return sorted(
        ({"id": k, **v} for k, v in SCENES.items()),
        key=lambda s: (order.get(str(s.get("family") or ""), 9), s["id"]),
    )
