"""timeline.json: the automatic builder, edit-preserving merge and PUT checks.

`settings.height` is the short side of the output ("1080p"): 16:9 renders
1920x1080 and 9:16 renders 1080x1920.
"""

import copy
import re
from pathlib import Path

from ..camera import CameraSettings, DirectionState, PanelInfo, plan_shot
from ..camera import keys as K
from .. import store, transitions
from .inputs import ChapterInputs

DEFAULT_SETTINGS = {
    "aspect": "16:9",
    "height": 1080,
    "fps": 30,
    "style": "motion",
    "bubbles": "keep",
    "subtitles": True,
    # panel-to-panel, page-reveal, or scroll (read down the strip as drawn,
    # nothing cut: every shot gets a `scroll` plan and the scroll style)
    "mode": "panel-to-panel",
    "pace": 1.0,
    "motion_strength": 1.0,
    "transition": "auto",
    "allow_flip": False,
    "effects": 1.0,
    # what fills the frame around a panel: auto, blur, stretch or black
    "backdrop": "auto",
    # full (voices, sfx, music), music (sfx and music, no voices: a "just
    # watch" film timed by reading pace) or silent (no audio track)
    "sound": "full",
    # how much the cutout character layers move on their own in the 3D style
    # (0 = flat drawing with depth parallax only, 1 = full layering)
    "layers": 1.0,
}

EDITABLE = ("camera", "transition_in", "style", "dur", "lines", "sfx", "style_settings")


def out_size(settings: dict) -> tuple[int, int]:
    short = int(settings.get("height") or 1080)
    long = int(round(short * 16 / 9 / 2)) * 2
    return (short, long) if settings.get("aspect") == "9:16" else (long, short)


def camera_settings(settings: dict, reading: str = "ttb") -> CameraSettings:
    return CameraSettings(
        out=out_size(settings),
        pace=float(settings.get("pace", 1.0)),
        motion_strength=float(settings.get("motion_strength", 1.0)),
        allow_flip=bool(settings.get("allow_flip", False)),
        text_kept=settings.get("bubbles", "keep") == "keep",
        reading=reading,
        voiced=settings.get("sound", "full") == "full",
    )


def shot_id(panel_id: str, kind: str = "panel") -> str:
    m = re.fullmatch(r"p(\d+)", panel_id)
    core = m.group(1) if m else panel_id
    return ("r" if kind == "reveal" else "t") + core


SCROLL_SPEED = 1.4  # seconds to scroll one window height at pace 1
SCROLL_MARGIN = 0.04  # of the window height, air above and below a panel


def plan_scroll(inp: ChapterInputs, shots: list[dict], settings: dict) -> None:
    """Give every panel shot a continuous scroll plan (in place).

    The strip is shown whole width; a wide frame gives it `scroll_width` of
    the width, a tall frame all of it. Each shot moves the window from
    where the last one left it to a spot that shows its panel entirely
    (centred), or, for a panel taller than the window, from the panel's top
    to its bottom over the shot. Nothing is ever cropped inside a panel.
    """
    from .. import styles

    ow, oh = out_size(settings)
    W = int(inp.strip.get("width") or 800)
    strip_h = int(inp.strip.get("height") or 0) or max(
        int(p["box"][1] + p["box"][3]) for p in inp.panels
    )
    share = (
        1.0
        if settings.get("aspect") == "9:16"
        else float(
            settings.get("scroll_width")
            or ((settings.get("style_settings") or {}).get("scroll") or {}).get("width")
            or styles.REGISTRY["scroll"].settings["width"]["default"]
        )
    )
    s = min(ow * share / max(1, W), oh / max(1, W * 0.25))
    H = max(1, int(round(oh / s)))
    pace = max(0.2, float(settings.get("pace", 1.0)))
    margin = SCROLL_MARGIN * H
    clamp = lambda v: float(min(max(0.0, v), max(0.0, strip_h - H)))  # noqa: E731
    y_prev = None
    for shot in shots:
        if shot.get("kind") != "panel":
            continue
        x, y, w, h = [float(v) for v in inp.by_id[shot["panel_id"]]["box"]]
        if h + 2 * margin <= H:
            ya = yb = clamp(y + h / 2 - H / 2)
        else:
            ya, yb = clamp(y - margin), clamp(y + h + margin - H)
        y0 = ya if y_prev is None else y_prev
        dist = abs(ya - y0)
        dur = float(shot.get("dur", 1.0))
        move = (
            0.0
            if dist < 1
            else min(0.6 * dur, max(0.15, dist / H * SCROLL_SPEED / pace))
        )
        keys = _scroll_keys(inp, shot, y0, ya, yb, move, dur, H, margin, clamp)
        ys = [k[1] for k in keys] or [y0, ya, yb]
        lo, hi = min(ys), max(ys) + H
        shot["scroll"] = {
            "y0": round(y0, 1),
            "y_a": round(ya, 1),
            "y_b": round(yb, 1),
            "move": round(move, 3),
            "dur": dur,
            "strip_w": W,
            "window_h": H,
            "scale": round(s, 5),
            "band_y0": int(lo),
            "band_h": int(hi - lo) + 2,
            "keys": [[round(t, 3), round(v, 1)] for t, v in keys],
        }
        shot["style"] = "scroll"
        shot["transition_in"] = {"kind": "cut", "dur": 0.0, "auto": True}
        y_prev = yb


SCROLL_HOLD_GAP = 0.05  # seconds between one balloon's hold and the next move
SCROLL_MOVE_LEAD = 0.6  # seconds the glide to the next balloon takes


def _scroll_keys(inp, shot, y0, ya, yb, move, dur, H, margin, clamp) -> list:
    """[(shot time, window top y), ...] for a panel taller than the window:
    the window rests on each balloon while its line plays and moves
    between lines, instead of drifting top to bottom at one speed and
    leaving the words half out of view (seen on chapter 1). Panels that
    fit, or shots without lines, keep the plain move-then-drift and get
    no keys."""
    if abs(yb - ya) < 1 or not shot.get("lines"):
        return []
    boxes = {b["id"]: b["box"] for b in inp.panel_bubbles(shot.get("panel_id"))}
    keys = [(0.0, y0)]
    last_t = 0.0
    lines = sorted(shot["lines"], key=lambda l: float(l.get("at", 0.0)))
    first_at = float(lines[0].get("at", 0.0)) if lines else dur
    if move > 0 and move + SCROLL_HOLD_GAP < first_at:
        keys.append((move, ya))  # time to show the panel's top first
        last_t = move
    for ln in lines:
        box = boxes.get(ln.get("bubble_id"))
        if not box:
            continue
        bx, by, bw, bh = [float(v) for v in box]
        # centre the balloon; stay within the panel's own range unless the
        # balloon itself pokes out of the panel box (chapter 2: balloons
        # drawn over the gutter were cut at the top), then it wins
        lo, hi = min(ya, by - margin), max(yb, by + bh + margin - H)
        y_i = clamp(min(max(by + bh / 2 - H / 2, lo), hi))
        # the window must be there when the line starts, even if that
        # means a quick move (the sound cannot wait)
        at = max(float(ln.get("at", 0.0)), last_t + SCROLL_HOLD_GAP, 0.15)
        end = max(at, float(ln.get("at", 0.0)) + float(ln.get("dur", 0.0)))
        if at - SCROLL_MOVE_LEAD > last_t + SCROLL_HOLD_GAP:
            # keep resting, then glide over in the last moments before the
            # line -- not a slow drift across a long pause
            keys.append((at - SCROLL_MOVE_LEAD, keys[-1][1]))
        keys.append((at, y_i))
        keys.append((end, y_i))
        last_t = end
    if last_t < dur:
        keys.append((dur, yb))
    return keys


def _style_pref(style: str) -> str | None:
    from .. import styles

    st = styles.REGISTRY.get(style)
    return getattr(st, "preferred_transition", None) if st else None


def _match_align(prev_shot, prev: PanelInfo, cur_plan, cur: PanelInfo, out):
    """Put the face at the same screen place and size as at the end of prev."""
    if not prev_shot or not prev.characters or not cur.characters:
        return
    fa, fb = prev.characters[0].face, cur.characters[0].face
    if not fa or not fb or not cur_plan.keys:
        return
    pk = prev_shot["camera"]["keys"][-1]
    m = K.affine(pk, (prev.w, prev.h), out)
    ax, ay = fa[0] + fa[2] / 2, fa[1] + fa[3] / 2
    sx = m[0][0] * ax + m[0][1] * ay + m[0][2]
    sy = m[1][0] * ax + m[1][1] * ay + m[1][2]
    s_prev = K.contain_scale((prev.w, prev.h), out) * pk["zoom"]
    size_screen = fa[2] * s_prev
    s_cur = size_screen / max(1.0, fb[2])
    zoom = s_cur / K.contain_scale((cur.w, cur.h), out)
    bx, by = fb[0] + fb[2] / 2, fb[1] + fb[3] / 2
    cx = (bx - (sx - out[0] / 2) / s_cur) / cur.w
    cy = (by - (sy - out[1] / 2) / s_cur) / cur.h
    zmax = K.max_zoom_for((cur.w, cur.h), out, 1.5)
    k0 = K.clamp_key(
        {**cur_plan.keys[0], "cx": cx, "cy": cy, "zoom": zoom},
        (cur.w, cur.h),
        out,
        zmax,
    )
    cur_plan.keys[0].update(
        cx=round(k0["cx"], 4), cy=round(k0["cy"], 4), zoom=round(k0["zoom"], 4)
    )
    cur_plan.notes.append("match cut: face lined up with the previous shot")


def _reveal_shot(inp: ChapterInputs, group: list[str], settings: dict) -> dict:
    """Page reveal: show a strip section, then fly into its first panel."""
    boxes = [inp.by_id[p]["box"] for p in group]
    x0 = min(b[0] for b in boxes)
    y0 = min(b[1] for b in boxes)
    x1 = max(b[0] + b[2] for b in boxes)
    y1 = max(b[1] + b[3] for b in boxes)
    region = [x0, y0, x1 - x0, y1 - y0]
    out = out_size(settings)
    src = (region[2], region[3])
    pace = max(0.2, float(settings.get("pace", 1.0)))
    fb = boxes[0]
    zmax = K.max_zoom_for(src, out, 1.5, cap=8.0, max_upscale=8.0)
    target = K.zoom_to_fit(fb[2], fb[3], src, out, 1.0)
    fly = K.clamp_key(
        {
            "cx": (fb[0] - x0 + fb[2] / 2) / src[0],
            "cy": (fb[1] - y0 + fb[3] / 2) / src[1],
            "zoom": target,
        },
        src,
        out,
        zmax,
    )
    hold, move = 1.4 / pace, 0.9 / pace
    tall = src[1] / src[0] > out[1] / out[0] * 1.6
    start = {"t": 0.0, "cx": 0.5, "cy": 0.0 if tall else 0.5, "zoom": 1.0}
    if tall:
        start["zoom"] = min(K.cover_zoom(src, out), zmax)
        start = K.clamp_key(start, src, out, zmax) | {"t": 0.0}
    keys = [start, {**start, "t": hold, "cy": 1.0 if tall else 0.5}]
    keys[1] = K.clamp_key(keys[1], src, out, zmax) | {"t": hold}
    keys.append(
        {"t": hold + move, **{k: fly[k] for k in ("cx", "cy", "zoom")}, "rot": 0}
    )
    return {
        "id": shot_id(group[0], "reveal"),
        "kind": "reveal",
        "panel_id": group[0],
        "panels": group,
        "region": region,
        "dur": round(hold + move, 3),
        "style": None,
        "camera": {
            "keys": [
                {f: (round(v, 4) if isinstance(v, float) else v) for f, v in k.items()}
                for k in keys
            ],
            "shake": 0.0,
            "impacts": [],
            "flip": False,
            "auto": True,
            "notes": ["page reveal: strip section, then fly into the panel"],
        },
        "transition_in": {"kind": "fade", "dur": 0.4, "auto": True},
        "lines": [],
        "sfx": [],
        "edited": False,
    }


def _reveal_groups(inp: ChapterInputs, settings: dict) -> list[list[str]]:
    out = out_size(settings)
    groups, cur, cur_h = [], [], 0.0
    width = inp.strip.get("width") or 800
    limit = width * max(1.2, out[1] / out[0] * 3.0)
    for p in inp.panels:
        h = p["box"][3]
        if cur and cur_h + h > limit:
            groups.append(cur)
            cur, cur_h = [], 0.0
        cur.append(p["id"])
        cur_h += h
    if cur:
        groups.append(cur)
    return groups


def lines_respoken(chapter_dir: Path, tl: dict, tolerance: float = 0.05) -> list[str]:
    """Ids of lines whose spoken length in script.json no longer matches the
    planned shot that carries them (a line re-spoken with another voice or
    other words). Such a film needs its shots planned again, or the new
    voice is cut short or runs into the next shot. Edited shots are the
    person's own timing and are left out."""
    script = store.read(chapter_dir / "script.json", {"lines": []}) or {}
    spoken = {
        ln["id"]: float(ln.get("dur") or 0.0)
        for ln in script.get("lines", [])
        # a line given to nobody has no sound and takes no time any more
        if ln.get("audio") or ln.get("speaker") is None
    }
    stale = []
    for shot in tl.get("shots", []):
        if shot.get("edited"):
            continue
        for ln in shot.get("lines", []):
            now = spoken.get(ln.get("line_id"))
            if now is not None and abs(now - float(ln.get("dur") or 0.0)) > tolerance:
                stale.append(ln["line_id"])
    return stale


def build(
    inp: ChapterInputs,
    existing: dict | None = None,
    overrides: dict | None = None,
    log=None,
) -> dict:
    """Plan every shot. Edited shots and saved settings are kept as they are."""
    existing = existing or {}
    settings = {
        **DEFAULT_SETTINGS,
        **(existing.get("settings") or {}),
        **(overrides or {}),
    }
    old = {s["id"]: s for s in existing.get("shots", [])}
    cam = camera_settings(settings, inp.reading)
    state = DirectionState()
    infos = [inp.panel_info(p["id"]) for p in inp.panels]
    groups = _reveal_groups(inp, settings) if settings["mode"] == "page-reveal" else []
    group_first = {g[0]: g for g in groups}
    shots: list[dict] = []
    prev_info: PanelInfo | None = None
    sfx_by_panel: dict[str, list[str]] = {}
    for x in inp.script.get("sfx", []):
        sfx_by_panel.setdefault(x.get("panel_id"), []).append(x["id"])
    for i, info in enumerate(infos):
        if info.id in group_first:
            rs = _reveal_shot(inp, group_first[info.id], settings)
            if old.get(rs["id"], {}).get("edited"):
                rs = copy.deepcopy(old[rs["id"]])
            shots.append(rs)
            prev_info = None  # the reveal flies into this panel: no transition
        sid = shot_id(info.id)
        nxt = infos[i + 1] if i + 1 < len(infos) else None
        plan = plan_shot(info, cam, state, nxt)
        if old.get(sid, {}).get("edited"):
            shot = copy.deepcopy(old[sid])
            shot["edited"] = True
            shots.append(shot)
            prev_info = info
            continue
        if shots and shots[-1].get("kind") == "reveal":
            kind, tdur = "cut", 0.0
        elif settings["transition"] == "auto":
            kind, tdur = transitions.choose_auto(
                prev_info, info, inp.reading, _style_pref(settings["style"])
            )
        else:
            kind = settings["transition"]
            mod = transitions.REGISTRY.get(kind, transitions.REGISTRY["cut"])
            tdur = mod.DEFAULT_DUR
        if kind == "match" and prev_info is not None:
            _match_align(shots[-1] if shots else None, prev_info, plan, info, cam.out)
        shot = {
            "id": sid,
            "kind": "panel",
            "panel_id": info.id,
            "dur": plan.dur,
            "style": None,
            "camera": plan.camera(),
            "transition_in": {"kind": kind, "dur": tdur, "auto": True},
            "lines": [
                {
                    "line_id": ln["line_id"],
                    "bubble_id": ln["bubble_id"],
                    "at": ln["at"],
                    "dur": round(ln["dur"], 3),
                }
                for ln in plan.lines
            ],
            "sfx": sfx_by_panel.get(info.id, []),
            "edited": False,
        }
        prev_shot_old = old.get(sid)
        if prev_shot_old and prev_shot_old.get("style_settings"):
            shot["style_settings"] = prev_shot_old["style_settings"]
        shots.append(shot)
        prev_info = info
        if log and i % 25 == 0:
            log(f"planned {i + 1}/{len(infos)} panels")
    if settings["mode"] == "scroll":
        plan_scroll(inp, shots, settings)
    tl = {
        "schema": 1,
        "settings": settings,
        "shots": shots,
        "music": [m["id"] for m in inp.script.get("music", [])],
        "panel_source": inp.panel_source,
    }
    return retime(tl)


def retime(tl: dict, fps: int | None = None) -> dict:
    """Shots play back to back. Durations snap to whole frames so video and
    audio (which uses `start`) stay in sync over a long chapter."""
    fps = int(fps or (tl.get("settings") or {}).get("fps") or 30)
    frames = 0
    for s in tl.get("shots", []):
        n = max(1, int(round(float(s.get("dur", 0.0)) * fps)))
        s["dur"] = round(n / fps, 4)
        s["start"] = round(frames / fps, 4)
        frames += n
    tl["duration"] = round(frames / fps, 4)
    return tl


def _norm_key(k: dict, dur: float) -> dict:
    out = {
        "t": round(min(max(0.0, float(k.get("t", 0.0))), dur), 3),
        "cx": min(1.0, max(0.0, float(k.get("cx", 0.5)))),
        "cy": min(1.0, max(0.0, float(k.get("cy", 0.5)))),
        "zoom": min(12.0, max(1.0, float(k.get("zoom", 1.0)))),
        "rot": min(45.0, max(-45.0, float(k.get("rot", 0.0)))),
    }
    if k.get("ease") in K.EASES and k.get("ease") != "inout":
        out["ease"] = k["ease"]
    return out


class TimelineError(ValueError):
    pass


def apply_put(old: dict | None, new: dict) -> dict:
    """Validate an edited timeline from the editor and mark changed shots edited.

    Accepts edits to camera keys, transitions, style, timing (dur) and line
    offsets. A shot whose editable fields differ from the stored version gets
    `edited: true` (so auto keeps it); the client may also set it directly.
    """
    from .. import styles

    if not isinstance(new, dict) or not isinstance(new.get("shots"), list):
        raise TimelineError("timeline needs a shots list")
    old = old or {}
    old_shots = {s["id"]: s for s in old.get("shots", [])}
    settings = {
        **DEFAULT_SETTINGS,
        **(old.get("settings") or {}),
        **(new.get("settings") or {}),
    }
    if settings["aspect"] not in ("16:9", "9:16"):
        raise TimelineError("aspect must be 16:9 or 9:16")
    if settings["bubbles"] not in ("keep", "erase"):
        raise TimelineError("bubbles must be keep or erase")
    if settings["style"] not in styles.REGISTRY:
        raise TimelineError(f"unknown style {settings['style']}")
    shots = []
    seen = set()
    for s in new["shots"]:
        if not isinstance(s, dict) or not s.get("id") or not s.get("panel_id"):
            raise TimelineError("every shot needs id and panel_id")
        if s["id"] in seen:
            raise TimelineError(f"duplicate shot id {s['id']}")
        seen.add(s["id"])
        s = copy.deepcopy(s)
        dur = float(s.get("dur", 0))
        if not 0.1 <= dur <= 600:
            raise TimelineError(f"{s['id']}: dur must be 0.1..600 seconds")
        s["dur"] = round(dur, 3)
        if s.get("style") not in (None, *styles.REGISTRY.keys()):
            raise TimelineError(f"{s['id']}: unknown style {s.get('style')}")
        cam = s.get("camera") or {}
        cam["keys"] = sorted(
            (_norm_key(k, dur) for k in cam.get("keys", [])), key=lambda k: k["t"]
        )
        cam["shake"] = min(2.0, max(0.0, float(cam.get("shake", 0.0))))
        cam["impacts"] = [min(dur, max(0.0, float(x))) for x in cam.get("impacts", [])]
        cam["flip"] = bool(cam.get("flip", False))
        s["camera"] = cam
        tr = s.get("transition_in") or {"kind": "cut", "dur": 0.0}
        if tr.get("kind") not in transitions.REGISTRY:
            raise TimelineError(f"{s['id']}: unknown transition {tr.get('kind')}")
        tr["dur"] = round(min(dur, max(0.0, float(tr.get("dur", 0.0)))), 3)
        s["transition_in"] = tr
        for ln in s.get("lines", []):
            ln["at"] = round(min(dur, max(0.0, float(ln.get("at", 0.0)))), 3)
        prev = old_shots.get(s["id"])
        if prev is not None and not s.get("edited"):
            changed = [f for f in EDITABLE if _cmp(prev.get(f)) != _cmp(s.get(f))]
            if changed:
                s["edited"] = True
                if "camera" in changed:
                    s["camera"]["auto"] = False
                if "transition_in" in changed:
                    s["transition_in"]["auto"] = False
        s["edited"] = bool(s.get("edited"))
        shots.append(s)
    tl = {**old, **new, "schema": 1, "settings": settings, "shots": shots}
    return retime(tl)


def _cmp(v):
    """Compare ignoring bookkeeping fields and float noise."""
    if isinstance(v, dict):
        return {k: _cmp(x) for k, x in v.items() if k not in ("auto", "notes")}
    if isinstance(v, list):
        return [_cmp(x) for x in v]
    if isinstance(v, float):
        return round(v, 3)
    return v
