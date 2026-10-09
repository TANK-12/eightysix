"""The fact table. Adding a fact to every dossier must stay one line in it."""

import pytest

from sources.properties import GROUP_ORDER, PROPERTIES, grouped
from sources.wikidata import _readable_quantity


def test_every_property_is_well_formed():
    for code, entry in PROPERTIES.items():
        assert code.startswith("P") and code[1:].isdigit(), code
        label, group, kind = entry
        assert label and label[0].isupper(), f"{code} label should read as a heading"
        assert group in GROUP_ORDER, f"{code} is in unknown group {group}"
        assert kind in ("list", "one", "time"), f"{code} has odd kind {kind}"


def test_labels_are_unique():
    """Two properties sharing a label would silently overwrite each other."""
    labels = [label for label, _, _ in PROPERTIES.values()]
    duplicates = {l for l in labels if labels.count(l) > 1}
    assert not duplicates, f"duplicate fact labels: {duplicates}"


def test_identifier_properties_are_excluded():
    """The bulk of a Wikidata entity is cross-reference ids nobody reads."""
    for code in ("P214", "P213", "P227", "P18", "P625"):
        assert code not in PROPERTIES


def test_grouped_orders_panels_and_skips_empties():
    panels = grouped(
        {
            "Occupation": ["politician"],
            "Born": "1954-07-17",
            "Awards": ["Charlemagne Prize", "Order of Merit"],
            "Revenue": "",
            "Nickname": [],
        }
    )
    assert [p["group"] for p in panels] == ["identity", "life", "record"]
    record = [p for p in panels if p["group"] == "record"][0]
    assert record["rows"][0]["value"] == "Charlemagne Prize, Order of Merit"
    assert all(p["rows"] for p in panels), "an empty panel should not be produced"


def test_grouped_on_an_empty_identity_is_empty():
    assert grouped({}) == []


@pytest.mark.parametrize(
    "raw,units,expected",
    [
        ("5050922925047|Q4917", {"Q4917": "US dollar"}, "5.1 trillion US dollar"),
        ("4685592577804|Q4917", {"Q4917": "US dollar"}, "4.7 trillion US dollar"),
        ("250000000|Q4917", {"Q4917": "US dollar"}, "250.0 million US dollar"),
        ("83500000|", {}, "83.5 million"),
        ("630|", {}, "630"),
        ("1.5|Q11229", {"Q11229": "percent"}, "1.50 percent"),
        ("not a number|", {}, "not a number"),
    ],
)
def test_quantities_read_like_a_person_wrote_them(raw, units, expected):
    """Quantities - net worth, revenue, population, casualties - were being
    dropped entirely before the fact table existed."""
    assert _readable_quantity(raw, units) == expected


def test_panels_are_scoped_to_the_kind_of_subject():
    """A country picked up "Deaths: 593,865" from a war statement and a seat
    count from a chamber; a war has no doctoral advisor."""
    identity = {
        "Population": "68.6 million",
        "Deaths": "593,865",
        "Seats": "81",
        "Doctoral advisor": "someone",
        "Type": ["sovereign state"],
    }
    labels = {
        p["group"]: [r["label"] for r in p["rows"]]
        for p in grouped(identity, "country")
    }
    assert "state" in labels and "Population" in labels["state"]
    assert "conflict" not in labels, "a country should not show conflict casualties"
    assert "organisation" not in labels, "a country should not show a seat count"
    assert "education" not in labels


def test_a_conflict_keeps_its_casualties():
    labels = {p["group"] for p in grouped({"Deaths": "1,200"}, "conflict")}
    assert "conflict" in labels


def test_no_entity_type_shows_everything():
    """Callers that do not know the type must not silently lose facts."""
    panels = grouped({"Deaths": "1,200", "Population": "5 million"})
    assert {p["group"] for p in panels} == {"conflict", "state"}


def test_unresolved_q_numbers_are_dropped():
    """An entity with no English label is not a fact anyone can use."""
    panels = grouped({"Head of state": ["Q3052772", "François Hollande"]}, "country")
    value = panels[0]["rows"][0]["value"]
    assert value == "François Hollande"


def test_a_fact_that_is_only_an_unresolved_id_disappears():
    assert grouped({"Head of state": ["Q3052772"]}, "country") == []
    assert grouped({"Chief executive": "Q99999"}, "organisation") == []
