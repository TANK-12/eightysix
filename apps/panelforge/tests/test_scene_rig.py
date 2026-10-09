"""scene rigs and facing: geometry invariants over a sweep of shapes."""

import numpy as np

from panelforge.scene import geom, rig


def test_rig_invariants_sweep():
    rng = np.random.default_rng(7)
    checked = 0
    for _ in range(3000):
        pw, ph = int(rng.integers(200, 1600)), int(rng.integers(200, 1600))
        cw, chh = int(rng.integers(20, pw)), int(rng.integers(20, ph))
        cx, cy = int(rng.integers(0, pw - cw + 1)), int(rng.integers(0, ph - chh + 1))
        box = [cx, cy, cw, chh]
        has_face = rng.random() < 0.8
        face = None
        if has_face:
            fw = int(rng.integers(8, max(9, min(cw, chh) + 1)))
            fh = int(fw * rng.uniform(0.9, 1.2))
            fx = int(rng.integers(cx, cx + max(1, cw - fw + 1)))
            fy = int(rng.integers(cy, cy + max(1, chh - fh + 1)))
            face = [fx, fy, fw, min(fh, cy + chh - fy)]
        facing = rng.choice(["left", "right", "front", None])
        r = rig.build(box, face, facing, pw, ph)
        head = r["head"]
        assert all(isinstance(v, int) for v in head)
        assert geom.inside(head, box, 0) and geom.inside(head, [0, 0, pw, ph])
        for e in r["eyes"]:
            assert geom.inside(e, head, 1) and e[2] > 0 and e[3] > 0
        if r["mouth"]:
            assert geom.inside(r["mouth"], head, 1)
            for e in r["eyes"]:
                assert e[1] + e[3] / 2 < r["mouth"][1] + r["mouth"][3] / 2
        nx, ny = r["pivot_neck"]
        assert geom.contains_point(box, nx, ny)
        if face:
            assert ny >= face[1] + face[3] / 2
        if r["pivot_hip"]:
            assert r["pivot_hip"][1] > ny and geom.contains_point(box, *r["pivot_hip"])
        if not face:
            assert r["eyes"] == [] and r["mouth"] is None
        checked += 1
    assert checked == 3000


def test_typical_portrait_has_two_eyes_mouth_and_hip():
    r = rig.build([100, 100, 300, 900], [200, 150, 100, 110], "front", 800, 1280)
    assert len(r["eyes"]) == 2 and r["mouth"] is not None and r["pivot_hip"] is not None
    left, right = sorted(r["eyes"])
    assert left[0] + left[2] <= right[0]


def _head_mask(char_box, head_left, head_right, top, bottom):
    m = np.zeros((char_box[3], char_box[2]), np.uint8)
    m[
        top - char_box[1] : bottom - char_box[1],
        head_left - char_box[0] : head_right - char_box[0],
    ] = 255
    return m


def test_facing_from_face_offset_in_head_sweep():
    box = [0, 0, 400, 600]
    for face_x in range(100, 221, 5):
        mask = _head_mask(box, 100, 300, 50, 250)
        face = [face_x, 100, 80, 100]  # head spans 100..300, centre 200
        offset = (face_x + 40 - 200) / 200
        got = rig.facing(face, box, mask)
        want = (
            "left"
            if offset < -rig.FRONT_BAND
            else "right" if offset > rig.FRONT_BAND else "front"
        )
        assert got == want, (face_x, got, want)
    assert rig.facing(None, box, None) is None
    assert rig.facing([160, 100, 80, 100], box, None) == "front"
