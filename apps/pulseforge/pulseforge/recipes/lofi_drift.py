"""The flagship Autopilot recipe.

`drift` (Ken Burns over a still image, parallax haze, drifting clouds) is the
scene Emerson singled out as already looking good, so this is the one recipe
tuned hard rather than left at the scene's own defaults: a warm evening grade
instead of the default cool-purple sky, a slightly slower zoom so an hour-long
loop does not feel restless, and a heavier vignette so a busy background photo
still reads as calm "lofi study beats" footage.

`drift` does not consume the shot/preset system the living-still editor uses
(that pipeline is for `living` scenes only) — so "lofi_lake" below is a
credit for where this grade's warmth and vignette numbers came from, not a
preset actually applied at render time. The params dict is what actually
reaches the scene.
"""

RECIPE = {
    "id": "lofi_drift",
    "label": "Lofi Drift",
    "description": "A still image breathing gently under the music — slow "
    "zoom, warm evening grade, drifting clouds. The lofi study-beats look.",
    "scene": "drift",
    "format": "long_1080p",
    "params": {
        "zoom": 0.08,
        "breathe": 0.045,
        "cloud_tint": "#f2c9a0",
        "cloud_amount": 0.3,
        "grade_top": "#2a1a3a",
        "grade_bottom": "#160d22",
        "vignette": 0.4,
    },
    "preset": "lofi_lake",
    "mood": "warm, unhurried, late-evening lofi study beats",
    "thumb_subtitle": "lofi beats to relax / study to",
}
