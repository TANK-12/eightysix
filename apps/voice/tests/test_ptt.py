import pytest

from service import PTT


def run(m, *events):
    out = []
    for e in events:
        name, now = (e if isinstance(e, tuple) else (e, 0.0))[:2]
        out.append((m.event(name, now), m.state))
    return out


def test_hold_then_up_stops():
    m = PTT(hold_s=0.35)
    assert m.event("down", 0.0) == ["start"] and m.state == "listening"
    assert m.event("up", 1.0) == ["stop"] and m.state == "transcribing"


def test_short_press_keeps_listening_with_silence_gate():
    m = PTT(hold_s=0.35)
    m.event("down", 0.0)
    assert m.event("up", 0.1) == [] and m.state == "listening"
    assert m.use_silence
    assert m.event("down", 2.0) == ["stop"] and m.state == "transcribing"
    assert m.event("up", 2.1) == [] and m.state == "transcribing"


def test_held_does_not_use_silence():
    m = PTT()
    m.event("down", 0.0)
    assert not m.use_silence


def test_full_round_and_tap_while_speaking_hushes():
    m = PTT()
    assert m.event("tap") == ["start"] and m.use_silence
    m.event("ended")
    assert m.state == "transcribing"
    m.event("heard", text="hi")
    assert m.state == "thinking"
    m.event("replied", speak=True)
    assert m.state == "speaking"
    assert m.event("tap") == ["hush"] and m.state == "idle"


def test_down_while_speaking_hushes_and_mic_stays_closed():
    m = PTT()
    m.state = "speaking"
    assert m.event("down", 0.0) == ["hush"]
    assert m.state == "idle"


@pytest.mark.parametrize(
    "state", ["idle", "listening", "transcribing", "thinking", "speaking"]
)
def test_cancel_from_every_state(state):
    m = PTT()
    m.state = state
    assert m.event("cancel") == ["discard", "hush"] and m.state == "idle"


@pytest.mark.parametrize("state", ["transcribing", "thinking"])
@pytest.mark.parametrize("ev", ["down", "tap"])
def test_press_while_busy_cancels_the_round(state, ev):
    m = PTT()
    m.state = state
    assert m.event(ev, 5.0) == ["discard", "hush"] and m.state == "idle"
    assert m.event("tap") == ["start"] and m.state == "listening"


@pytest.mark.parametrize("state", ["transcribing", "thinking"])
def test_release_while_busy_is_ignored(state):
    m = PTT()
    m.state = state
    assert m.event("up", 5.0) == [] and m.state == state


def test_stale_worker_events_after_a_cancel_do_nothing():
    m = PTT()
    m.state = "thinking"
    m.event("tap")
    assert m.event("replied", speak=True) == [] and m.state == "idle"
    assert m.event("heard", text="x") == [] and m.state == "idle"


def test_empty_heard_goes_idle_and_no_speak_goes_idle():
    m = PTT()
    m.event("tap")
    m.event("tap")
    m.event("heard", text="")
    assert m.state == "idle"
    for ev in ("tap", "tap"):
        m.event(ev)
    m.event("heard", text="x")
    m.event("replied", speak=False)
    assert m.state == "idle"


def test_hush_only_leaves_speaking():
    m = PTT()
    m.state = "thinking"
    assert m.event("hush") == ["hush"] and m.state == "thinking"


def test_unknown_event():
    with pytest.raises(ValueError):
        PTT().event("jump")
