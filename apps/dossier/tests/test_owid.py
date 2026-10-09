"""Our World in Data, and the Society page that reads it.

No network: a stub fetcher returns the CSV shapes the live endpoint was
observed to return - including the awkward one, where a map chart ignores the
country filter and answers with every country in the world.
"""

from dataclasses import dataclass

import pytest

from entities import registry as entities
from pages import registry as pages
from research.scoring import SubjectProfile
from sources import countrycodes, owid
from sources.registry import Context


@dataclass
class Response:
    text: str


class StubFetcher:
    """Answers the two shapes of OWID chart, and the World Bank country list."""

    def __init__(self):
        self.calls = []

    def get_json(self, url, api=True, **kw):
        return [
            {},
            [
                {"id": "DEU", "name": "Germany", "region": {"id": "ECS"}},
                {"id": "FRA", "name": "France", "region": {"id": "ECS"}},
                {"id": "WLD", "name": "World", "region": {"id": "NA"}},
            ],
        ]

    def get(self, url, api=True, params=None, **kw):
        params = params or {}
        self.calls.append((url, params.get("country", "")))
        if "life-expectancy" in url:
            # A line chart: the country filter works and history comes back
            # for whichever country was asked for.
            code = (params.get("country") or "~DEU").lstrip("~")
            return Response(
                "entity,code,year,life_expectancy_0\n"
                f"X,{code},2019,81.3\n"
                f"X,{code},2020,80.9\n"
                f"X,{code},2021,80.8\n"
            )
        if "political-regime" in url:
            # A map chart: the filter is ignored, every country comes back.
            return Response(
                "entity,code,year,regime_row_owid\n"
                "Germany,DEU,2025,3\n"
                "France,FRA,2025,3\n"
                "Afghanistan,AFG,2025,0\n"
            )
        return Response('{"status":404,"error":"Not found"}')


def context(fetcher, entity_type="country", identity=None, phase="quick"):
    return Context(
        fetcher=fetcher,
        phase=phase,
        entity_type=entity_type,
        identity=identity if identity is not None else {"label": "Germany"},
    )


@pytest.fixture(autouse=True)
def _clear_caches():
    """These caches are process-wide by design; tests must not inherit them."""
    countrycodes._codes = {}
    owid._snapshots = {}
    yield
    countrycodes._codes = {}
    owid._snapshots = {}


def subject(name="Germany"):
    return SubjectProfile(name=name)


# --- resolving the country --------------------------------------------------


def test_a_country_resolves_to_its_iso3_code():
    assert countrycodes.iso3(StubFetcher(), "Germany") == "DEU"


def test_aggregates_are_not_countries():
    """ "World" is a row in the same list and must never match."""
    assert countrycodes.iso3(StubFetcher(), "World") == ""


def test_a_wikidata_label_that_differs_is_fixed_up():
    assert "United States of America" in countrycodes.NAME_FIXES


def test_a_person_is_looked_up_under_their_country():
    ctx = context(StubFetcher(), "person", {"citizenship": ["Germany"]})
    assert countrycodes.country_for(subject("Angela Merkel"), ctx) == "Germany"


def test_a_subject_with_no_country_is_skipped_not_guessed():
    ctx = context(StubFetcher(), "person", {})
    harvest = owid.fetch(subject("Someone"), ctx)
    assert harvest.timeline == [] and harvest.notes


# --- reading the two chart shapes -------------------------------------------


def test_a_line_chart_is_filtered_to_the_country():
    fetcher = StubFetcher()
    harvest = owid.fetch(subject(), context(fetcher))
    life = [e for e in harvest.timeline if e["indicator"] == "life_expectancy"]
    assert [e["date"] for e in life] == ["2019", "2020", "2021"]
    assert life[0]["title"] == "Life expectancy: 81.30 yrs"


def test_a_map_chart_is_read_from_the_whole_world_table():
    harvest = owid.fetch(subject(), context(StubFetcher()))
    regime = [e for e in harvest.timeline if e["indicator"] == "democracy"]
    assert len(regime) == 1 and regime[0]["date"] == "2025"
    # The number means nothing to a reader; the word does.
    assert regime[0]["title"] == "Political regime: liberal democracy"


def test_a_map_chart_is_fetched_once_for_the_whole_process():
    """Fetching it per subject would download the world a thousand times."""
    fetcher = StubFetcher()
    owid.fetch(subject(), context(fetcher))
    owid.fetch(subject("France"), context(fetcher, identity={"label": "France"}))
    regime_calls = [c for c in fetcher.calls if "political-regime" in c[0]]
    assert len(regime_calls) == 1


def test_a_failed_snapshot_is_not_cached_as_empty():
    """Otherwise one transient failure would blank that indicator for the run."""
    owid._snapshots = {}
    assert owid._snapshot(StubFetcher(), "hdi") == {}
    assert "hdi" not in owid._snapshots


def test_an_error_page_is_never_parsed_as_a_table():
    harvest = owid.fetch(subject(), context(StubFetcher()))
    assert all(
        e["indicator"] in ("life_expectancy", "democracy") for e in harvest.timeline
    )


def test_a_deep_dive_keeps_more_history_than_a_quick_pass():
    quick = owid.fetch(subject(), context(StubFetcher(), phase="quick"))
    deep = owid.fetch(subject(), context(StubFetcher(), phase="deep"))
    assert len(deep.timeline) >= len(quick.timeline)


# --- what it stores ---------------------------------------------------------


def test_every_figure_is_dated_cited_and_marked_as_published():
    harvest = owid.fetch(subject(), context(StubFetcher()))
    assert harvest.timeline
    for entry in harvest.timeline:
        assert entry["date"] and entry["url"].startswith("https://ourworldindata.org")
        assert entry["source_id"] == "owid"
        assert entry["confidence"] == "verified"
        assert entry["kind"] == "indicator"


def test_a_summary_document_is_offered_for_scoring():
    harvest = owid.fetch(subject(), context(StubFetcher()))
    assert len(harvest.documents) == 1
    assert harvest.documents[0].tier == "primary"
    assert "Life expectancy" in harvest.documents[0].text


# --- the page that shows them -----------------------------------------------


def test_the_society_page_shows_owid_and_the_economy_page_is_untouched():
    stored = {
        "timeline": [
            {"kind": "indicator", "source_id": "owid", "date": "2021", "title": "a"},
            {
                "kind": "indicator",
                "source_id": "worldbank",
                "date": "2021",
                "title": "b",
            },
        ],
        "claims": [],
    }
    society = pages.build_page("society", stored)["blocks"][0]
    assert [e["title"] for e in society["events"]] == ["a"]
    # The Economy page keeps showing everything it showed before, and now also
    # picks up the new source. Adding a page must never narrow an old one.
    economy = pages.build_page("economy", stored)["blocks"][0]
    assert {e["title"] for e in economy["events"]} == {"a", "b"}


def test_the_society_page_is_a_tab_on_the_types_that_have_indicators():
    for name in ("country", "political_system"):
        assert "society" in entities.get(name).pages
