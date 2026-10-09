"""Arcs drawn between countries on the world map.

An arc asserts a tie between two countries, so every one of these builds real
subject directories and checks the arc came from a stored relation rather than
from anything inferred.
"""

import dossier
import store
from research import arcs


def hold(tmp_path, name, entity_type, relations=()):
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


def countries(tmp_path, *names):
    for name in names:
        hold(tmp_path, name, "country")


# --- what becomes an arc ----------------------------------------------------


def test_a_conflict_joins_each_participant_to_where_it_was_fought(tmp_path):
    countries(tmp_path, "Finland", "Soviet Union", "Germany")
    hold(
        tmp_path,
        "Continuation War",
        "conflict",
        [
            ("participant", "Soviet Union"),
            ("participant", "Germany"),
            ("located in", "Finland"),
        ],
    )
    drawn = arcs.build(tmp_path)
    pairs = {tuple(sorted((a["a"], a["b"]))) for a in drawn}
    assert ("Finland", "Soviet Union") in pairs
    assert ("Finland", "Germany") in pairs
    # Two participants are NOT joined to each other: Wikidata's participant
    # list records no sides, so an arc between them would invent a hostility.
    assert ("Germany", "Soviet Union") not in pairs


def test_a_conflict_with_no_recorded_place_draws_nothing(tmp_path):
    countries(tmp_path, "Finland", "Soviet Union")
    hold(
        tmp_path,
        "Some War",
        "conflict",
        [("participant", "Soviet Union"), ("participant", "Finland")],
    )
    assert arcs.build(tmp_path) == []


def test_bloc_membership_joins_members_to_each_other(tmp_path):
    countries(tmp_path, "France", "Germany", "Italy")
    hold(
        tmp_path,
        "European Union",
        "alliance",
        [("has member", "France"), ("has member", "Germany"), ("has member", "Italy")],
    )
    drawn = arcs.build(tmp_path)
    pairs = {tuple(sorted((a["a"], a["b"]))) for a in drawn}
    assert pairs == {("France", "Germany"), ("France", "Italy"), ("Germany", "Italy")}
    assert all(a["kind"] == "alliance" for a in drawn)


def test_a_target_that_is_not_a_country_is_ignored(tmp_path):
    """Relation targets are bare names. Only a dossier saying "country" makes
    one a country, so an ideology never becomes a point on the map."""
    countries(tmp_path, "Finland")
    hold(
        tmp_path,
        "A War",
        "conflict",
        [("participant", "social democracy"), ("located in", "Finland")],
    )
    assert arcs.build(tmp_path) == []


# --- merging and provenance -------------------------------------------------


def test_the_same_pair_from_two_subjects_is_one_thicker_arc(tmp_path):
    countries(tmp_path, "Israel", "Lebanon")
    hold(
        tmp_path,
        "1982 Lebanon War",
        "conflict",
        [("participant", "Israel"), ("located in", "Lebanon")],
    )
    hold(
        tmp_path,
        "2006 Lebanon War",
        "conflict",
        [("participant", "Israel"), ("located in", "Lebanon")],
    )
    drawn = arcs.build(tmp_path)
    assert len(drawn) == 1
    assert drawn[0]["weight"] == 2
    assert {v["name"] for v in drawn[0]["via"]} == {
        "1982 Lebanon War",
        "2006 Lebanon War",
    }


def test_every_arc_names_the_dossier_it_came_from(tmp_path):
    """An arc is a claim about the world; it has to be checkable."""
    countries(tmp_path, "Finland", "Soviet Union")
    hold(
        tmp_path,
        "Winter War",
        "conflict",
        [("participant", "Soviet Union"), ("located in", "Finland")],
    )
    drawn = arcs.build(tmp_path)
    assert drawn and all(a["via"] and a["via"][0]["slug"] for a in drawn)


def test_one_subject_cannot_bury_the_map(tmp_path):
    """A conflict naming dozens of participants is capped rather than drawn."""
    names = [f"Country {i}" for i in range(20)]
    countries(tmp_path, *names)
    hold(
        tmp_path,
        "A Big War",
        "conflict",
        [("participant", n) for n in names[1:]] + [("located in", names[0])],
    )
    assert len(arcs.build(tmp_path)) <= arcs.MAX_PARTIES


def test_kinds_are_discovered_from_the_table(tmp_path):
    """The frontend filter is built from this, so it must stay declarative."""
    names = {k["name"] for k in arcs.kinds()}
    assert names == set(arcs.ARC_KINDS)
    assert all(k["label"] and k["blurb"] for k in arcs.kinds())
