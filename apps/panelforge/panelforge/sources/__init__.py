"""Site fetchers: one module per site plus one registry entry below.

A source module exposes:

    SITE: str                                  # short id, e.g. "comix"
    def matches(url: str) -> bool
    def fetch_title(url: str, job) -> dict      # {title, chapters:[{number,title,url}]}
    def fetch_chapter(url: str, out_dir: Path, job) -> list[dict]
                                                 # page dicts per CONTRACTS.md chapter.json,
                                                 # files already written under out_dir/pages/

``job`` is a panelforge.jobs.Job (or anything with .log/.progress/.check);
callers may also pass a minimal stand-in for tests.
"""

from __future__ import annotations

import importlib
from types import ModuleType
from typing import Optional

# name -> module path. Add a new site by adding one file plus one line here.
REGISTRY = {
    "comix": "panelforge.sources.comix",
    "generic": "panelforge.sources.generic",
}

_cache: dict[str, ModuleType] = {}


def _load(name: str) -> ModuleType:
    if name not in _cache:
        _cache[name] = importlib.import_module(REGISTRY[name])
    return _cache[name]


def list_sources() -> list[dict]:
    out = []
    for name in REGISTRY:
        mod = _load(name)
        out.append({"name": name, "site": getattr(mod, "SITE", name)})
    return out


def find_for_url(url: str) -> Optional[str]:
    """First registered source (other than 'generic') whose matches() is true."""
    for name in REGISTRY:
        if name == "generic":
            continue
        if _load(name).matches(url):
            return name
    return None


def get(name: str) -> ModuleType:
    if name not in REGISTRY:
        raise KeyError(f"no such source: {name}")
    return _load(name)
