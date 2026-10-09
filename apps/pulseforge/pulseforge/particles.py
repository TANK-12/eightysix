"""Particle effects layered over any frame-based scene.

Emerson (2026-09-27) asked for particle effects. Each preset is one entry in
PRESETS; the registry adds the "particles" and "particle_amount" params to
every visualizer, scenery and sprites scene, and render.py passes every
scene's frames through `wrap`, so a new preset is one dict here and nothing
else. With "none" (the default) frames pass through untouched.

A preset says where particles start, how they move and what the music does:
    color     RGB            count  particles at amount 1
    velocity  (vx, vy) in frame heights per second; sway: sideways wobble
    gravity   added to vy per second; size: dot radius in pixels at 720p
    life      seconds a particle lives; spawn: "bottom", "top", "any", "centre"
    drive     "energy" speeds them up with loudness; "beat" bursts on beats
"""

from __future__ import annotations

import numpy as np

PRESETS = {
    "embers": dict(
        color=(255, 140, 50),
        count=160,
        velocity=(0.0, -0.18),
        sway=0.05,
        gravity=0.0,
        size=2.2,
        life=4.0,
        spawn="bottom",
        drive="energy",
    ),
    "snow": dict(
        color=(235, 240, 255),
        count=260,
        velocity=(0.02, 0.10),
        sway=0.06,
        gravity=0.0,
        size=1.8,
        life=12.0,
        spawn="top",
        drive="energy",
    ),
    "sparks": dict(
        color=(255, 200, 90),
        count=220,
        velocity=(0.0, 0.0),
        sway=0.0,
        gravity=0.35,
        size=2.0,
        life=1.2,
        streak=0.06,
        spawn="centre",
        drive="beat",
    ),
    "dust": dict(
        color=(255, 236, 200),
        count=140,
        velocity=(0.01, -0.01),
        sway=0.02,
        gravity=0.0,
        size=1.2,
        life=10.0,
        spawn="any",
        drive="energy",
    ),
    "petals": dict(
        color=(255, 160, 200),
        count=90,
        velocity=(0.06, 0.08),
        sway=0.12,
        gravity=0.0,
        size=3.0,
        life=12.0,
        spawn="top",
        drive="energy",
    ),
}
PARAMS = [
    {
        "key": "particles",
        "label": "Particles",
        "type": "select",
        "default": "none",
        "options": ["none", *PRESETS],
        "group": "particles",
    },
    {
        "key": "particle_amount",
        "label": "Particle amount",
        "type": "float",
        "default": 1.0,
        "min": 0.1,
        "max": 3.0,
        "group": "particles",
    },
]


def _spawn(kind, n, rng, w, h):
    if kind == "bottom":
        return np.c_[rng.random(n) * w, h + rng.random(n) * h * 0.1]
    if kind == "top":
        return np.c_[rng.random(n) * w, -rng.random(n) * h * 0.1]
    if kind == "centre":
        return np.c_[np.full(n, w / 2.0), np.full(n, h / 2.0)]
    return np.c_[rng.random(n) * w, rng.random(n) * h]


class Layer:
    """One preset's particles over a w x h frame, stepped once per frame."""

    def __init__(self, preset: dict, amount: float, w: int, h: int, fps: float):
        self.p, self.w, self.h, self.fps = preset, w, h, fps
        self.rng = np.random.default_rng(7)
        n = max(1, int(preset["count"] * amount))
        self.pos = _spawn(
            "any" if preset["drive"] != "beat" else "centre", n, self.rng, w, h
        )
        self.vel = np.zeros((n, 2))
        self.age = self.rng.random(n) * preset["life"]
        if preset["drive"] == "beat":
            self.age[:] = preset["life"]  # sparks wait for the first beat
        self.phase = self.rng.random(n) * 6.28
        self.radius = max(1, int(round(preset["size"] * h / 720.0)))

    def _reset(self, idx, burst: bool):
        p, n = self.p, len(idx)
        self.pos[idx] = _spawn(p["spawn"], n, self.rng, self.w, self.h)
        self.age[idx] = 0.0
        if burst:
            ang = self.rng.random(n) * 6.28
            speed = (0.3 + 0.7 * self.rng.random(n)) * 0.6 * self.h
            self.vel[idx] = np.c_[np.cos(ang), np.sin(ang)] * speed[:, None]
        else:
            jitter = 0.5 + self.rng.random(n)
            self.vel[idx] = np.array(p["velocity"]) * self.h * jitter[:, None]

    def step(self, energy: float, beat: bool, t: float) -> np.ndarray:
        """Advance one frame; the light to add, (h, w) in 0..1."""
        p, dt = self.p, 1.0 / self.fps
        if p["drive"] == "beat":
            if beat:
                idle = np.flatnonzero(self.age >= p["life"])
                self._reset(idle[: max(1, len(self.age) // 3)], burst=True)
            pace = 1.0
        else:
            self._reset(np.flatnonzero(self.age >= p["life"]), burst=False)
            pace = 0.5 + 1.5 * energy
        self.age += dt
        self.vel[:, 1] += p["gravity"] * self.h * dt
        sway = p["sway"] * self.h * np.sin(self.phase + t * 1.7)
        self.pos[:, 0] += (self.vel[:, 0] + sway) * dt * pace
        self.pos[:, 1] += self.vel[:, 1] * dt * pace
        alive = self.age < p["life"]
        fade = np.clip(1.0 - self.age / p["life"], 0.0, 1.0) * np.clip(
            self.age * 4, 0, 1
        )
        light = np.zeros((self.h, self.w))
        # `streak` (seconds of travel) draws a fading tail behind each
        # particle, so fast ones read as sparks rather than dots.
        streak = float(p.get("streak", 0.0))
        steps = np.linspace(0.0, 1.0, 16) if streak > 0 else np.zeros(1)
        for s in steps:
            back = self.vel[alive] * (streak * s * pace)
            x = np.rint(self.pos[alive, 0] - back[:, 0]).astype(int)
            y = np.rint(self.pos[alive, 1] - back[:, 1]).astype(int)
            keep = (x >= 0) & (x < self.w) & (y >= 0) & (y < self.h)
            np.add.at(light, (y[keep], x[keep]), fade[alive][keep] * (1.0 - 0.8 * s))
        # A bright core plus a soft halo: the blur alone spreads a dot's light
        # so thin that small particles vanish.
        halo = light.copy()
        for _ in range(self.radius + 1):
            halo = (
                halo
                + np.roll(halo, 1, 0)
                + np.roll(halo, -1, 0)
                + np.roll(halo, 1, 1)
                + np.roll(halo, -1, 1)
            ) / 5.0
        light = 1.2 * light + 3.0 * halo
        return np.clip(light, 0.0, 1.0)


def wrap(frame_fn):
    """frame_fn with the chosen particle preset drawn over each frame."""

    def framed(ctx):
        preset = PRESETS.get(str(ctx.p("particles", "none")))
        if preset is None:
            yield from frame_fn(ctx)
            return
        layer = Layer(
            preset, float(ctx.p("particle_amount", 1.0)), ctx.w, ctx.h, ctx.fps
        )
        colour = np.array(preset["color"], dtype=np.float64)
        for i, fr in enumerate(frame_fn(ctx)):
            light = layer.step(
                float(ctx.frame_feat("energy", i)),
                bool(ctx.frame_feat("beat", i)),
                i / ctx.fps,
            )
            out = np.asarray(fr, dtype=np.float64) + light[..., None] * colour
            yield np.clip(out, 0, 255).astype(np.uint8)

    return framed
