"""Refreshing a subject should cost only what is new.

Storage was already incremental - a second run added nothing and lost nothing -
but the *work* was not: nothing told the fetcher what was already held, so a
refresh re-downloaded and re-parsed every known article to rediscover it.
"""

from research.fetcher import Document
from research.scoring import SubjectProfile
from sources import ddg_lite
from sources.registry import Context


class _Fetcher:
    """Records what it was actually asked to fetch."""

    stats = {"fetched": 0, "failed": 0, "blocked": 0, "bytes": 0}

    def __init__(self):
        self.requested: list[str] = []

    def articles(self, urls, tier_for=None, origin="", workers=None):
        self.requested.extend(urls)
        return [
            Document(
                url=u,
                title="t",
                text=" ".join(["word"] * 120),
                tier="major",
                origin=origin,
            )
            for u in urls
        ]


def _ctx(fetcher, known=()):
    return Context(
        fetcher=fetcher,
        phase="quick",
        entity_type="person",
        budget=10,
        log=lambda m: None,
        identity={"context_hint": ""},
        known_urls=set(known),
    )


FOUND = [
    "https://bbc.co.uk/news/one",
    "https://reuters.com/two",
    "https://theguardian.com/three",
    "https://apnews.com/four",
]


def test_a_first_run_fetches_everything(monkeypatch):
    monkeypatch.setattr(ddg_lite, "search", lambda ctx, q, limit: list(FOUND))
    f = _Fetcher()
    harvest = ddg_lite.fetch(SubjectProfile(name="X"), _ctx(f))
    assert sorted(f.requested) == sorted(FOUND)
    assert len(harvest.documents) == 4
    assert harvest.skipped_known == 0


def test_a_refresh_only_fetches_what_is_new(monkeypatch):
    monkeypatch.setattr(ddg_lite, "search", lambda ctx, q, limit: list(FOUND))
    f = _Fetcher()
    held = FOUND[:3]
    harvest = ddg_lite.fetch(SubjectProfile(name="X"), _ctx(f, known=held))
    assert f.requested == [FOUND[3]], "already-held articles were refetched"
    assert harvest.skipped_known == 3
    assert len(harvest.documents) == 1


def test_nothing_new_means_nothing_fetched(monkeypatch):
    monkeypatch.setattr(ddg_lite, "search", lambda ctx, q, limit: list(FOUND))
    f = _Fetcher()
    harvest = ddg_lite.fetch(SubjectProfile(name="X"), _ctx(f, known=FOUND))
    assert f.requested == []
    assert harvest.skipped_known == 4


def test_the_skip_matches_on_canonical_url(monkeypatch):
    """A stored URL and the same article with tracking parameters are one
    document; the skip has to see that or it refetches anyway."""
    dirty = "https://www.bbc.co.uk/news/one?utm_source=twitter"
    monkeypatch.setattr(ddg_lite, "search", lambda ctx, q, limit: [dirty])
    f = _Fetcher()
    harvest = ddg_lite.fetch(
        SubjectProfile(name="X"), _ctx(f, known=["https://bbc.co.uk/news/one"])
    )
    assert f.requested == [], "tracking parameters defeated the skip"
    assert harvest.skipped_known == 1


def test_the_harvest_carries_the_count_through_extend():
    from sources.registry import Harvest

    a, b = Harvest(), Harvest()
    a.skipped_known, b.skipped_known = 3, 4
    a.extend(b)
    assert a.skipped_known == 7
