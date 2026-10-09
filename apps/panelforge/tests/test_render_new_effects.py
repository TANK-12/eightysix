"""The 2026-09-27 effects and transitions: film grain, RGB split on impacts,
the screentone and flash transitions. Each is small, pure and registered."""

from types import SimpleNamespace

import numpy as np
import pytest

from panelforge import transitions as T
from panelforge.render import effects as E

H, W = 90, 160


def _frame(value=128):
    f = np.full((H, W, 4), value, np.uint8)
    f[..., 3] = 255
    f[:, W // 2 :, :3] = (40, 90, 200)  # something for a split to move
    return f


CTX = SimpleNamespace(fps=24, settings={})


def facts(mood=None, strength=1.0, seed=7):
    return {
        "action": 0.0,
        "mood": mood,
        "speed_angle": None,
        "strength": strength,
        "seed": seed,
    }


def test_new_effects_are_registered():
    names = [fx.__name__ for fx in E.EFFECTS]
    assert "film_grain" in names and "rgb_split" in names


def test_film_grain_only_on_its_moods_and_is_repeatable():
    shot = {"id": "t1"}
    plain = _frame()
    assert np.array_equal(E.film_grain(CTX, shot, 1.0, plain.copy(), facts()), plain)
    assert np.array_equal(
        E.film_grain(CTX, shot, 1.0, plain.copy(), facts("mystery", 0.0)), plain
    )
    a = E.film_grain(CTX, shot, 1.0, plain.copy(), facts("mystery"))
    b = E.film_grain(CTX, shot, 1.0, plain.copy(), facts("mystery"))
    c = E.film_grain(CTX, shot, 1.5, plain.copy(), facts("mystery"))
    assert not np.array_equal(a, plain)  # grain is there
    assert np.array_equal(a, b)  # same frame, same grain (resumable renders)
    assert not np.array_equal(a, c)  # and it moves from frame to frame
    assert np.array_equal(a[..., 3], plain[..., 3])  # alpha untouched
    assert abs(float(a[..., :3].mean()) - float(plain[..., :3].mean())) < 3


def test_rgb_split_at_an_impact_then_gone():
    shot = {"id": "t1", "camera": {"impacts": [1.0]}}
    plain = _frame()
    hit = E.rgb_split(CTX, shot, 1.02, plain.copy(), facts())
    assert not np.array_equal(hit, plain)
    assert np.array_equal(hit[..., 1], plain[..., 1])  # green stays put
    later = E.rgb_split(
        CTX, shot, 1.0 + E.RGB_SPLIT_SECONDS + 0.01, plain.copy(), facts()
    )
    assert np.array_equal(later, plain)
    before = E.rgb_split(CTX, shot, 0.9, plain.copy(), facts())
    assert np.array_equal(before, plain)
    none = E.rgb_split(CTX, {"id": "t1"}, 1.02, plain.copy(), facts())
    assert np.array_equal(none, plain)


def test_a_shot_can_switch_the_new_effects_off():
    ctx = SimpleNamespace(
        fps=24, settings={}, cache={("facts", "t1", "p1"): facts("mystery")}
    )
    shot = {
        "id": "t1",
        "panel_id": "p1",
        "style_settings": {
            "effects_off": ["film_grain", "light_glow", "particles", "speed_lines"]
        },
    }
    plain = _frame()
    assert np.array_equal(E.apply(ctx, shot, 1.0, plain.copy()), plain)


@pytest.mark.parametrize("kind", ["screentone", "flash"])
def test_new_transitions_run_from_old_shot_to_new(kind):
    assert kind in T.REGISTRY
    assert kind in {t["kind"] for t in T.listing()}
    a = np.zeros((H, W, 4), np.uint8)
    b = np.full((H, W, 4), 200, np.uint8)
    info = T.TransitionInfo(direction=(0.0, 1.0))
    assert np.array_equal(T.blend(kind, a, b, 0.0, info), a)
    assert np.array_equal(T.blend(kind, a, b, 1.0, info), b)
    mid = T.blend(kind, a, b, 0.5, info)
    assert mid.shape == a.shape and mid.dtype == np.uint8
    assert not np.array_equal(mid, a) and not np.array_equal(mid, b)


def test_screentone_prints_in_reading_order():
    a = np.zeros((H, W, 4), np.uint8)
    b = np.full((H, W, 4), 255, np.uint8)
    # top-to-bottom reading: the next panel comes in from below, as with Slide
    info = T.TransitionInfo(direction=T.reading_direction("ttb"))
    mid = T.blend("screentone", a, b, 0.4, info)
    top, bottom = mid[: H // 3].mean(), mid[-H // 3 :].mean()
    assert bottom > top  # printed first on the side it comes in from
    # the dots grow: more of the new shot at every step
    cover = [(T.blend("screentone", a, b, u, info) > 0).mean() for u in (0.2, 0.5, 0.8)]
    assert cover[0] < cover[1] < cover[2]


def test_flash_goes_through_white():
    a = np.zeros((H, W, 4), np.uint8)
    b = np.zeros((H, W, 4), np.uint8)
    peak = T.blend("flash", a, b, 0.35, T.TransitionInfo())
    assert peak[..., :3].min() == 255
