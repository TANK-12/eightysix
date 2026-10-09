"""The Alt+Space overview's pictures (S2, A12).

forge.py photographs the window a moment after an app comes to the front and
cuts out that app's area, shrunk to a card-sized PNG, so each card in the
overview shows the app as it was last seen.
"""

import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cairo  # noqa: E402

import forge  # noqa: E402


def window(width=1400, height=900):
    s = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
    ctx = cairo.Context(s)
    ctx.set_source_rgb(0, 0, 1)  # blue bar and chrome
    ctx.paint()
    ctx.set_source_rgb(1, 0, 0)  # the app: red, at 100,50 1200x800
    ctx.rectangle(100, 50, 1200, 800)
    ctx.fill()
    return s


def decode(png):
    return cairo.ImageSurface.create_from_png(io.BytesIO(png))


def pixel(img, x, y):
    data = img.get_data()
    i = y * img.get_stride() + x * 4
    return data[i + 2], data[i + 1], data[i]  # BGRA -> RGB


def test_the_app_area_is_cut_out_and_shrunk():
    img = decode(forge.thumb_png(window(), [100, 50, 1200, 800], width=480))
    assert (img.get_width(), img.get_height()) == (480, 320)
    assert pixel(img, 2, 2) == (255, 0, 0)  # the app, not the bar
    assert pixel(img, 477, 317) == (255, 0, 0)


def test_page_pixels_are_turned_into_window_pixels():
    # Under App size 1.25 the page's 80,40 960x640 is the window's 100,50 1200x800.
    img = decode(forge.thumb_png(window(), [80, 40, 960, 640], width=480, scale=1.25))
    assert (img.get_width(), img.get_height()) == (480, 320)
    assert pixel(img, 1, 1) == (255, 0, 0)


def test_a_bad_or_oversized_rect_falls_back_to_what_exists():
    img = decode(forge.thumb_png(window(), None, width=700))
    assert (img.get_width(), img.get_height()) == (700, 450)
    img = decode(forge.thumb_png(window(), [1300, 800, 900, 900], width=480))
    assert (img.get_width(), img.get_height()) == (100, 100)  # clipped to the window


def test_small_areas_are_not_blown_up():
    img = decode(forge.thumb_png(window(), [100, 50, 200, 100], width=480))
    assert (img.get_width(), img.get_height()) == (200, 100)


if __name__ == "__main__":
    failed = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS {name}")
            except (AssertionError, AttributeError, TypeError) as exc:
                failed += 1
                print(f"FAIL {name}: {exc!r}")
    sys.exit(1 if failed else 0)
