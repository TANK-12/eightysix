"""In-between frames: the outgoing drawing flows into the incoming one.

Optical flow (DIS, on a half-size grey copy) is measured between the
two real frames. Each in-between warps the outgoing frame forward by u of
the flow and the incoming frame backward by (1 - u) of the reverse flow,
then blends them, so shapes travel instead of just dissolving. Where the
two frames have nothing in common the flow is small and it degrades to a
cross-dissolve. Animation of the manga's own drawings; nothing invented.
"""

import cv2
import numpy as np

LABEL = "In-between (morph)"
DEFAULT_DUR = 0.6
SETTINGS = {"dur": {"type": "number", "min": 0.2, "max": 2.0, "step": 0.05}}

_cache: dict = {}


def _flow(src: np.ndarray, dst: np.ndarray) -> np.ndarray:
    """Dense flow from src to dst, full size, in pixels."""
    key = (src.ctypes.data, dst.ctypes.data, src.shape)
    hit = _cache.get(key)
    if hit is not None:
        return hit
    h, w = src.shape[:2]
    small = (max(8, w // 2), max(8, h // 2))
    g0 = cv2.cvtColor(
        cv2.resize(src, small, interpolation=cv2.INTER_AREA), cv2.COLOR_BGRA2GRAY
    )
    g1 = cv2.cvtColor(
        cv2.resize(dst, small, interpolation=cv2.INTER_AREA), cv2.COLOR_BGRA2GRAY
    )
    # DIS flow: Farneback found only a third of a 40 px shift of a flat
    # shape; DIS (medium preset, spatial propagation) finds all of it
    dis = getattr(cv2, "DISOpticalFlow_create")(cv2.DISOPTICAL_FLOW_PRESET_MEDIUM)
    dis.setFinestScale(0)
    dis.setPatchSize(16)
    dis.setPatchStride(4)
    dis.setUseSpatialPropagation(True)
    f = dis.calc(g0, g1, None)  # type: ignore[arg-type]
    f = cv2.resize(f, (w, h), interpolation=cv2.INTER_LINEAR) * 2.0
    f = cv2.GaussianBlur(f, (0, 0), 4)
    if len(_cache) > 8:
        _cache.clear()
    _cache[key] = f
    return f


def _warp(img: np.ndarray, flow: np.ndarray, amount: float) -> np.ndarray:
    h, w = img.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    map_x = xx - flow[..., 0] * amount
    map_y = yy - flow[..., 1] * amount
    return cv2.remap(
        img, map_x, map_y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE
    )


def blend(a, b, u, info):
    if u <= 0.0:
        return a
    if u >= 1.0:
        return b
    fwd = _flow(a, b)  # a -> b
    back = _flow(b, a)  # b -> a
    # the outgoing frame has moved u of the way along a->b: the pixel at x
    # came from x - u*flow; the incoming one is (1-u) of the way back along
    # b->a
    a_warped = _warp(a, fwd, u)
    b_warped = _warp(b, back, 1.0 - u)
    # ease the mix so both drawings hold their shape at the ends
    m = u * u * (3 - 2 * u)
    return cv2.addWeighted(a_warped, 1.0 - m, b_warped, m, 0.0)
