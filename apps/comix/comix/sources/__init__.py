"""Site sources: one module per site plus one line in REGISTRY.

A source module exposes:
    SITE: str                 short id shown in the page
    DOMAIN: str               cookie domain borrowed from the Forge Browser
    HOME: str                 where "Log in" opens the Forge Browser
    def matches(url) -> bool
    def list_series(url, cookies, log) -> {"title", "groups", "rows":
        [{"number", "group", "url", "label"}]}   one row per chapter *and* group;
        "group" is never blank (UNKNOWN_GROUP when the site names nobody)
    def list_library(page_url, cookies, log) -> [{"url", "title"}]   every page
        of the library, starting from page 1 whichever page the link is on
    def reader(cookies, slot) -> Reader           see comix_to.Reader
"""

from __future__ import annotations

import importlib
from types import ModuleType

# The group name given to chapters the site shows with no scan group at all.
UNKNOWN_GROUP = "Unknown group"

REGISTRY = {
    "comix": "comix.sources.comix_to",
}

_cache: dict[str, ModuleType] = {}


def get(name: str) -> ModuleType:
    if name not in _cache:
        _cache[name] = importlib.import_module(REGISTRY[name])
    return _cache[name]


def find_for_url(url: str) -> str | None:
    for name in REGISTRY:
        if get(name).matches(url):
            return name
    return None


def all_sources() -> list[dict]:
    return [{"name": n, "site": get(n).SITE, "home": get(n).HOME} for n in REGISTRY]
