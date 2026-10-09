"""Every catalog part's size_bytes matches Hugging Face (network; opt-in).

Run with AI_STUDIO_CHECK_HF=1. A HEAD on the resolve URL gives the file size
in X-Linked-Size; gated repos answer 401 to that, so their size comes from the
public file listing (the HF API tree) instead.
"""

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from catalog import CATALOG  # noqa: E402  # pyright: ignore[reportMissingImports]

pytestmark = pytest.mark.skipif(
    not os.environ.get("AI_STUDIO_CHECK_HF"), reason="network check, opt-in"
)

_trees = {}


def _tree_size(url):
    repo_path = url.split("https://huggingface.co/", 1)[1]
    repo = "/".join(repo_path.split("/")[:2])
    path = urllib.parse.unquote(repo_path.split("/resolve/main/", 1)[1])
    if repo not in _trees:
        api = f"https://huggingface.co/api/models/{repo}/tree/main?recursive=true"
        with urllib.request.urlopen(api, timeout=30) as r:
            _trees[repo] = {
                f["path"]: f.get("lfs", {}).get("size", f["size"])
                for f in json.load(r)
                if f["type"] == "file"
            }
    return _trees[repo].get(path)


def _head_size(url):
    req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "x"})

    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *a, **k):
            return None

    opener = urllib.request.build_opener(NoRedirect)
    try:
        resp = opener.open(req, timeout=30)
        headers = resp.headers
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            return None
        headers = e.headers
    # Only LFS files carry X-Linked-Size; a small file's redirect has no size
    # of its own, so those come from the file listing.
    size = headers.get("X-Linked-Size")
    return int(size) if size else None


PARTS = sorted(
    {
        (p["url"], p["size_bytes"])
        for e in CATALOG.values()
        for p in e["parts"]
        if p["url"].startswith("https://huggingface.co/")
    }
)  # other hosts (pinned GitHub archives) send no size without a full GET


@pytest.mark.parametrize("url,size", PARTS)
def test_part_size_matches_hugging_face(url, size):
    got = _head_size(url)
    if got is None:
        got = _tree_size(url)
    assert got == size, url
