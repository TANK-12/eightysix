"""In-between frames: a shape that moves between two real frames travels."""

import cv2
import numpy as np

from panelforge import transitions as T


def _frame(x0):
    f = np.zeros((120, 200, 4), np.uint8)
    f[..., 3] = 255
    cv2.rectangle(f, (x0, 40), (x0 + 40, 80), (255, 255, 255, 255), -1)
    return f


def test_morph_moves_the_shape_halfway_instead_of_dissolving():
    a, b = _frame(40), _frame(80)
    mid = T.blend("morph", a, b, 0.5, T.TransitionInfo())
    row = mid[60, :, 0].astype(int)
    bright = np.nonzero(row > 200)[0]
    # one solid square about x 60..100, not two half-bright ghosts
    assert (
        bright.size > 25 and 50 <= bright.min() <= 70 and 90 <= bright.max() <= 110
    ), (bright.min(), bright.max())
    assert row.max() > 240
    assert np.array_equal(T.blend("morph", a, b, 0.0, T.TransitionInfo()), a)
    assert np.array_equal(T.blend("morph", a, b, 1.0, T.TransitionInfo()), b)


def test_inbetween_style_is_listed_and_prefers_morph():
    from panelforge import styles

    st = styles.REGISTRY["inbetween"]
    assert st.enabled and st.preferred_transition == "morph"
    assert "morph" in T.REGISTRY


def test_morph_is_not_used_between_panels_with_lettering():
    from panelforge.camera import PanelInfo

    from panelforge.camera import Character

    rook = [Character(box=[0, 0, 100, 200], cast_id="c01")]
    plain_a = PanelInfo(id="a", w=800, h=600, scene_id="s1", characters=rook)
    plain_b = PanelInfo(id="b", w=800, h=600, scene_id="s1", characters=rook)
    texty = PanelInfo(
        id="c", w=800, h=600, scene_id="s1", has_text=True, characters=rook
    )
    nobody = PanelInfo(id="d", w=800, h=600, scene_id="s1")
    assert T.choose_auto(plain_a, plain_b, "ttb", "morph")[0] == "morph"
    assert T.choose_auto(plain_a, texty, "ttb", "morph")[0] != "morph"
    assert T.choose_auto(texty, plain_b, "ttb", "morph")[0] != "morph"
    # unrelated drawings (no shared character) do not morph either
    assert T.choose_auto(plain_a, nobody, "ttb", "morph")[0] != "morph"


def test_drawn_sound_words_count_as_lettering(tmp_path):
    from panelforge import store
    from panelforge.render.fixture import make_chapter
    from panelforge.render.inputs import ChapterInputs

    ch = make_chapter(tmp_path, n_panels=2, script=False)
    scene = store.read(ch / "scene.json")
    pids = list(scene["panels"])
    scene["panels"][pids[0]]["sfx_text"] = [{"box": [10, 10, 80, 40], "text": "BOOM"}]
    store.write(ch / "scene.json", scene)
    bubbles = store.read(ch / "bubbles.json")
    bubbles["bubbles"] = []  # no balloons at all: only the drawn sound word
    store.write(ch / "bubbles.json", bubbles)
    inp = ChapterInputs(ch)
    assert inp.panel_info(pids[0]).has_text is True
    assert inp.panel_info(pids[1]).has_text is False
