"""Synthetic chapter for render tests: drawn pages, panels, bubbles, scene, script.

Two 800x1280 pages stacked into one strip. Each panel shows two simple
"characters" (head, eyes, mouth, body) on a gradient with a white speech
bubble, so every render path has something real to chew on.
"""

from pathlib import Path

import cv2
import numpy as np

from .. import store


def _draw_char(img, x, y, s, color):
    cv2.rectangle(img, (x - s // 2, y + s // 2), (x + s // 2, y + s * 2), color, -1)
    cv2.circle(img, (x, y), s // 2, (205, 215, 235), -1)
    cv2.circle(img, (x, y), s // 2, (30, 30, 30), 3)
    for ex in (x - s // 6, x + s // 6):
        cv2.circle(img, (ex, y - s // 10), max(2, s // 16), (20, 20, 20), -1)
    cv2.line(img, (x - s // 8, y + s // 5), (x + s // 8, y + s // 5), (20, 20, 60), 3)


def make_chapter(
    root: Path, n_panels: int = 4, scene=True, script=True, crossed=False
) -> Path:
    ch = Path(root) / "series" / "test-series" / "chapters" / "0001"
    (ch / "pages").mkdir(parents=True, exist_ok=True)
    W, H = 800, 1280
    ph, gap = 520, 60
    strip_h = gap + n_panels * (ph + gap)
    pages = (strip_h + H - 1) // H
    strip = np.full((pages * H, W, 3), 255, np.uint8)
    panels, bubbles, scene_panels, lines = [], [], {}, []
    for i in range(n_panels):
        y = gap + i * (ph + gap)
        pid = f"p{i + 1:04d}"
        grad = np.linspace(60 + 30 * i, 190, ph, dtype=np.uint8)[:, None]
        strip[y : y + ph, 40 : W - 40] = np.stack(
            [
                np.repeat(grad, W - 80, 1),
                np.repeat(grad // 2 + 40, W - 80, 1),
                np.repeat(255 - grad, W - 80, 1),
            ],
            -1,
        )
        left, right = (560, 240) if (crossed and i == 1) else (240, 560)
        _draw_char(strip, left, y + 230, 120, (40, 90, 200))
        _draw_char(strip, right, y + 250, 110, (60, 160, 60))
        bx, by, bw, bh = 250, y + 20, 300, 110
        cv2.ellipse(
            strip,
            (bx + bw // 2, by + bh // 2),
            (bw // 2, bh // 2),
            0,
            0,
            360,
            (255, 255, 255),
            -1,
        )
        cv2.ellipse(
            strip,
            (bx + bw // 2, by + bh // 2),
            (bw // 2, bh // 2),
            0,
            0,
            360,
            (0, 0, 0),
            3,
        )
        cv2.putText(
            strip,
            "HELLO THERE!",
            (bx + 50, by + 65),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.9,
            (0, 0, 0),
            2,
        )
        panels.append(
            {
                "id": pid,
                "order": i + 1,
                "box": [40, y, W - 80, ph],
                "kind": "panel",
                "shape": "rect",
                "polygon": None,
                "image": None,
                "edited": False,
            }
        )
        bid = f"b{i + 1:04d}"
        bubbles.append(
            {
                "id": bid,
                "panel_id": pid,
                "order": i + 1,
                "box": [bx, by, bw, bh],
                "kind": "speech",
                "text": "HELLO THERE, FRIEND OF MINE!",
                "ocr_conf": 0.9,
                "tail": [left, y + 170],
                "speaker": "c01",
                "speaker_conf": 0.8,
                "edited": False,
            }
        )
        lx = left - 40
        rx = right - 40
        scene_panels[pid] = {
            "scene_id": "s01",
            "location": "hall",
            "mood": "action" if i == 2 else "calm",
            "action": 0.9 if i == 2 else 0.1,
            "characters": [
                {
                    "cast_id": "c01",
                    "extra_id": None,
                    "box": [lx - 60, 150, 200, 330],
                    "face": [lx - 20, 170, 120, 120],
                    "facing": "right",
                    "cutout": None,
                },
                {
                    "cast_id": "c02",
                    "extra_id": None,
                    "box": [rx - 60, 170, 190, 320],
                    "face": [rx - 15, 195, 110, 110],
                    "facing": "left",
                    "cutout": None,
                },
            ],
            "background": None,
            "depth": None,
            "saliency": [[left - 40, 190, 1.0]],
            "sfx_text": [],
            "speed_lines": {"present": True, "angle_deg": 20} if i == 2 else None,
            "rigs": [],
        }
        if script:
            lines.append(
                {
                    "id": f"l{i + 1:04d}",
                    "bubble_id": bid,
                    "speaker": "c01",
                    "text": "Hello there, friend of mine!",
                    "kind": "speech",
                    "emotion": {
                        "speed": 1.0,
                        "gain_db": 0,
                        "pause_after": 0.25,
                        "reverb": 0.0,
                    },
                    "audio": None,
                    "dur": 1.5,
                }
            )
    page_list = []
    for p in range(pages):
        f = ch / "pages" / f"{p + 1:03d}.png"
        cv2.imwrite(str(f), strip[p * H : (p + 1) * H])
        page_list.append(
            {
                "idx": p + 1,
                "file": f"pages/{f.name}",
                "w": W,
                "h": H,
                "sha1": f"x{p}",
                "capture": "import",
            }
        )
    store.write(
        ch / "chapter.json",
        {
            "schema": 1,
            "series": "test-series",
            "chapter": "0001",
            "number": 1,
            "title": "Test",
            "layout": "strip",
            "reading": "ttb",
            "pages": page_list,
        },
    )
    store.write(ch / "panels.json", {"schema": 1, "panels": panels})
    store.write(ch / "bubbles.json", {"schema": 1, "bubbles": bubbles})
    if scene:
        store.write(
            ch / "scene.json", {"schema": 1, "panels": scene_panels, "speakers": {}}
        )
    if script:
        store.write(
            ch / "script.json", {"schema": 1, "lines": lines, "sfx": [], "music": []}
        )
    return ch


def add_scene_layers(ch: Path) -> Path:
    """Write the scene layers depth3d uses for every panel of a fixture chapter:
    an inpainted background (characters painted over with the gradient), a
    16-bit depth map (characters near, floor nearer than the top) and RGBA
    cutouts cropped to each character box. Returns the chapter dir."""
    from .inputs import ChapterInputs

    inp = ChapterInputs(ch)
    scene = store.read(ch / "scene.json") or {"schema": 1, "panels": {}, "speakers": {}}
    for p in inp.panels:
        pid = p["id"]
        rec = scene["panels"].setdefault(pid, {})
        img = inp.panel_image(pid)
        h, w = img.shape[:2]
        folder = ch / "work" / "scene" / pid
        folder.mkdir(parents=True, exist_ok=True)
        bg = img[..., :3].copy()
        depth = np.repeat(np.linspace(0.15, 0.55, h, dtype=np.float32)[:, None], w, 1)
        chars = rec.get("characters") or []
        for i, c in enumerate(chars):
            x, y, cw, chh = [int(v) for v in c["box"]]
            x0, y0, x1, y1 = max(0, x), max(0, y), min(w, x + cw), min(h, y + chh)
            crop = img[y0:y1, x0:x1]
            # the drawn figure is anything that is not the gradient backdrop
            gray = cv2.cvtColor(crop[..., :3], cv2.COLOR_BGR2GRAY)
            sat = cv2.cvtColor(crop[..., :3], cv2.COLOR_BGR2HSV)[..., 1]
            fg = ((gray < 60) | (sat < 40) | (gray > 180)).astype(np.uint8) * 255
            fg = cv2.morphologyEx(fg, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
            cut = np.zeros((chh, cw, 4), np.uint8)
            cut[y0 - y : y1 - y, x0 - x : x1 - x, :3] = crop[..., :3]
            cut[y0 - y : y1 - y, x0 - x : x1 - x, 3] = fg
            cv2.imwrite(str(folder / f"cut_{i}.png"), cut)
            c["cutout"] = f"work/scene/{pid}/cut_{i}.png"
            # paint the figure out of the background with the row colour at its edge
            col = bg[y0:y1, max(0, x0 - 3) : max(1, x0 - 1)].mean(axis=1, keepdims=True)
            region = bg[y0:y1, x0:x1]
            m = fg > 0
            region[m] = np.repeat(col, region.shape[1], 1)[m].astype(np.uint8)
            depth[y0:y1, x0:x1][m] = 0.85 - 0.15 * i
        for b in inp.panel_bubbles(pid):
            bx, by, bw, bh = [int(v) for v in inp.local_box(pid, b["box"])]
            bx0, by0, bx1, by1 = (
                max(0, bx - 6),
                max(0, by - 6),
                min(w, bx + bw + 6),
                min(h, by + bh + 6),
            )
            col = bg[by0:by1, max(0, bx0 - 3) : max(1, bx0 - 1)].mean(
                axis=1, keepdims=True
            )
            bg[by0:by1, bx0:bx1] = np.repeat(col, bx1 - bx0, 1).astype(np.uint8)
        cv2.imwrite(str(folder / "bg.png"), bg)
        cv2.imwrite(str(folder / "depth.png"), (depth * 65535).astype(np.uint16))
        rec["background"] = f"work/scene/{pid}/bg.png"
        rec["depth"] = f"work/scene/{pid}/depth.png"
    store.write(ch / "scene.json", scene)
    return ch
