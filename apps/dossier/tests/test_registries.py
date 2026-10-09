"""The registries are the architecture: adding a source, a subject type or a
page must stay one file. These tests fail if that ever stops being true."""

import entities.registry as entity_registry
import pages.registry as page_registry
from sources.registry import all_sources, for_phase


def test_every_entity_type_has_every_page_it_asks_for():
    missing = [
        (entity.name, page)
        for entity in entity_registry.all_types()
        for page in entity.pages
        if page_registry.get(page) is None
    ]
    assert not missing, f"entity types reference pages that do not exist: {missing}"


def test_every_entity_type_supplies_context_terms():
    identity = {
        "occupation": ["politician"],
        "party": ["A Party"],
        "citizenship": ["Nowhere"],
        "country": ["Nowhere"],
        "ideology": ["centrism"],
        "industry": ["mining"],
        "instance_of": ["thing"],
        "employer": ["Someone"],
    }
    for entity in entity_registry.all_types():
        terms = entity.context_terms(identity)
        assert isinstance(terms, list) and terms, f"{entity.name} produced no context"
        assert isinstance(entity.search_hint(identity), str)


def test_general_sources_serve_every_entity_type():
    """A new subject type must not need edits in sources/."""
    for entity in entity_registry.all_types():
        names = {s.name for s in for_phase("quick", entity.name)}
        assert "wikidata" in names, f"{entity.name} cannot even be identified"
        assert "wikipedia" in names and "ddg_lite" in names


def test_restricted_sources_stay_restricted():
    sec = [s for s in all_sources() if s.name == "sec_edgar"][0]
    assert "*" not in sec.entity_types
    assert "conflict" not in {
        s.name for s in for_phase("quick", "conflict") if s.name == "sec_edgar"
    }


def test_every_source_declares_a_known_tier_and_phase():
    valid_tiers = {
        "primary",
        "encyclopedic",
        "major",
        "regional",
        "aggregator",
        "unknown",
    }
    for source in all_sources():
        assert source.tier in valid_tiers, f"{source.name} has tier {source.tier}"
        assert source.phases, f"{source.name} runs in no phase"
        assert set(source.phases) <= {"identify", "quick", "deep"}


def test_identify_phase_is_wikidata_only():
    """Identity has to be settled before anything else runs."""
    assert {s.name for s in for_phase("identify", "person")} == {"wikidata"}


def test_pages_build_from_an_empty_dossier_without_raising():
    empty = {
        "subject": {},
        "timeline": [],
        "claims": [],
        "quotes": [],
        "relations": [],
        "sources": [],
        "notes": {},
    }
    for page in page_registry.all_pages():
        built = page_registry.build_page(page.name, empty)
        assert "blocks" in built and isinstance(built["blocks"], list)
