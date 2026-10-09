"""The connection graph: how two subjects turn out to be linked.

Every hop has to come from a stored relation, so these build real subject
directories on disk rather than stubbing the reader.
"""

import dossier
import store
from research import graph
from sources.properties import RELATIONS, edges_from


def hold(tmp_path, name, relations, entity_type="person"):
    """Write a subject with relations, the way a finished job would."""
    slug = store.slugify(name)
    d = store.ensure_subject(slug, tmp_path)
    store.write_json(
        d / dossier.FILES["subject"],
        {"slug": slug, "name": name, "entity_type": entity_type, "depth": "quick"},
    )
    store.write_json(
        d / dossier.FILES["relations"],
        [
            {"relation": r, "target": t, "source_id": "wikidata:Q1", "url": "u"}
            for r, t in relations
        ],
    )
    dossier.reindex(tmp_path)
    return slug


# --- the table that decides what counts as a connection ---------------------


def test_edges_are_built_from_the_table_not_named_in_code():
    """The harvest used to name four relations inline, which is why the graph
    was thin. Anything in the table should become an edge."""
    identity = {
        "Educated at": ["University of Leipzig"],
        "Spouse": ["Joachim Sauer"],
        "Positions held": ["Chancellor of Germany"],
        "Father": "Horst Kasner",
    }
    edges = dict((t, r) for r, t in edges_from(identity))
    assert edges["University of Leipzig"] == "educated at"
    assert edges["Joachim Sauer"] == "spouse"
    assert edges["Chancellor of Germany"] == "held office"
    assert edges["Horst Kasner"] == "child of", "a single-value fact was skipped"


def test_the_same_target_under_two_labels_is_one_edge():
    """A party arrives as both 'Party' and 'Member of'. One edge is enough."""
    edges = edges_from({"Party": ["CDU"], "Member of": ["cdu"]})
    assert len(edges) == 1


def test_empty_and_non_string_values_are_ignored():
    assert edges_from({"Spouse": ["", "   ", None, 42]}) == []
    assert edges_from({}) == []


def test_the_table_covers_more_than_the_four_it_started_with():
    for label in ("Party", "Employer", "Educated at", "Ideology"):
        assert label in RELATIONS, f"{label} was dropped in the rewrite"
    assert len(RELATIONS) > 20, "the graph is still thin"


# --- building the graph -----------------------------------------------------


def test_a_relation_target_that_has_its_own_dossier_becomes_one_node(tmp_path):
    hold(tmp_path, "Angela Merkel", [("member of", "CDU")])
    hold(tmp_path, "CDU", [], entity_type="party")
    g = graph.build(tmp_path)

    cdu = g.nodes[store.slugify("CDU")]
    assert cdu["held"] is True and cdu["entity_type"] == "party"
    assert cdu["slug"] == "cdu"


def test_a_target_with_no_dossier_is_still_a_node(tmp_path):
    hold(tmp_path, "Angela Merkel", [("educated at", "University of Leipzig")])
    g = graph.build(tmp_path)

    node = g.nodes[store.slugify("University of Leipzig")]
    assert node["held"] is False and node["name"] == "University of Leipzig"


# --- how are they linked ----------------------------------------------------


def test_two_subjects_meet_at_something_neither_has_a_dossier_for(tmp_path):
    """The interesting answer: two people who never mention each other were
    educated in the same place."""
    hold(tmp_path, "Angela Merkel", [("educated at", "University of Leipzig")])
    hold(tmp_path, "Someone Else", [("educated at", "University of Leipzig")])
    g = graph.build(tmp_path)

    hops = g.path("angela-merkel", "someone-else")
    assert hops is not None, "no path found between two alumni of one university"
    assert len(hops) == 2
    assert hops[0]["to"]["name"] == "University of Leipzig"
    assert hops[1]["to"]["name"] == "Someone Else"
    assert hops[0]["relation"] == "educated at"


def test_a_path_records_which_subject_stated_each_hop(tmp_path):
    """A chain has to be checkable, so every hop names the file it came from."""
    hold(tmp_path, "Angela Merkel", [("member of", "CDU")])
    hold(tmp_path, "CDU", [])
    g = graph.build(tmp_path)

    hops = g.path("angela-merkel", "cdu")
    assert hops and hops[0]["stated_by"] == "Angela Merkel"


def test_the_direction_a_relation_was_recorded_in_does_not_block_a_path(tmp_path):
    """Merkel names the CDU; the CDU does not name Merkel. Asking the other way
    round still has to work."""
    hold(tmp_path, "Angela Merkel", [("member of", "CDU")])
    hold(tmp_path, "CDU", [])
    g = graph.build(tmp_path)

    assert g.path("cdu", "angela-merkel") is not None


def test_unconnected_subjects_return_no_path(tmp_path):
    hold(tmp_path, "Angela Merkel", [("member of", "CDU")])
    hold(tmp_path, "Unrelated Person", [("member of", "Some Other Party")])
    g = graph.build(tmp_path)

    assert g.path("angela-merkel", "unrelated-person") is None


def test_a_path_to_an_unknown_subject_is_none(tmp_path):
    hold(tmp_path, "Angela Merkel", [])
    g = graph.build(tmp_path)
    assert g.path("angela-merkel", "nobody-at-all") is None


def test_the_shortest_chain_is_the_one_returned(tmp_path):
    hold(tmp_path, "A", [("member of", "Party"), ("educated at", "Long Way")])
    hold(tmp_path, "Long Way", [("member of", "Longer Way")])
    hold(tmp_path, "Longer Way", [("member of", "Party")])
    hold(tmp_path, "Party", [])
    g = graph.build(tmp_path)

    hops = g.path("a", "party")
    assert hops is not None and len(hops) == 1


# --- the neighbourhood the mind map draws -----------------------------------


def test_the_neighbourhood_reaches_past_immediate_links(tmp_path):
    hold(tmp_path, "A", [("member of", "Party")])
    hold(tmp_path, "B", [("member of", "Party")])
    g = graph.build(tmp_path)

    around = g.around("a", depth=2)
    names = {n["name"] for n in around["nodes"]}
    assert {"A", "Party", "B"} <= names
    assert around["centre"] == "a"


def test_the_neighbourhood_is_budgeted_so_it_stays_readable(tmp_path):
    hold(tmp_path, "Hub", [("member of", f"Thing {i}") for i in range(60)])
    g = graph.build(tmp_path)

    around = g.around("hub", depth=2, budget=20)
    assert len(around["nodes"]) == 20
    assert around["truncated"] is True
    # Every edge drawn must join two nodes that survived the budget.
    keys = {n["key"] for n in around["nodes"]}
    assert all(e["from"] in keys and e["to"] in keys for e in around["edges"])


def test_an_unknown_centre_draws_nothing(tmp_path):
    g = graph.build(tmp_path)
    assert g.around("nobody")["nodes"] == []


# --- finding a node from whatever was typed ---------------------------------


def test_a_node_can_be_found_by_name_or_by_slug(tmp_path):
    hold(tmp_path, "Angela Merkel", [])
    g = graph.build(tmp_path)

    assert graph.resolve("angela-merkel", g) == "angela-merkel"
    assert graph.resolve("Angela Merkel", g) == "angela-merkel"
    assert graph.resolve("angela merkel", g) == "angela-merkel"
    assert graph.resolve("Nobody", g) is None
