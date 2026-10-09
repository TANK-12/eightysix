"""A researched subject must be stored under its own name.

This reproduces a real data loss: the loop that gathered sources concurrently
used `name` as its loop variable, shadowing the function's `name` parameter, so
the slug was taken from whichever source adapter finished last. 146 subjects
were written to directories called "wikipedia" and "worldbank", overwriting one
another. Nothing errored, and every job reported success.
"""

import pytest

import research.pipeline as pipeline
from research.fetcher import Document
from sources.registry import Harvest, SourceSpec


class _FakeFetcher:
    stats = {"fetched": 0, "failed": 0, "blocked": 0, "bytes": 0}

    def close(self):
        pass


def _spec(name):
    """A source whose name is deliberately not the subject's."""

    def fetch(subject, ctx):
        h = Harvest()
        h.documents.append(
            Document(
                url=f"https://{name}.example/a",
                title=f"{subject.name} coverage",
                text=" ".join([subject.name, "did something notable."] * 40),
                tier="major",
                origin=name,
            )
        )
        if name == "wikidata":
            h.identity.update({"qid": "Q1", "label": subject.name, "description": "x"})
        return h

    return SourceSpec(
        name=name,
        label=name,
        tier="major",
        phases=("identify", "quick", "deep"),
        entity_types=("*",),
        fetch=fetch,
    )


@pytest.fixture
def offline(monkeypatch):
    sources = {
        "identify": [_spec("wikidata")],
        "quick": [_spec("wikidata"), _spec("wikipedia"), _spec("worldbank")],
    }
    monkeypatch.setattr(pipeline, "for_phase", lambda phase, et: sources.get(phase, []))
    monkeypatch.setattr(pipeline, "shared_fetcher", lambda: _FakeFetcher())
    monkeypatch.setattr(pipeline.llm, "status", lambda: {"jan": False})


def test_the_slug_comes_from_the_subject_not_a_source(offline):
    result = pipeline.research("Andy Burnham", entity_type="person", log=lambda m: None)
    assert result["slug"] == "andy-burnham"
    assert result["slug"] not in ("wikipedia", "worldbank", "wikidata")


def test_every_subject_gets_its_own_slug(offline):
    """The failure showed up as many subjects sharing one directory."""
    names = ["European Commission", "Andy Burnham", "Japan", "Likud"]
    slugs = [
        pipeline.research(n, entity_type="person", log=lambda m: None)["slug"]
        for n in names
    ]
    assert slugs == ["european-commission", "andy-burnham", "japan", "likud"]
    assert len(set(slugs)) == len(names), "subjects collided onto one slug"


def test_the_name_survives_concurrent_source_gathering(offline):
    result = pipeline.research("Japan", entity_type="country", log=lambda m: None)
    assert result["name"] == "Japan"
    assert result["slug"] == "japan"
