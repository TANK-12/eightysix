"""Intelligent camera: view math (keys.py) and the planning rules (rules.py)."""

from .keys import affine, clamp_key, key_inside, sample, shake_offset, view_size
from .rules import (
    RULES,
    CameraSettings,
    Character,
    DirectionState,
    Line,
    PanelInfo,
    ShotPlan,
    line_duration,
    plan_shot,
)

__all__ = [
    "RULES",
    "CameraSettings",
    "Character",
    "DirectionState",
    "Line",
    "PanelInfo",
    "ShotPlan",
    "affine",
    "clamp_key",
    "key_inside",
    "line_duration",
    "plan_shot",
    "sample",
    "shake_offset",
    "view_size",
]
