"""The deterministic core: identity of a URL, identity of a story, relevance,
and what counts as independent corroboration. No network, no model."""

import pytest

from research.canonical import canonical_url, registrable_domain, same_document
from research.dedupe import StoryClusterer, hamming, simhash
from research.scoring import SubjectProfile, score_document
from research.corroborate import (
    Claim,
    Evidence,
    grade,
    merge_claims,
    independent_sources,
)

# --- URL identity ----------------------------------------------------------


@pytest.mark.parametrize(
    "dirty,clean",
    [
        (
            "https://www.bbc.co.uk/news/uk-123?utm_source=twitter&utm_medium=social",
            "https://bbc.co.uk/news/uk-123",
        ),
        (
            "http://theguardian.com/politics/story/?fbclid=abc123",
            "https://theguardian.com/politics/story",
        ),
        ("https://www.reuters.com/world/piece/amp/", "https://reuters.com/world/piece"),
        (
            "https://m.economictimes.com/news/item",
            "https://economictimes.com/news/item",
        ),
        (
            "https://nytimes.com/2024/01/01/us/x.html?smid=tw-share&ref=home",
            "https://nytimes.com/2024/01/01/us/x.html",
        ),
        ("https://example.com:443/a/", "https://example.com/a"),
    ],
)
def test_canonical_url_strips_noise(dirty, clean):
    assert canonical_url(dirty) == clean


def test_canonical_url_keeps_meaningful_query():
    # An article id is the document; dropping it would merge different pages.
    assert (
        canonical_url("https://site.com/view?id=99&utm_source=x")
        == "https://site.com/view?id=99"
    )


def test_google_news_wrapper_unwrapped():
    wrapped = "https://news.google.com/rss/articles/CBMi?url=https%3A%2F%2Fbbc.co.uk%2Fnews%2Fx"
    assert canonical_url(wrapped) == "https://bbc.co.uk/news/x"


def test_same_document_across_formats():
    assert same_document(
        "https://www.bbc.co.uk/news/uk-123?utm_campaign=x",
        "http://bbc.co.uk/news/uk-123/",
    )


@pytest.mark.parametrize(
    "url,owner",
    [
        ("https://news.bbc.co.uk/story", "bbc.co.uk"),
        ("https://www.theguardian.com/x", "theguardian.com"),
        ("https://edition.cnn.com/2024/x", "cnn.com"),
        ("https://abc.net.au/news/x", "abc.net.au"),
        ("https://sec.gov/filing", "sec.gov"),
    ],
)
def test_registrable_domain(url, owner):
    assert registrable_domain(url) == owner


# --- Story identity --------------------------------------------------------

WIRE = (
    "BERLIN (Reuters) - Former German chancellor Angela Merkel defended her 2015 "
    "decision to admit hundreds of thousands of refugees, telling an audience in "
    "Berlin on Tuesday that she would take the same decision again. Merkel, who "
    "led Germany for 16 years, said the policy had been a humanitarian necessity."
)


def test_syndicated_reprints_collapse_to_one_cluster():
    """Forty outlets running one wire story is one story."""
    clusterer = StoryClusterer()
    for i in range(40):
        # Each outlet adds its own furniture around identical wire copy.
        clusterer.add(
            {
                "url": f"https://outlet{i}.com/world/merkel-refugees",
                "domain": f"outlet{i}.com",
                "title": "Merkel defends 2015 refugee decision",
                "text": f"{WIRE} Copyright {2020 + i % 3} Reuters. All rights reserved.",
            }
        )
    assert len(clusterer.clusters) == 1
    assert clusterer.summary()["duplicates_collapsed"] == 39


def test_genuinely_different_stories_stay_apart():
    clusterer = StoryClusterer()
    clusterer.add({"domain": "a.com", "title": "t", "text": WIRE})
    clusterer.add(
        {
            "domain": "b.com",
            "title": "t",
            "text": "LONDON - The Bank of England raised interest rates by a quarter point on "
            "Thursday, its fourteenth consecutive increase, as policymakers continued "
            "their fight against stubborn inflation across the British economy.",
        }
    )
    assert len(clusterer.clusters) == 2


def test_simhash_is_stable_and_close_for_edits():
    a = simhash(WIRE)
    b = simhash(WIRE + " Additional reporting by a correspondent in Munich.")
    assert a == simhash(WIRE)
    assert hamming(a, b) <= 6


# --- Relevance -------------------------------------------------------------

MERKEL = SubjectProfile(
    name="Angela Merkel",
    aliases=["Merkel"],
    context_terms=["chancellor", "germany", "cdu", "berlin"],
    birth_year=1954,
)


def test_on_topic_article_scores_high():
    r = score_document(
        {"title": "Merkel defends 2015 refugee decision", "text": WIRE},
        MERKEL,
        tier="major",
    )
    assert r.score >= 0.6, r.breakdown


def test_namesake_article_scores_low():
    """A different Merkel, with none of her distinguishing context."""
    r = score_document(
        {
            "title": "Local bakery owner Hans Merkel wins county pie contest",
            "text": "Hans Merkel, who runs a bakery in rural Ohio, took first "
            "place at the county fair on Saturday with a cherry pie.",
        },
        MERKEL,
        tier="unknown",
    )
    assert r.score < 0.35, r.breakdown


def test_passing_mention_scores_below_focused_article():
    focused = score_document(
        {"title": "Merkel defends 2015 refugee decision", "text": WIRE},
        MERKEL,
        tier="major",
    )
    passing = score_document(
        {
            "title": "European leaders gather for climate summit",
            "text": "Delegates from across the bloc met in Brussels. Among the "
            "guests were several former leaders, including Angela Merkel. "
            "The summit focused on emissions targets for the next decade "
            "and on financing for developing nations facing rising seas.",
        },
        MERKEL,
        tier="major",
    )
    assert passing.score < focused.score


def test_score_explains_itself():
    r = score_document(
        {"title": "Merkel in Berlin", "text": WIRE}, MERKEL, tier="major"
    )
    assert "chancellor" in r.breakdown["context_terms_found"]
    assert 0.0 <= r.breakdown["base"] <= 1.0


# --- Corroboration ---------------------------------------------------------


def _ev(
    sid,
    cluster,
    domain,
    tier="major",
    span="Merkel said she would decide the same way.",
):
    return Evidence(
        source_id=sid,
        cluster_id=cluster,
        domain=domain,
        tier=tier,
        relevance=0.8,
        span=span,
    )


def test_forty_reprints_are_one_independent_source():
    """The whole point: syndication must not manufacture confirmation."""
    ev = [_ev(f"s{i}", "c0001", f"outlet{i}.com") for i in range(40)]
    assert independent_sources(ev) == 1
    claim = grade(Claim(text="Merkel would take the same decision again", evidence=ev))
    assert claim.confidence == "reported"


def test_same_outlet_twice_is_one_voice():
    ev = [_ev("s1", "c1", "bbc.co.uk"), _ev("s2", "c2", "bbc.co.uk")]
    assert independent_sources(ev) == 1


def test_two_independent_outlets_plus_encyclopedic_is_verified():
    ev = [
        _ev("s1", "c1", "bbc.co.uk"),
        _ev("s2", "c2", "reuters.com"),
        _ev("s3", "c3", "wikipedia.org", tier="encyclopedic"),
    ]
    claim = grade(Claim(text="Merkel led Germany for 16 years", evidence=ev))
    assert claim.confidence == "verified"
    assert claim.independent == 3


def test_conflicting_sources_are_marked_disputed_not_resolved():
    ev = [
        _ev("s1", "c1", "bbc.co.uk", span="Merkel said she would decide the same way."),
        _ev(
            "s2",
            "c2",
            "reuters.com",
            span="Merkel said she would not decide the same way.",
        ),
    ]
    claim = grade(Claim(text="Merkel would repeat the decision", evidence=ev))
    assert claim.confidence == "disputed"
    assert claim.conflicts
    assert len(claim.evidence) == 2, "both sides must be kept"


def test_differing_figures_are_disputed():
    ev = [
        _ev("s1", "c1", "a.com", span="The policy admitted 890000 people in 2015."),
        _ev("s2", "c2", "b.com", span="The policy admitted 1200000 people in 2015."),
    ]
    claim = grade(Claim(text="number admitted in 2015", evidence=ev))
    assert claim.confidence == "disputed"


def test_claim_with_no_evidence_is_unsourced():
    assert grade(Claim(text="something the model just knows")).confidence == "unsourced"


def test_restatements_merge_into_one_claim():
    raw = [
        Claim(
            text="Merkel served as chancellor of Germany for sixteen years",
            evidence=[_ev("s1", "c1", "bbc.co.uk")],
        ),
        Claim(
            text="Merkel was Germany's chancellor for 16 years",
            evidence=[_ev("s2", "c2", "reuters.com")],
        ),
        Claim(
            text="Merkel studied physics in Leipzig",
            evidence=[_ev("s3", "c3", "wikipedia.org", tier="encyclopedic")],
        ),
    ]
    merged = merge_claims(raw)
    assert len(merged) == 2
    chancellor = [c for c in merged if "chancellor" in c.text.lower()][0]
    assert len(chancellor.evidence) == 2


def test_incidental_numbers_are_not_a_disagreement():
    """The false positive this rule was rewritten for: a year in one span and
    a duration in another are not sources contradicting each other."""
    ev = [
        _ev(
            "s1",
            "c1",
            "a.com",
            span="With Chancellor Angela Merkel departing in 2021 after a long career.",
        ),
        _ev(
            "s2",
            "c2",
            "b.com",
            span="In her 16 years as leader, Merkel saw many counterparts come and go.",
        ),
    ]
    claim = grade(Claim(text="Merkel served as chancellor for 16 years", evidence=ev))
    assert claim.confidence != "disputed", claim.conflicts


def test_different_figures_for_the_same_thing_are_still_disputed():
    ev = [
        _ev("s1", "c1", "a.com", span="The policy admitted 890,000 people in 2015."),
        _ev("s2", "c2", "b.com", span="The policy admitted 1,200,000 people in 2015."),
    ]
    claim = grade(Claim(text="number admitted", evidence=ev))
    assert claim.confidence == "disputed"
    assert "people" in claim.conflicts[0]


def test_same_figure_stated_twice_is_agreement():
    ev = [
        _ev("s1", "c1", "a.com", span="She served 16 years as chancellor."),
        _ev("s2", "c2", "b.com", span="Her 16 years in office reshaped the party."),
    ]
    claim = grade(Claim(text="sixteen years in office", evidence=ev))
    assert claim.confidence != "disputed"
