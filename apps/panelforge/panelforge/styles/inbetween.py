"""In-between frames: the 3D layered style with morph transitions, so one
real drawing flows into the next instead of cutting or dissolving. The
in-betweens are optical-flow warps between the two real frames
(`transitions/morph.py`); nothing is generated."""

from .depth3d import Depth3D


class InBetween(Depth3D):
    name = "inbetween"
    label = "In-between frames"
    description = (
        "The 3D layered style where each panel flows into the next: "
        "in-between frames are warps between the two real drawings."
    )
    version = 1
    enabled = True
    preferred_transition = "morph"


STYLE = InBetween()
