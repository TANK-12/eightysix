"""U1 sweep: bad input gets a calm answer, never a 500 or an hours-long job."""

import sys
from pathlib import Path

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import app as studio  # noqa: E402  # pyright: ignore[reportMissingImports]
import library  # noqa: E402  # pyright: ignore[reportMissingImports]


@pytest.fixture
def lib(tmp_path, monkeypatch):
    monkeypatch.setattr(library, "DB_PATH", tmp_path / "library.db")
    library.init()
    library.record("a1", "image", "a cat on a roof", "", {}, "/outputs/a1/x", 1.0)
    library.record("b2", "video", 'neon "city" at night', "", {}, "/outputs/b2/x", 2.0)
    return library


@pytest.mark.parametrize(
    "q", ['"', "a AND", "NEAR(", ":(", "cat OR", "*", "(((", "x:y", "'", "-"]
)
def test_search_never_breaks_on_fts_syntax(lib, q):
    # (no HTTP client: this starlette wants an extra package; the handler is
    # called straight, which is what the route runs)
    assert isinstance(studio.search_library(q=q, kind=""), list)


def test_search_still_finds_words_and_prefixes(lib):
    assert [r["id"] for r in lib.search("cat")] == ["a1"]
    assert [r["id"] for r in lib.search("ro")] == ["a1"]  # last word is a prefix
    assert [r["id"] for r in lib.search('"city"')] == ["b2"]
    assert [r["id"] for r in lib.search("neon AND")] == []  # AND is just a word
    assert len(lib.search("")) == 2
    assert lib.search("  ") == lib.search("")
    assert lib.search("?!") == []  # only punctuation: nothing to look for
    assert [r["id"] for r in lib.search("", kind="video")] == ["b2"]


@pytest.mark.parametrize(
    "body",
    [
        {"prompt": "x", "width": 51200},
        {"prompt": "x", "steps": 0},
        {"prompt": "x", "seed": None},
        {"prompt": "x", "seed": -5},
        {"prompt": "x", "upscale_scale": 9},
        {"prompt": "x", "output_format": "exe"},
        {"prompt": "x", "jpg_quality": 0},
        {"prompt": "x", "batch_count": 0},
        {"prompt": "x" * 5000},
        {"prompt": 5},
    ],
)
def test_image_request_bounds(body):
    with pytest.raises(ValidationError):  # FastAPI answers these with a 422
        studio.ImageRequest.model_validate(body)


@pytest.mark.parametrize(
    "body",
    [
        {"prompt": "x", "keyframes": 9999},
        {"prompt": "x", "motion": "spin-forever"},
        {"prompt": "x", "fps": 0},
        {"prompt": "x", "hold_frames": None},
        {"prompt": "x", "motion_strength": 3},
        {"prompt": "x", "anchor_weight": -1},
        {"scenes": [{"prompt": "x", "frames": 500}]},
        {"scenes": [{"prompt": "x", "motion": "nope"}]},
        {"scenes": [{"prompt": "x"}] * 21},
    ],
)
def test_video_request_bounds(body):
    with pytest.raises(ValidationError):
        studio.VideoRequest.model_validate(body)


def test_requests_the_page_sends_still_validate():
    studio.ImageRequest(
        prompt="a cat",
        width=1024,
        height=384,
        seed=-1,
        steps=40,
        cfg_scale=20,
        upscale_scale=2,
        output_format="png",
        jpg_quality=50,
        batch_count=8,
    )
    studio.VideoRequest(
        prompt="a cat",
        motion="orbit-ccw",
        keyframes=30,
        motion_strength=0.9,
        hold_frames=16,
        fps=30,
        scenes=[studio.Scene(prompt="x", frames=30, motion="zoom-in", strength=0.32)]
        * 20,
    )


@pytest.mark.parametrize("job_id", ["..", "a.b", "x-y", "../outputs", ""])
def test_job_state_refuses_odd_ids(job_id):
    with pytest.raises(HTTPException) as e:
        studio.job_state(job_id)
    assert e.value.status_code == 400


def test_job_state_unknown_id_is_404():
    with pytest.raises(HTTPException) as e:
        studio.job_state("nosuchjob0")
    assert e.value.status_code == 404


@pytest.mark.parametrize("raw", ["NaN", "Infinity", "-Infinity"])
def test_nan_is_a_422_with_a_reply_that_can_be_sent(raw):
    from fastapi.exceptions import RequestValidationError

    for model, body in (
        (studio.ImageRequest, '{"prompt": "a", "cfg_scale": %s}'),
        (studio.VideoRequest, '{"prompt": "a", "motion_strength": %s}'),
        (studio.VideoRequest, '{"scenes": [{"prompt": "a", "strength": %s}]}'),
    ):
        with pytest.raises(ValidationError) as e:
            model.model_validate_json(body % raw)
        res = studio._bad_request(None, RequestValidationError(e.value.errors()))
        assert res.status_code == 422
        assert b"finite" in bytes(res.body)
