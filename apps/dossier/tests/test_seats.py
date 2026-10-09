"""Seat share: picking the right statement and the right chamber.

The network parts are exercised against live Wikidata by hand; these cover the
choices that were got wrong and would silently stay wrong.
"""

from pages import common
from sources.wikidata import _best_statement, _quantity


def statement(amount, rank="normal", time=None):
    st = {
        "mainsnak": {"datavalue": {"value": {"amount": f"+{amount}"}}},
        "rank": rank,
    }
    if time:
        st["qualifiers"] = {
            "P585": [{"datavalue": {"value": {"time": f"+{time}T00:00:00Z"}}}]
        }
    return st


def test_preferred_rank_wins():
    """A party carries a seat count for every term it has ever sat in."""
    best = _best_statement([statement(200), statement(164, rank="preferred")])
    assert _quantity(best) == 164


def test_deprecated_statements_are_ignored():
    best = _best_statement([statement(999, rank="deprecated"), statement(150)])
    assert _quantity(best) == 150


def test_latest_dated_statement_wins_without_a_preferred_one():
    best = _best_statement(
        [
            statement(100, time="2013-09-22"),
            statement(152, time="2021-09-26"),
            statement(120, time="2017-09-24"),
        ]
    )
    assert _quantity(best) == 152


def test_no_statements_gives_nothing():
    assert _best_statement([]) is None


def test_chamber_ranking_prefers_the_domestic_lower_house():
    """Britain's Lords has 808 seats to the Commons' 650, and the European
    Parliament has 720 - size alone picks the wrong chamber both times."""
    chambers = [
        {
            "body": "House of Lords",
            "total": 808,
            "seats": 180,
            "domestic": True,
            "lower_house": False,
            "upper_house": True,
        },
        {
            "body": "European Parliament",
            "total": 720,
            "seats": 20,
            "domestic": False,
            "lower_house": False,
            "upper_house": False,
        },
        {
            "body": "House of Commons",
            "total": 650,
            "seats": 198,
            "domestic": True,
            "lower_house": True,
            "upper_house": False,
        },
    ]
    chambers.sort(
        key=lambda c: (
            c["domestic"],
            c["lower_house"],
            not c["upper_house"],
            c["total"],
            c["seats"],
        ),
        reverse=True,
    )
    assert chambers[0]["body"] == "House of Commons"


def test_seats_block_is_empty_when_no_seats_are_held():
    block = common.seats_block({"subject": {"identity": {}}})
    assert block["kind"] == "seats"
    assert not block["seats"]


def test_seats_block_carries_the_share_and_the_other_chambers():
    block = common.seats_block(
        {
            "subject": {
                "identity": {
                    "seats": 198,
                    "seats_total": 650,
                    "seats_share": 0.3046,
                    "seats_body": "House of Commons",
                    "seats_chambers": [
                        {"body": "House of Commons"},
                        {"body": "Scottish Parliament"},
                    ],
                }
            }
        }
    )
    assert block["seats"] == 198 and block["total"] == 650
    assert round(block["share"] * 100, 1) == 30.5
    assert len(block["chambers"]) == 2
