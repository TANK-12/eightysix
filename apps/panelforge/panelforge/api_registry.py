"""The declarative list of API modules web_app.py mounts.

Each entry is one module under panelforge/api/ exposing `router`
(a fastapi.APIRouter). Adding an area = one new file + one line here.
A module that fails to import is reported at /api/health instead of
taking the whole app down, so crew helpers can land independently.
"""

API_MODULES = (
    "panelforge.api.library",  # helper-1: fetch, import, PDF export, MediaForge link
    "panelforge.api.detect",  # helper-2: strips, panels, bubbles, OCR
    "panelforge.api.scene",  # helper-3: cast, extras, backgrounds, depth, cutouts
    "panelforge.api.audio",  # helper-4: voices, script, SFX, music
    "panelforge.api.render",  # helper-5: styles, camera, timeline, previews, renders
)
