"""GDELT: worldwide news coverage, including outside the English-language press.

Useful for figures who are covered heavily in one country and barely elsewhere.
It is a free service with no key and a firm rate limit - a 429 was returned
while this was being built - so it backs off and gives up quietly rather than
holding up a research run. It is never on the critical path.
"""

from __future__ import annotations

import time

from research.canonical import registrable_domain
from research.fetcher import Document, _iso
from research.scoring import SubjectProfile

from .registry import Context, Harvest, SourceSpec

API = "https://api.gdeltproject.org/api/v2/doc/doc"
BACKOFF = (2.0, 6.0)


def fetch(subject: SubjectProfile, ctx: Context) -> Harvest:
    harvest = Harvest()
    params = {
        "query": f'"{subject.name}"',
        "mode": "artlist",
        "format": "json",
        "maxrecords": str(min(ctx.budget * 2, 75)),
        "sort": "hybridrel",
    }
    data = None
    for attempt, pause in enumerate((0.0, *BACKOFF)):
        if pause:
            time.sleep(pause)
        r = ctx.fetcher.get(API, api=True, params=params)
        if r is None:
            continue
        if r.status_code == 429:
            continue
        try:
            data = r.json()
            break
        except Exception:
            continue
    if not data:
        harvest.notes.append("GDELT was rate-limited or unreachable; skipped")
        ctx.log("GDELT: skipped (rate-limited)")
        return harvest

    for art in (data.get("articles") or [])[: ctx.budget * 2]:
        url = art.get("url") or ""
        if not url:
            continue
        title = art.get("title") or ""
        published = _iso((art.get("seendate") or "")[:8].replace("", "")) or ""
        if not published and art.get("seendate"):
            raw = art["seendate"][:8]
            published = f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}" if len(raw) == 8 else ""
        harvest.documents.append(
            Document(
                url=url,
                title=title,
                text=f"{title}. {art.get('domain','')} "
                f"({art.get('sourcecountry','')}, {art.get('language','')}).",
                published=published,
                tier="unknown",
                origin="gdelt",
                domain=registrable_domain(url),
            )
        )
    ctx.log(f"GDELT: {len(harvest.documents)} articles indexed")
    return harvest


SPEC = SourceSpec(
    name="gdelt",
    label="GDELT",
    tier="unknown",
    phases=("deep",),
    entity_types=("*",),
    fetch=fetch,
    description="International news index, including non-English coverage.",
)
