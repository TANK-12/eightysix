"""Tiers, and the one that never asks a model.

The rule these protect: an answer must always say which tier produced it, and
the rules tier must never reach for Jan. A "rules" answer that quietly called a
model would be the worst outcome here — it would look cheap and deterministic
and be neither.
"""

import pytest

import tiers
import world


class StubWorld:
    """A world with known numbers, so a solver's arithmetic can be checked."""

    def __init__(self, findings=None, subjects=None, facts=None):
        self._findings = findings or []
        self._subjects = subjects or []
        self._facts = facts or {}

    def findings(self, limit=40):
        return self._findings[:limit]

    def coverage(self):
        return {
            "subjects": 1212,
            "watched": 3,
            "sources": 2,
            "points": 140,
            "dossier_available": True,
        }

    def find_subject(self, text):
        # The real rule, not an approximation of it: a stub that matched only
        # full names is why a surname test passed while the app refused.
        return world.match_subject(self._subjects, text)

    def subject_summary(self, slug, name):
        return {"text": f"{name}: 5 sources, 2 findings", "evidence": [{"slug": slug}]}

    def subject_facts(self, slug):
        return self._facts.get(slug, {})

    def ranked(self, limit=12, entity_types=()):
        rows = [
            r
            for r in self._subjects
            if not entity_types or r.get("entity_type") in entity_types
        ]
        rows.sort(
            key=lambda r: r.get("sources", 0) + r.get("timeline", 0), reverse=True
        )
        return rows[:limit]


class ExplodingLLM:
    """Any call to this fails the test - the rules tier must not reach a model."""

    def chat(self, *a, **kw):
        raise AssertionError("the rules tier called a model")


# --- the tier table ---------------------------------------------------------


def test_rules_is_a_real_tier_that_uses_no_model():
    assert tiers.RULES in tiers.ALL_TIERS
    assert tiers.TIERS[tiers.RULES].uses_model is False
    assert all(tiers.TIERS[t].uses_model for t in tiers.MODEL_TIERS)


def test_only_the_think_tier_thinks():
    """Dossier forces thinking off everywhere; here exactly one tier turns it on."""
    import llm

    assert llm.TIER_THINKS["think"] is True
    assert llm.TIER_THINKS["chat"] is False
    assert llm.TIER_THINKS["analyse"] is False


def test_the_think_tier_prefers_a_mixture_of_experts_model():
    """A dense model of the same size cannot afford a long chain of thought on
    a CPU, which is the whole reason this tier exists."""
    import llm

    assert "A3B" in llm.TIER_PREFERENCE["think"][0]


def test_describe_lists_every_tier_for_the_picker():
    described = {d["name"] for d in tiers.describe()}
    assert described == set(tiers.ALL_TIERS)
    rules = [d for d in tiers.describe() if d["name"] == tiers.RULES][0]
    assert rules["solvers"], "the rules tier should advertise what it can settle"


# --- the rules tier never touches a model -----------------------------------


def test_rules_answers_what_is_moving_without_a_model(monkeypatch):
    monkeypatch.setattr(tiers, "llm", ExplodingLLM())
    world = StubWorld(
        findings=[
            {
                "headline": "NATO: pageviews up sharply",
                "detail": "9000 against 400",
                "weight": 0.9,
            },
        ]
    )
    answer = tiers.answer("what is moving right now?", tier="rules", world=world)
    assert answer.used_model is False and answer.tier == "rules"
    assert "NATO" in answer.text
    assert answer.evidence


def test_rules_counts_the_library_without_a_model(monkeypatch):
    monkeypatch.setattr(tiers, "llm", ExplodingLLM())
    answer = tiers.answer(
        "how many subjects do you have?", tier="rules", world=StubWorld()
    )
    assert answer.used_model is False
    assert "1212" in answer.text


def test_rules_says_so_plainly_when_it_cannot_help(monkeypatch):
    """It must refuse rather than quietly escalate to a model."""
    monkeypatch.setattr(tiers, "llm", ExplodingLLM())
    answer = tiers.answer(
        "should I move to another country?", tier="rules", world=StubWorld()
    )
    assert answer.used_model is False
    assert "rules tier" in answer.text.lower()


def test_rules_reports_honestly_when_nothing_is_moving(monkeypatch):
    monkeypatch.setattr(tiers, "llm", ExplodingLLM())
    answer = tiers.answer("what changed?", tier="rules", world=StubWorld(findings=[]))
    assert "Nothing has broken out" in answer.text


# --- preferring rules over a model ------------------------------------------


def test_prefer_rules_lets_a_solver_answer_a_model_tier_question(monkeypatch):
    """The cheapest correct answer should win - but it must say it was rules."""
    monkeypatch.setattr(tiers, "llm", ExplodingLLM())
    world = StubWorld(findings=[{"headline": "X up", "detail": "d", "weight": 0.5}])
    answer = tiers.answer(
        "what is moving?", tier="think", world=world, prefer_rules=True
    )
    assert answer.tier == "rules" and answer.used_model is False


def test_prefer_rules_off_sends_the_same_question_to_the_model(monkeypatch):
    seen = {}

    class FakeLLM:
        JanUnavailable = RuntimeError

        def chat(self, tier, messages, **kw):
            seen["tier"] = tier
            return {
                "text": "a model answer",
                "reasoning": "thinking",
                "model": "m",
                "seconds": 1.0,
            }

    monkeypatch.setattr(tiers, "llm", FakeLLM())
    answer = tiers.answer(
        "what is moving?", tier="think", world=StubWorld(), prefer_rules=False
    )
    assert seen["tier"] == "think"
    assert answer.used_model is True and answer.tier == "think"
    assert answer.reasoning == "thinking"


# --- degrading honestly ------------------------------------------------------


def test_a_model_tier_with_jan_off_says_so_rather_than_guessing(monkeypatch):
    class DeadLLM:
        class JanUnavailable(RuntimeError):
            pass

        class NotEnoughMemory(RuntimeError):
            pass

        def chat(self, *a, **kw):
            raise self.JanUnavailable("Jan unreachable")

    dead = DeadLLM()
    monkeypatch.setattr(tiers, "llm", dead)
    answer = tiers.answer(
        "should I be worried?", tier="analyse", world=StubWorld(), prefer_rules=False
    )
    assert answer.used_model is False
    assert "rules tier still works" in answer.text


def test_an_empty_question_is_not_sent_anywhere(monkeypatch):
    monkeypatch.setattr(tiers, "llm", ExplodingLLM())
    assert tiers.answer("   ", tier="think", world=StubWorld()).used_model is False


# --- subject matching --------------------------------------------------------


def test_the_longest_matching_name_wins():
    """'Donald Trump' must beat 'Donald', or questions land on the wrong subject."""
    world = StubWorld(
        subjects=[
            {"slug": "donald", "name": "Donald"},
            {"slug": "donald-trump", "name": "Donald Trump"},
        ]
    )
    hit = world.find_subject("tell me about Donald Trump")
    assert hit is not None and hit["slug"] == "donald-trump"


def test_an_unknown_subject_is_admitted_not_invented(monkeypatch):
    monkeypatch.setattr(tiers, "llm", ExplodingLLM())
    answer = tiers.answer(
        "tell me about Someone Unheard Of", tier="rules", world=StubWorld(subjects=[])
    )
    assert answer.used_model is False
    assert "No subject" in answer.text


# --- the no-swap safeguard ---------------------------------------------------


def test_thinking_is_refused_when_memory_is_short(monkeypatch):
    """There is no swap on this machine: running out locks it up rather than
    degrading, so a long thinking call must refuse rather than risk it."""
    import llm

    monkeypatch.setattr(llm, "available_mb", lambda: 800)
    monkeypatch.setattr(llm, "resolve", lambda tier: "big-model")
    with pytest.raises(llm.NotEnoughMemory):
        llm.chat("think", [{"role": "user", "content": "hello"}])


def test_a_short_call_is_allowed_when_memory_is_short(monkeypatch):
    """Only the thinking tier is gated - the small models are not the risk."""
    import llm

    calls = {}
    monkeypatch.setattr(llm, "available_mb", lambda: 800)
    monkeypatch.setattr(llm, "resolve", lambda tier: "small-model")

    class Response:
        status_code = 200

        def json(self):
            calls["made"] = True
            return {"choices": [{"message": {"content": "hi"}}]}

    class Client:
        def __init__(self, *a, **kw):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, *a, **kw):
            return Response()

    monkeypatch.setattr(llm.httpx, "Client", Client)
    assert llm.chat("chat", [{"role": "user", "content": "hi"}])["text"] == "hi"
    assert calls["made"]


def test_the_refusal_reaches_the_user_as_an_answer(monkeypatch):
    """It must come back as a plain answer naming the rules tier, not a 500."""

    class TightLLM:
        class JanUnavailable(RuntimeError):
            pass

        class NotEnoughMemory(RuntimeError):
            pass

        def chat(self, *a, **kw):
            raise self.NotEnoughMemory("Only 800 MB available; use the rules tier.")

    monkeypatch.setattr(tiers, "llm", TightLLM())
    answer = tiers.answer(
        "think hard about this", tier="think", world=StubWorld(), prefer_rules=False
    )
    assert answer.used_model is False
    assert "rules tier" in answer.text


# --- the rules tier answering more than it used to --------------------------
#
# Every test below started life as a question the user typed and got turned
# away from. The tier was keyword-triggered, so it refused anything phrased in
# a way nobody had listed, while the answer sat in the library.


def _library():
    return [
        {
            "slug": "australia",
            "name": "Australia",
            "entity_type": "country",
            "description": "country in Oceania",
            "sources": 13,
            "timeline": 44,
        },
        {
            "slug": "donald-trump",
            "name": "Donald Trump",
            "entity_type": "person",
            "description": "president of the United States",
            "sources": 40,
            "timeline": 120,
        },
        {
            "slug": "trump-organization",
            "name": "Trump Organization",
            "entity_type": "company",
            "description": "American company",
            "sources": 2,
            "timeline": 1,
        },
    ]


def _facts():
    return {
        "australia": {
            "Population": "27.6 million",
            "Currency": ["Australian dollar", "pound sterling"],
            "Head of government": ["Tony Abbott", "Kevin Rudd"],
            "Continent": ["Oceania"],
        }
    }


def _world():
    return StubWorld(subjects=_library(), facts=_facts())


def test_rules_answers_a_stored_fact():
    """'population of australia' was refused; the figure was in the library."""
    answer = tiers.answer("population of australia", tier=tiers.RULES, world=_world())
    assert answer.tier == tiers.RULES
    assert not answer.used_model
    assert "27.6 million" in answer.text
    assert "Australia" in answer.text


def test_a_stored_fact_says_it_is_stored_not_computed():
    answer = tiers.answer("population of australia", tier=tiers.RULES, world=_world())
    assert "Wikidata" in answer.text


def test_a_multi_valued_fact_does_not_pretend_to_be_current():
    """Wikidata keeps every head of government a country has ever had."""
    answer = tiers.answer(
        "head of government of australia", tier=tiers.RULES, world=_world()
    )
    assert "Tony Abbott" in answer.text
    assert "not only the current one" in answer.text


def test_a_bare_name_is_a_question():
    """'trump' is how people actually ask. It used to be refused outright."""
    answer = tiers.answer("trump", tier=tiers.RULES, world=_world())
    assert answer.tier == tiers.RULES
    assert "Donald Trump" in answer.text


def test_a_surname_reaches_the_subject_most_is_held_about():
    """Both 'Donald Trump' and 'Trump Organization' match the word; the one
    with a real dossier behind it should win."""
    stub = _world()
    hit = stub.find_subject("trump")
    assert hit is not None and hit["name"] == "Donald Trump"
    answer = tiers.answer("trump", tier=tiers.RULES, world=stub)
    assert "Trump Organization" not in answer.text


def test_rules_ranks_the_library():
    """'who is important' matched the subject solver and then failed to find a
    subject called 'important'."""
    answer = tiers.answer("who is important", tier=tiers.RULES, world=_world())
    assert answer.tier == tiers.RULES
    assert "Donald Trump" in answer.text
    assert "matches that name closely enough" not in answer.text


def test_a_ranking_says_what_it_is_ranking_by():
    answer = tiers.answer("who is important", tier=tiers.RULES, world=_world())
    assert "coverage, not of merit" in answer.text


def test_a_ranking_respects_the_kind_asked_for():
    answer = tiers.answer("the biggest countries", tier=tiers.RULES, world=_world())
    assert "Australia" in answer.text
    assert "Donald Trump" not in answer.text
    assert "countries" in answer.text


def test_the_refusal_now_teaches_what_to_type():
    """A dead end that does not say what would have worked is a bad refusal."""
    answer = tiers.answer(
        "should I move to another country?", tier=tiers.RULES, world=StubWorld()
    )
    assert answer.tier == tiers.RULES
    assert "population of Australia" in answer.text
    assert "what changed" in answer.text


def test_widening_the_facts_needs_no_change_here():
    """The fact solver matches against the keys a subject actually has, so a
    property Dossier starts harvesting is answerable with nothing edited in
    this file."""
    world = StubWorld(
        subjects=_library(),
        facts={"australia": {"Gross domestic product": "1.7 trillion"}},
    )
    answer = tiers.answer(
        "gross domestic product of australia", tier=tiers.RULES, world=world
    )
    assert "1.7 trillion" in answer.text


def test_one_incidental_word_does_not_pull_in_a_subject():
    """A solver that grabs the wrong question is worse than one that grabs
    none. 'What is the meaning of life' matched a company called Orange Life
    Insurance on the word 'life'."""
    stub = StubWorld(
        subjects=_library()
        + [
            {
                "slug": "orange-life-insurance",
                "name": "Orange Life Insurance",
                "entity_type": "company",
                "sources": 1,
                "timeline": 0,
            }
        ]
    )
    assert stub.find_subject("what is the meaning of life") is None
    answer = tiers.answer("what is the meaning of life", tier=tiers.RULES, world=stub)
    assert "Orange Life" not in answer.text
    assert "could not settle" in answer.text
