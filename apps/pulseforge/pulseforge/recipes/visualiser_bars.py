"""Classic reactive-bars channel look, 16:9 for a regular YouTube upload."""

RECIPE = {
    "id": "visualiser_bars",
    "label": "Visualiser Bars",
    "description": "Frequency bars and a circular equaliser riding the "
    "track, over your background image or a colour gradient. The classic "
    "music-channel look.",
    "scene": "bars",
    "format": "long_1080p",
    "params": {
        "color_a": "#d16bff",
        "color_b": "#3bd6ff",
        "bg_top": "#12071e",
        "bg_bottom": "#03040a",
        "use_image": True,
        "style": "soft",
        "bar_count": 72,
        "bar_height": 0.26,
        "bar_opacity": 0.85,
        "flash": 0.25,
        "image_dim": 0.25,
        "ring": True,
    },
    "mood": "energetic, colourful, a music-channel visualiser",
    "thumb_subtitle": "audio visualiser",
}
