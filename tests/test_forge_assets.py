"""shared/forge_assets.py with a fake network (no downloads)."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "shared"))
import forge_assets  # noqa: E402

HDR = b"#?RADIANCE fake"
GLTF, BIN = b'{"asset":{}}', b"\x00\x01"


def md5(b):
    return hashlib.md5(b).hexdigest()


ROUTES = {
    "/assets?t=hdris": {
        "sunset_a": {
            "name": "Sunset A",
            "tags": ["sunset", "sky"],
            "categories": ["outdoor"],
            "download_count": 5,
        },
        "sunset_b": {
            "name": "Sunset B",
            "tags": ["sunset"],
            "categories": ["urban"],
            "download_count": 50,
        },
        "studio": {
            "name": "Studio",
            "tags": ["indoor"],
            "categories": [],
            "download_count": 99,
        },
    },
    "/files/sunset_a": {
        "hdri": {
            "1k": {"hdr": {"url": "https://dl/x/sunset_a_1k.hdr", "md5": md5(HDR)}}
        }
    },
    "/info/sunset_a": {"name": "Sunset A", "authors": {"Greg": "All"}},
    "/files/chair": {
        "gltf": {
            "1k": {
                "gltf": {
                    "url": "https://dl/m/chair.gltf",
                    "md5": md5(GLTF),
                    "include": {
                        "chair.bin": {"url": "https://dl/m/chair.bin", "md5": md5(BIN)}
                    },
                }
            }
        }
    },
    "/info/chair": {"name": "Chair", "authors": {"Kim": "All"}},
    "/files/evil": {
        "gltf": {
            "1k": {
                "gltf": {
                    "url": "https://dl/m/e.gltf",
                    "include": {"../../x": {"url": "https://dl/m/x"}},
                }
            }
        }
    },
    "/info/evil": {},
}
BLOBS = {
    "https://dl/x/sunset_a_1k.hdr": HDR,
    "https://dl/m/chair.gltf": GLTF,
    "https://dl/m/chair.bin": BIN,
    "https://dl/m/e.gltf": GLTF,
    "https://dl/m/x": b"x",
}


@pytest.fixture
def net(tmp_path, monkeypatch):
    monkeypatch.setattr(forge_assets, "ROOT", tmp_path)
    calls = []

    def fetch(url):
        calls.append(url)
        if url.startswith(forge_assets.API):
            return json.dumps(ROUTES[url[len(forge_assets.API) :]]).encode()
        return BLOBS[url]

    return fetch, calls


def test_search_matches_all_words_most_downloaded_first(net):
    fetch, _ = net
    ids = [h["id"] for h in forge_assets.search("hdris", "sunset", fetch=fetch)]
    assert ids == ["sunset_b", "sunset_a"]
    assert [
        h["id"] for h in forge_assets.search("hdris", "sunset outdoor", fetch=fetch)
    ] == ["sunset_a"]


def test_search_rejects_unknown_kind(net):
    with pytest.raises(ValueError):
        forge_assets.search("sounds", fetch=net[0])


def test_get_hdri_writes_manifest_and_caches(net):
    fetch, calls = net
    m = forge_assets.get("sunset_a", fetch=fetch)
    assert m["kind"] == "hdri" and m["license"] == "CC0" and m["authors"] == ["Greg"]
    assert Path(m["main"]).read_bytes() == HDR
    n = len(calls)
    assert forge_assets.get("sunset_a", fetch=fetch) == m
    assert len(calls) == n  # second call is served from disk
    assert [x["id"] for x in forge_assets.local()] == ["sunset_a"]


def test_get_model_includes_buffers(net):
    m = forge_assets.get("chair", fetch=net[0])
    assert m["kind"] == "model" and m["main"].endswith("chair.gltf")
    assert (Path(m["dir"]) / "chair.bin").read_bytes() == BIN


def test_get_refuses_paths_outside_asset_dir(net):
    with pytest.raises(ValueError, match="unsafe"):
        forge_assets.get("evil", fetch=net[0])


def test_missing_resolution_is_explained(net):
    with pytest.raises(ValueError, match="1k"):
        forge_assets.get("sunset_a", res="8k", fetch=net[0])


def test_checksum_mismatch_is_refused(net, monkeypatch):
    fetch, _ = net
    monkeypatch.setitem(BLOBS, "https://dl/m/chair.bin", b"tampered")
    with pytest.raises(ValueError, match="checksum"):
        forge_assets.get("chair", fetch=fetch)
