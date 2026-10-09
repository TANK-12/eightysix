"""
Visual theme for the customtkinter UI. One accent, two modes.
"""

ACCENTS = {
    "forge":  {"primary": "#1f6feb", "hover": "#388bfd", "on": "#ffffff"},
    "ember":  {"primary": "#e8590c", "hover": "#f76707", "on": "#ffffff"},
    "moss":   {"primary": "#2f9e44", "hover": "#37b24d", "on": "#ffffff"},
    "plum":   {"primary": "#9c36b5", "hover": "#ae3ec9", "on": "#ffffff"},
}

DARK = {
    "bg":        "#0d1117",
    "surface":   "#161b22",
    "surface_2": "#1c2330",
    "border":    "#2d333b",
    "text":      "#e6edf3",
    "text_dim":  "#8b949e",
    "good":      "#3fb950",
    "warn":      "#d29922",
    "bad":       "#f85149",
}

LIGHT = {
    "bg":        "#f6f7f9",
    "surface":   "#ffffff",
    "surface_2": "#eef1f5",
    "border":    "#d8dade",
    "text":      "#16181d",
    "text_dim":  "#5b616e",
    "good":      "#2f9e44",
    "warn":      "#b8860b",
    "bad":       "#e03131",
}

FONT_FAMILY = "Inter"          # customtkinter falls back gracefully
MONO_FAMILY = "JetBrains Mono"


def palette(mode):
    return DARK if mode == "dark" else LIGHT


def accent(name):
    return ACCENTS.get(name, ACCENTS["forge"])
