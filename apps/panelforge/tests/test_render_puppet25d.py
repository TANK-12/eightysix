"""2.5D puppets: breathing, blinks and lip-flap on the character cutouts."""

import numpy as np
import pytest

from panelforge import store, styles
from panelforge.render import timeline as TL
from panelforge.render.context import RenderContext
from panelforge.render.fixture import add_scene_layers, make_chapter
from panelforge.render.inputs import ChapterInputs
from panelforge.render.renderer import Renderer
from panelforge.styles import puppet25d as P


def test_registry_lists_the_puppet_style_as_enabled():
    st = styles.REGISTRY["puppet25d"]
    assert st.enabled and "blinks" in st.settings and "lipflap" in st.settings


def test_blinks_are_brief_deterministic_and_never_in_step():
    a = [P.blink_amount(t / 100, 0.2) for t in range(0, 1200)]
    b = [P.blink_amount(t / 100, 0.7) for t in range(0, 1200)]
    closed_a = sum(1 for v in a if v >= 0.99) / 100
    assert 0.05 <= closed_a <= 0.4, closed_a  # a few brief blinks in 12 s
    assert a != b  # two characters do not blink together
    assert a == [P.blink_amount(t / 100, 0.2) for t in range(0, 1200)]
    assert all(P.blink_amount(t / 100, 0.2, rate=0.0) == 0 for t in range(0, 500))


def test_mouth_moves_only_while_the_line_plays():
    speaking = [(1.0, 3.0)]
    before = [P.mouth_amount(t / 100, speaking, 0.3) for t in range(0, 100)]
    during = [P.mouth_amount(t / 100, speaking, 0.3) for t in range(120, 280)]
    after = [P.mouth_amount(t / 100, speaking, 0.3) for t in range(320, 400)]
    assert max(before) == 0 and max(after) == 0
    assert max(during) > 0.5 and min(during) < 0.3  # opens and closes


def test_squash_rows_changes_only_the_target_region():
    img = np.random.default_rng(1).integers(0, 255, (200, 120, 4), np.uint8)
    img[..., 3] = 255
    eye = (40, 80, 30, 12)
    out = img.copy()
    P.squash_rows(out, eye, 1.0, "close")
    diff = np.abs(out.astype(int) - img.astype(int)).sum(axis=2)
    ys, xs = np.nonzero(diff)
    assert len(ys) > 50
    assert ys.min() >= 60 and ys.max() <= 115 and xs.min() >= 30 and xs.max() <= 80
    mouth = (45, 130, 30, 10)
    out2 = img.copy()
    P.squash_rows(out2, mouth, 1.0, "open")
    d2 = np.abs(out2.astype(int) - img.astype(int)).sum(axis=2)
    assert np.nonzero(d2)[0].min() >= 125  # nothing above the mouth moves


@pytest.fixture()
def rigged(tmp_path):
    ch = make_chapter(tmp_path, n_panels=2)
    add_scene_layers(ch)
    scene = store.read(ch / "scene.json")
    for rec in scene["panels"].values():
        c = rec["characters"][0]
        fx, fy, fw, fh = c["face"]
        rec["rigs"] = [
            {
                "char_index": 0,
                "head": c["face"],
                "eyes": [[fx + 20, fy + 45, 24, 12], [fx + 70, fy + 45, 24, 12]],
                "mouth": [fx + 45, fy + 85, 30, 12],
                "pivot_neck": [fx + fw // 2, fy + fh],
                "pivot_hip": [fx + fw // 2, c["box"][1] + c["box"][3]],
            }
        ]
    store.write(ch / "scene.json", scene)
    return ch


def test_puppet_frames_move_the_face_and_keep_the_background(rigged):
    inp = ChapterInputs(rigged)
    tl = TL.build(inp, overrides={"height": 360, "style": "puppet25d"})
    ctx = RenderContext(inp, tl["settings"])
    r = Renderer(ctx, tl)
    st = styles.style_for(ctx, r.shots[0])
    assert st.name == "puppet25d"
    sc = st.scene(ctx, r.shots[0])
    ch = next(c for c in sc["chars"] if c["cast_id"] == "c01")  # layers are far to near
    assert ch["eyes"] and ch["mouth"] and ch["speaking"], ch.keys()
    # the layer picture differs between an open-eyed and a closed-eyed moment
    t_open = 0.3
    t_closed = next(
        t / 100 for t in range(0, 2000) if P.blink_amount(t / 100, ch["seed"]) >= 0.99
    )
    a = st.layer_image(ctx, r.shots[0], sc, ch, t_open)
    b = st.layer_image(ctx, r.shots[0], sc, ch, t_closed)
    assert a.shape == b.shape and np.abs(a.astype(int) - b.astype(int)).sum() > 0
    # whole frames render and are sane
    for t in (0.0, 0.5, 1.0):
        f = r.frame(0, t)
        assert f.shape[0] == 360 and f[..., 3].min() == 255
