"""Voiced slideshow: each panel held still and fitted, with fades between."""

from .base import Style


class Slideshow(Style):
    name = "slideshow"
    label = "Slideshow"
    description = "Each panel shown whole and still, fading from one to the next."
    preferred_transition = "fade"
    settings = {
        "drift": {
            "type": "number",
            "label": "Gentle drift",
            "min": 0.0,
            "max": 0.1,
            "step": 0.01,
            "default": 0.02,
        },
    }

    def render(self, ctx, shot, t):
        dur = max(0.1, float(shot.get("dur", 1.0)))
        drift = float(self.option(ctx, shot, "drift"))
        key = {
            "cx": 0.5,
            "cy": 0.5,
            "zoom": 1.0 + drift * min(1.0, t / dur),
            "rot": 0.0,
        }
        if shot.get("kind") == "reveal":
            return self.draw_camera(ctx, shot, t)
        return self.draw_camera(ctx, shot, t, key=key)


STYLE = Slideshow()
