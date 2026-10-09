"""
Loop-exact timing.

A living shot is rendered once, for `loop_s` seconds, and then ffmpeg repeats
that bed for as long as the shot holds. That only looks right if every moving
thing is back exactly where it started at the seam, which is true only when
each oscillator completes a *whole number* of cycles inside the loop.

So nothing here lets an effect use a raw period. You ask for "about four
seconds" and `LoopClock` snaps it to the nearest period that divides the loop
evenly, then hands back a phase that wraps exactly at the boundary. Effects and
emitters call `tl.wave()` / `tl.saw()` instead of touching `t`, which makes a
clean loop the default rather than something each effect has to remember.
"""

import math

import numpy as np


def whole_cycles(period_s, loop_s, minimum=1):
    """The number of whole cycles of roughly `period_s` that fit in `loop_s`."""
    if loop_s <= 0 or period_s <= 0:
        return max(1, int(minimum))
    return max(int(minimum), int(round(loop_s / float(period_s))))


def snapped_period(period_s, loop_s, minimum=1):
    """The nearest period to `period_s` that divides `loop_s` a whole number of
    times. This is what actually gets rendered, so the UI can show it back."""
    return float(loop_s) / whole_cycles(period_s, loop_s, minimum)


class LoopClock:
    """The clock handed to every effect and emitter.

    `t` is seconds into the loop, `loop_s` the loop length. `seed` lets a layer
    or emitter decorrelate its randomness from its neighbours without any of
    them going out of sync with the loop.
    """

    def __init__(self, t, i, loop_s, fps, seed=0, feat=None, frame_index=0):
        self.t = float(t)
        self.i = int(i)
        self.loop_s = max(1e-6, float(loop_s))
        self.fps = float(fps)
        self.seed = int(seed)
        self.feat = feat or {}
        self.frame_index = int(frame_index)

    def child(self, seed_offset):
        """A clock with the same time but its own random stream."""
        return LoopClock(
            self.t,
            self.i,
            self.loop_s,
            self.fps,
            self.seed + int(seed_offset) * 7919,
            self.feat,
            self.frame_index,
        )

    # ---- loop-exact oscillators -------------------------------------------
    def phase(self, period_s, offset=0.0):
        """Phase in turns, in [0, 1), wrapping exactly at the loop boundary."""
        k = whole_cycles(period_s, self.loop_s)
        return ((self.t / self.loop_s) * k + offset) % 1.0

    def wave(self, period_s, offset=0.0):
        """A sine in [-1, 1] that is identical at t=0 and t=loop_s."""
        return math.sin(2.0 * math.pi * self.phase(period_s, offset))

    def cowave(self, period_s, offset=0.0):
        return math.cos(2.0 * math.pi * self.phase(period_s, offset))

    def saw(self, period_s, offset=0.0):
        """A 0->1 ramp that resets on the loop grid. Particle travel uses this."""
        return self.phase(period_s, offset)

    def waves(self, period_s, offsets):
        """Vectorised `wave` over an array of per-particle phase offsets."""
        k = whole_cycles(period_s, self.loop_s)
        ph = (self.t / self.loop_s) * k + np.asarray(offsets, dtype=np.float64)
        return np.sin(2.0 * np.pi * ph)

    def saws(self, period_s, offsets, rate=None):
        """Vectorised `saw` -- N things each at their own point in the cycle.

        `rate` lets them run at different speeds, but only in whole multiples:
        a particle going 1.5x as fast would not be back at the start when the
        loop closes, so the multiplier is rounded.
        """
        k = whole_cycles(period_s, self.loop_s)
        steps = 1.0 if rate is None else np.maximum(1.0, np.rint(rate))
        ph = (self.t / self.loop_s) * (k * steps) + np.asarray(
            offsets, dtype=np.float64
        )
        return ph % 1.0

    def rng(self, extra=0):
        """A generator seeded per layer, *not* per frame -- particles must keep
        the same identity from frame to frame."""
        return np.random.default_rng(self.seed * 104729 + int(extra))

    def audio(self, name, default=0.0):
        """Per-frame audio feature, safely clamped. Live mode only feeds these;
        in loop mode they are absent and every effect falls back to `default`."""
        arr = self.feat.get(name)
        if arr is None or len(arr) == 0:
            return default
        return float(arr[min(self.frame_index, len(arr) - 1)])
