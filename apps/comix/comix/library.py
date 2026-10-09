"""Library sync: add every series on Emerson's library page to the store."""

from __future__ import annotations

from types import ModuleType
from typing import Callable

from comix.store import Store


def sync(
    store: Store,
    src: ModuleType,
    name: str,
    link: str,
    cookies: list[dict],
    say: Callable[[str], None],
) -> dict:
    """Nothing is queued: each new series waits for its groups to be picked
    (his choice: pick per series). Series still waiting for that choice have
    nothing downloaded, so they are listed again to pick up chapters an
    earlier, cut-short list missed."""
    found = src.list_library(link, cookies, say)
    known = {s["url"]: s for s in store.series()}
    added = relisted = 0
    for n, item in enumerate(found, 1):
        old = known.get(item["url"])
        if old and old["group_mode"] != "pending":
            continue
        say(f"({n}/{len(found)}) listing {item['title'] or item['url']}")
        try:
            info = src.list_series(item["url"], cookies, say)
        except Exception as e:
            say(f"skipped {item['url']}: {e}")
            continue
        store.save_series(
            item["url"],
            info["title"],
            name,
            info["rows"],
            "pending",
            [],
            from_library=True,
        )
        if old:
            relisted += 1
        else:
            added += 1
    say(
        f"library: {len(found)} series found, {added} new, "
        f"{relisted} waiting for groups listed again"
    )
    return {"found": len(found), "added": added, "relisted": relisted}
