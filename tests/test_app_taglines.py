"""Every app's tagline fits its home-screen tile.

A tile shows the tagline in at most two lines (hub/index.html `.tile .tag`,
`-webkit-line-clamp: 2`). At the narrowest tile (--tile-w 236px, 12px text)
that is about 149px a line. 45 characters is a rough guide, not a promise:
where the words break matters too (on 2026-09-27 two 41-character taglines
still took three lines in headless Chrome), so recheck the real tile after a
long one. The full description belongs in the app's README.
"""

import json
from pathlib import Path

APPS = Path(__file__).resolve().parents[1] / "apps"
LIMIT = 45


def test_every_tagline_fits_two_lines_of_a_tile():
    long = {}
    for manifest in sorted(APPS.glob("*/forge_app.json")):
        tagline = json.loads(manifest.read_text()).get("tagline", "")
        if len(tagline) > LIMIT:
            long[manifest.parent.name] = f"{len(tagline)}: {tagline}"
    assert not long, long
