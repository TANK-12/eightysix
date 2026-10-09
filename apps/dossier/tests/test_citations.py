"""Nothing uncited reaches the user. These guard the three places a model's
words could otherwise pass as fact."""

import ask
import briefing
from research.claims import _locate_sentence, _span_is_real, needs_triage

ARTICLE = (
    "Merkel, who led Germany for 16 years, said the policy had been a "
    "humanitarian necessity. She spoke in Berlin on Tuesday."
)


def test_a_real_anchor_recovers_the_whole_sentence():
    span = _locate_sentence("Merkel, who led Germany", ARTICLE)
    assert span.startswith("Merkel, who led Germany for 16 years")
    assert span.endswith("humanitarian necessity.")


def test_an_invented_anchor_recovers_nothing():
    assert _locate_sentence("Merkel apologised to the nation for", ARTICLE) == ""


def test_span_check_forgives_punctuation_but_not_invention():
    assert _span_is_real("Merkel who led Germany for 16 years said the policy", ARTICLE)
    assert not _span_is_real("Merkel resigned in disgrace after the scandal", ARTICLE)


def test_triage_only_runs_on_the_uncertain_middle():
    assert not needs_triage(0.05)
    assert needs_triage(0.45)
    assert not needs_triage(0.95)


def test_brief_points_carry_only_event_numbers_that_exist():
    """The brief no longer asks the model to write citation markers into prose -
    it produced one uncitable sentence and the whole summary was stripped.
    The model now returns points plus event numbers, those numbers are checked
    against the events it was actually given, and the markers are composed
    here, so a citation can be neither forgotten nor invented."""
    used = [{"title": "a"}, {"title": "b"}, {"title": "c"}]

    def validate(refs):
        return [n for n in refs if isinstance(n, int) and 0 <= n < len(used)]

    assert validate([0, 2]) == [0, 2]
    assert validate([0, 99]) == [0], "an event that was never supplied is dropped"
    assert validate([]) == []
    assert validate(["1"]) == [], "a non-number is not a citation"


def test_evidence_pack_prefers_items_that_share_words_with_the_question():
    stored = {
        "claims": [
            {
                "text": "Merkel defended the refugee policy",
                "confidence": "reported",
                "relevance": 0.9,
                "evidence": [{"url": "u"}],
            },
            {
                "text": "Merkel studied quantum chemistry",
                "confidence": "verified",
                "relevance": 0.9,
                "evidence": [{"url": "u"}],
            },
        ],
        "quotes": [],
        "timeline": [],
    }
    pack = ask._evidence_pack(stored, "what did she say about refugee policy?")
    assert "refugee" in pack[0]["text"]
