"""The IMF adapter, and the one distinction it exists to preserve.

No network: a stub fetcher returns the shape the live DataMapper API was
observed to return — including its quirk, where asking for one country answers
with every country in the world.

The rule these protect: **a projection is not a measurement.** This is the only
source in the library that reports the future, and storing an IMF staff
estimate as an observed figure would make the factual record less trustworthy
rather than more.
"""

from dataclasses import dataclass
from datetime import date

from research.scoring import SubjectProfile
from sources import imf
from sources.registry import Context


@dataclass
class Response:
    text: str


class StubFetcher:
    """The World Bank country list, then a DataMapper payload per indicator."""

    def __init__(self, series):
        self.series = series
        self.calls = []

    def get_json(self, url, api=True, **kw):
        self.calls.append(url)
        if "worldbank" in url or "/country" in url:
            return [
                {},
                [
                    {"id": "AUS", "name": "Australia", "region": {"id": "EAP"}},
                    {"id": "WLD", "name": "World", "region": {"id": "NA"}},
                ],
            ]
        indicator = url.rstrip("/").split("/")[-2]
        # The quirk: every country comes back whatever one was asked for.
        return {
            "values": {
                indicator: {
                    "AUS": self.series.get(indicator, {}),
                    "SDN": {"2024": 99.0},
                }
            }
        }

    def get(self, url, api=True, params=None, **kw):
        return None


def _ctx(series):
    return Context(
        fetcher=StubFetcher(series),
        phase="quick",
        entity_type="country",
        identity={"country": ["Australia"]},
    )


def _harvest(series):
    return imf.fetch(SubjectProfile(name="Australia"), _ctx(series))


def test_a_past_year_is_stored_as_a_measurement():
    past = str(date.today().year - 2)
    harvest = _harvest({"NGDP_RPCH": {past: 3.1}})
    rows = [t for t in harvest.timeline if t["indicator"] == "NGDP_RPCH"]
    assert len(rows) == 1
    assert rows[0]["kind"] == "indicator"
    assert rows[0]["confidence"] == "verified"
    assert "projection" not in rows[0]["title"]


def test_a_future_year_is_stored_as_a_projection():
    ahead = str(date.today().year + 3)
    harvest = _harvest({"NGDP_RPCH": {ahead: 2.4}})
    rows = [t for t in harvest.timeline if t["indicator"] == "NGDP_RPCH"]
    assert rows[0]["kind"] == "projection"
    assert rows[0]["confidence"] == "reported"
    assert "IMF projection" in rows[0]["title"]
    assert "not an observed figure" in rows[0]["detail"]


def test_the_current_year_is_a_projection_too():
    """The year is not over, so the figure has not been observed. The WEO
    publishes it as a staff estimate and it must be stored as one."""
    now = str(date.today().year)
    harvest = _harvest({"NGDP_RPCH": {now: 2.0}})
    assert harvest.timeline[0]["kind"] == "projection"


def test_only_the_country_asked_for_is_kept():
    """The API answers with every country in the world; SDN must not end up in
    Australia's dossier."""
    past = str(date.today().year - 1)
    harvest = _harvest({"NGDP_RPCH": {past: 3.1}})
    assert all(t["value"] != 99.0 for t in harvest.timeline)


def test_ancient_history_is_not_carried():
    harvest = _harvest({"NGDP_RPCH": {"1985": 4.0, str(date.today().year - 1): 3.0}})
    assert [t["date"] for t in harvest.timeline] == [str(date.today().year - 1)]


def test_the_summary_document_quotes_only_observed_figures():
    """The prose the model later reads must not present a forecast as a fact."""
    past, ahead = str(date.today().year - 1), str(date.today().year + 2)
    harvest = _harvest({"NGDP_RPCH": {past: 3.1, ahead: 9.9}})
    assert harvest.documents
    text = harvest.documents[0].text
    assert "3.1" in text
    assert "9.9" not in text
    assert "projections" in text.lower()


def test_a_subject_with_no_country_says_so_rather_than_guessing():
    ctx = Context(fetcher=StubFetcher({}), phase="quick", entity_type="person")
    harvest = imf.fetch(SubjectProfile(name="Nobody"), ctx)
    assert harvest.timeline == []
    assert harvest.notes


def test_it_is_registered_and_restricted_to_the_right_subjects():
    from sources import registry

    spec = registry.get("imf")
    assert spec is not None
    assert spec.tier == "primary"
    # An IMF outlook is meaningless for a person or a war.
    assert "country" in spec.entity_types
    assert "person" not in spec.entity_types
