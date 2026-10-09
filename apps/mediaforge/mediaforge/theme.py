"""Dark/light palette + fonts for the customtkinter UI."""

from .config import ACCENTS

DARK = {
    "bg": "#0e1116", "surface": "#161b22", "surface_2": "#1c2431",
    "border": "#2b3240", "text": "#e6edf3", "text_dim": "#8b949e",
    "good": "#3fb950", "warn": "#d29922", "bad": "#f85149", "console": "#0a0d12",
}
LIGHT = {
    "bg": "#f5f6f8", "surface": "#ffffff", "surface_2": "#eceef2",
    "border": "#d6d9e0", "text": "#161b22", "text_dim": "#5b616e",
    "good": "#2f9e44", "warn": "#b8860b", "bad": "#e03131", "console": "#f0f1f4",
}

FONT = "Inter"
MONO = "JetBrains Mono"


def palette(mode):
    return DARK if mode == "dark" else LIGHT


def accent(name):
    return ACCENTS.get(name, ACCENTS["cyan"])
