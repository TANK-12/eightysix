"""Lofi Radio: the whole inbox as one long mix, the format lofi channels earn on.

Every song in the folder plays in order, repeating to `minutes`. Each picture
becomes a living still with the built-in `lofi_lake` look (clouds, water,
birds, dust, found per picture), one picture per song. Soft rain sits under
the music, and the description gets a chapter per song. It renders on the
living-still path, which draws one loop per picture and repeats it, so an hour
takes minutes rather than an hour.
"""

RECIPE = {
    "id": "lofi_radio",
    "label": "Lofi Radio",
    "description": "Every song in the folder as one long mix (an hour by "
    "default), your pictures gently alive with clouds, water and birds, soft "
    "rain underneath and a chapter per song. Needs a pictures folder.",
    "scene": "living",
    "format": "long_1080p",
    "per": "folder",
    "needs_art": True,
    "minutes": 60,
    "params": {},
    "look": {"preset": "lofi_lake", "grade": "faded", "grade_amount": 0.45},
    "ambience": {"bed": "rain", "level": 0.12},
    "mood": "warm, unhurried lofi radio to study and relax to",
    "tagline": "{length} of lofi beats to study and relax to",
    "thumb_subtitle": "lofi radio · {length}",  # {length} -> "1 hour"
}
