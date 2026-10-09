"""Every SFX recipe renders non-silent audio without clipping. Also checks
the onomatopoeia fuzzy matcher."""

import numpy as np
import pytest

from panelforge.sfx import match, recipes


@pytest.mark.parametrize("name", recipes.names())
def test_recipe_renders_non_silent_no_clip(name):
    samples, sr = recipes.render(name)
    assert sr == recipes.SR
    assert samples.shape[0] > sr * 0.02  # at least ~20ms
    assert np.max(np.abs(samples)) > 0.02  # audible
    assert np.max(np.abs(samples)) <= 1.0  # never clips


def test_repeated_letters_lengthen_or_repeat():
    short = match.match_word("BOOM")
    long_ = match.match_word("BOOOOOOM")
    assert long_[1] > short[1]  # stretch grows with the run length


def test_fuzzy_and_exact_matches():
    name, params = match.match_text("CLANK!!")
    assert name == "clank"
    name2, params2 = match.match_text("RATATATATATA")
    assert name2 == "ratatata"
    assert params2.get("repeat", 1) > 1


def test_unmatched_word_falls_back_not_silent():
    name, params = match.match_text("zzzxqq")
    samples, sr = recipes.render(name, **params)
    assert np.max(np.abs(samples)) > 0.0


def test_gain_and_stretch_overrides():
    base, _ = recipes.render("boom")
    louder, _ = recipes.render("boom", gain_db=6.0)
    longer, _ = recipes.render("boom", stretch=2.0)
    assert longer.shape[0] > base.shape[0]
    assert np.max(np.abs(louder)) >= np.max(np.abs(base)) - 1e-6
