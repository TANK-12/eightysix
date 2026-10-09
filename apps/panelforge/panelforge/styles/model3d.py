"""Real 3D character models: registered for later, disabled for now."""

from .motion import Motion


class Model3D(Motion):
    name = "model3d"
    label = "3D models (later)"
    description = "Reserved slot for real 3D character models. Renders as motion comic until built."
    enabled = False


STYLE = Model3D()
