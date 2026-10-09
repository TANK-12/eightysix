"""The common style interface."""

import cv2
import numpy as np


class Style:
    name = "base"
    label = "Base"
    description = ""
    enabled = True
    version = 1  # bump to invalidate cached shot clips
    preferred_transition: str | None = None
    settings: dict = {}

    def describe(self) -> dict:
        return {
            "name": self.name,
            "label": self.label,
            "description": self.description,
            "enabled": self.enabled,
            "preferred_transition": self.preferred_transition,
            "settings": self.settings,
        }

    def option(self, ctx, shot, key):
        """A style setting: shot override, then timeline settings, then default."""
        own = (shot.get("style_settings") or {}).get(key)
        if own is not None:
            return own
        glob = (ctx.settings.get("style_settings") or {}).get(self.name, {}).get(key)
        if glob is not None:
            return glob
        return self.settings.get(key, {}).get("default")

    def render(self, ctx, shot, t) -> np.ndarray:
        raise NotImplementedError

    # shared drawing helper used by most styles
    def draw_camera(self, ctx, shot, t, canvas=None, key=None) -> np.ndarray:
        """The shot's source image through the camera, over the backdrop."""
        src = ctx.source(shot)
        m = ctx.matrix(shot, t, key=key)
        canvas = ctx.backdrop(shot).copy() if canvas is None else canvas
        cv2.warpAffine(
            src,
            m,
            ctx.out,
            dst=canvas,
            flags=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_TRANSPARENT,
        )
        return canvas
