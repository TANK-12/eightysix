"""Motion comic: the intelligent camera pans and zooms through each panel,
with the effects layer (speed lines, impact, shake, particles, glow)."""

from .base import Style


class Motion(Style):
    name = "motion"
    label = "Motion comic"
    description = "Camera moves through each panel, bubble by bubble, with shake and effects on action."
    settings = {}

    def render(self, ctx, shot, t):
        return self.draw_camera(ctx, shot, t)


STYLE = Motion()
