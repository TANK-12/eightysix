"""Guards the bug found 2026-09-27: jan-tune and calendar both claimed port
8453 in forge_app.json. forge.py treats a port that is already answering as
an always-on backend and points the newer app's window at it instead of
starting its own server, so jan-tune silently showed calendar's backend
(all its API calls 404'd against calendar's routes). Every app's port must
be unique across the whole ~/Forge/apps/ registry."""

import json
from pathlib import Path

APPS_DIR = Path(__file__).resolve().parents[2]


def _load_manifests():
    manifests = {}
    for manifest_path in sorted(APPS_DIR.glob("*/forge_app.json")):
        with open(manifest_path) as f:
            manifests[manifest_path.parent.name] = json.load(f)
    return manifests


def test_jan_tune_port_is_not_shared_with_another_app():
    manifests = _load_manifests()
    assert "jan-tune" in manifests, "jan-tune's own forge_app.json is missing"
    my_port = manifests["jan-tune"]["port"]

    collisions = [
        name
        for name, m in manifests.items()
        if name != "jan-tune" and m.get("port") == my_port
    ]
    assert collisions == [], (
        f"jan-tune's port {my_port} is also claimed by {collisions}; "
        "each app in apps/ must have a unique port"
    )


def test_no_two_apps_share_a_port():
    manifests = _load_manifests()
    by_port = {}
    for name, m in manifests.items():
        by_port.setdefault(m["port"], []).append(name)

    dupes = {port: names for port, names in by_port.items() if len(names) > 1}
    assert dupes == {}, f"duplicate ports across apps/: {dupes}"
