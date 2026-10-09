import picker
import store

S = store.DEFAULTS
NOW = 1_000_000.0


def m(five, week=10):
    return {"five": five, "week": week}


def test_blocked_reasons_at_each_level():
    assert picker.blocked_reason(m(50), 0, NOW, S) == ""
    assert picker.blocked_reason(m(70), 0, NOW, S) == ""  # no launch for ages
    assert "next launch" in picker.blocked_reason(m(70), NOW - 60, NOW, S)
    assert picker.blocked_reason(m(70), NOW - 16 * 60, NOW, S) == ""
    assert "92" in picker.blocked_reason(m(92), 0, NOW, S)
    assert "95" in picker.blocked_reason(m(95), 0, NOW, S)
    assert "weekly" in picker.blocked_reason(m(10, 99), 0, NOW, S)
    assert picker.blocked_reason({"five": None}, 0, NOW, S) == "no usage reading"


def test_most_headroom_wins():
    acct, why = picker.pick_account({"a": m(60), "b": m(20)}, {}, NOW, S)
    assert (acct, why) == ("b", "most headroom")


def test_weekly_meter_counts_in_headroom():
    acct, _ = picker.pick_account({"a": m(10, 90), "b": m(30, 10)}, {}, NOW, S)
    assert acct == "b"


def test_warm_cache_preferred_under_an_hour():
    meters = {"a": m(60), "b": m(20)}
    acct, why = picker.pick_account(
        meters, {}, NOW, S, prefer="a", prefer_ended=NOW - 600
    )
    assert acct == "a" and "warm" in why
    acct, _ = picker.pick_account(
        meters, {}, NOW, S, prefer="a", prefer_ended=NOW - 7200
    )
    assert acct == "b"


def test_warm_account_skipped_when_over_limit():
    meters = {"a": m(95), "b": m(20)}
    acct, _ = picker.pick_account(meters, {}, NOW, S, prefer="a", prefer_ended=NOW)
    assert acct == "b"


def test_slow_zone_spacing_per_account():
    meters = {"a": m(75), "b": m(80)}
    acct, _ = picker.pick_account(meters, {"a": NOW - 60}, NOW, S)
    assert acct == "b"
    acct, why = picker.pick_account(meters, {"a": NOW - 60, "b": NOW - 60}, NOW, S)
    assert acct is None and "next launch" in why


def test_nothing_when_all_full():
    acct, why = picker.pick_account({"a": m(95), "b": m(99)}, {}, NOW, S)
    assert acct is None and "a:" in why and "b:" in why


def test_forced_account():
    meters = {"a": m(60), "b": m(20)}
    assert picker.pick_account(meters, {}, NOW, S, forced="a")[0] == "a"
    acct, why = picker.pick_account({"a": m(96)}, {}, NOW, S, forced="a")
    assert acct is None and "96" in why


def test_effort():
    assert picker.effort_for("important") == "max"
    assert picker.effort_for("normal") == "high"  # Emerson 2026-10-07
    assert picker.effort_for("important", "plan") == "medium"
    assert picker.effort_for("normal", "handoff") == "low"
    assert picker.effort_for("normal", "work", "high") == "high"


def test_hand_over_threshold():
    assert picker.over_hand_over(m(95), S)
    assert not picker.over_hand_over(m(94), S)
    assert picker.over_hand_over(m(10, 99), S)


def test_parked_after_two_fails():
    assert picker.should_park({"fails": 1}, S) == ""
    assert "2 times" in picker.should_park({"fails": "2"}, S)
    # no session cap (Emerson, 2026-10-08): a long task gets a review instead
    assert picker.should_park({"attempts": 13}, S) == ""
    assert picker.should_park({"attempts": 500}, S) == ""


def test_account_over_hand_over_line_takes_nothing_even_if_settings_odd():
    odd = {**S, "hand_over_at": 60, "no_new_at": 92}
    assert "65" in picker.blocked_reason(m(65), 0, NOW, odd)


def test_launches_on_one_account_are_spaced_even_with_room():
    # 2026-10-06: three queued tasks all started in the same second after a reset
    assert "next launch" in picker.blocked_reason(m(5), NOW - 60, NOW, S)
    assert picker.blocked_reason(m(5), NOW - S["launch_gap_minutes"] * 60, NOW, S) == ""
    acct, _ = picker.pick_account({"a": m(5), "b": m(30)}, {"a": NOW - 60}, NOW, S)
    assert acct == "b"


def test_context_cap_and_fresh_start():
    cap = S["hand_over_context_k"] * 1000
    assert not picker.over_context(cap - 1, S)
    assert picker.over_context(cap, S)
    assert picker.resume_cheap(S["resume_max_context_k"] * 1000 - 1, S)
    assert not picker.resume_cheap(S["resume_max_context_k"] * 1000, S)
    assert S["resume_max_context_k"] < S["hand_over_context_k"]


def test_hey_has_its_own_lines():
    """Emerson 2026-10-07: on hey no 15-minute spacing, new launches up to 95,
    hand over at 98; other accounts keep 70 / 92 / 95."""
    limits = {
        "account_limits": {"hey": {"slow_at": 101, "no_new_at": 95, "hand_over_at": 98}}
    }
    s = {**S, **limits}
    just = NOW - S["launch_gap_minutes"] * 60
    assert picker.blocked_reason(m(80), just, NOW, picker.limits(s, "hey")) == ""
    assert "next launch" in picker.blocked_reason(m(80), just, NOW, s)
    assert picker.blocked_reason(m(94), 0, NOW, picker.limits(s, "hey")) == ""
    assert "95" in picker.blocked_reason(m(95), 0, NOW, picker.limits(s, "hey"))
    acct, _ = picker.pick_account({"hey": m(93), "b": m(93)}, {}, NOW, s)
    assert acct == "hey"
    assert not picker.over_hand_over(m(97), s, "hey")
    assert picker.over_hand_over(m(98), s, "hey")
    assert picker.over_hand_over(m(95), s, "b")
    assert picker.over_hand_over(m(10, 99), s, "hey")  # the weekly line stays


def test_account_limits_setting_saves_as_a_dict():
    saved = store.save_settings({"account_limits": '{"hey": {"no_new_at": 90}}'})
    assert saved["account_limits"] == {"hey": {"no_new_at": 90}}


# ---- account fallback (Emerson, 2026-10-09: hey runs out -> default) ----------

FB = {**S, "account_fallback": {"hey": "default"}}


def test_hey_falls_back_to_default_by_default():
    assert S["account_fallback"] == {"hey": "default"}
    assert picker.fallbacks(S, "hey") == ["default"]
    assert picker.fallbacks(S, "default") == []


def test_pinned_task_on_a_full_account_goes_to_its_fallback():
    for hey in (m(100), m(98), m(10, 99), m(10, 100)):
        acct, why = picker.pick_account(
            {"hey": hey, "default": m(40)}, {}, NOW, FB, forced="hey"
        )
        assert acct == "default", hey
        assert "fallback" in why and "hey" in why


def test_fallback_needs_the_account_to_be_out_not_just_spaced():
    meters = {"hey": m(30), "default": m(10)}
    just = {"hey": NOW - 60}
    acct, why = picker.pick_account(meters, just, NOW, FB, forced="hey")
    assert acct is None and "next launch" in why  # 3 minutes, then hey
    # no reading counts as out: default has a real one, so nothing runs blind
    for hey in ({"five": None}, {"five": None, "week": 100}, None):
        meters = {"default": m(10), **({"hey": hey} if hey else {})}
        assert picker.pick_account(meters, {}, NOW, FB, forced="hey")[0] == "default"


def test_fallback_that_only_waits_for_spacing_is_waited_for():
    """Critic, task 128: the chain must not skip default for its 3 minutes."""
    s = {**S, "account_fallback": {"hey": "default", "default": "second"}}
    meters = {"hey": m(100), "default": m(30), "second": m(1)}
    acct, why = picker.pick_account(meters, {"default": NOW - 60}, NOW, s, forced="hey")
    assert acct is None and "fallback default" in why and "next launch" in why
    assert picker.pick_account(meters, {}, NOW, s, forced="hey")[0] == "default"


def test_fallback_that_is_full_too_waits_and_says_both():
    acct, why = picker.pick_account(
        {"hey": m(100), "default": m(96)}, {}, NOW, FB, forced="hey"
    )
    assert acct is None and "hey:" in why and "100" in why


def test_fallback_chain_and_loops():
    s = {**S, "account_fallback": {"hey": "default", "default": "second"}}
    assert picker.fallbacks(s, "hey") == ["default", "second"]
    meters = {"hey": m(100), "default": m(100), "second": m(5)}
    assert picker.pick_account(meters, {}, NOW, s, forced="hey")[0] == "second"
    looped = {**S, "account_fallback": {"a": ["b", "c"], "b": "a", "c": ["a", 7, None]}}
    assert picker.fallbacks(looped, "a") == ["b", "c"]
    assert picker.fallbacks({**S, "account_fallback": "junk"}, "a") == []
    assert picker.fallbacks({**S, "account_fallback": {"a": "a"}}, "a") == []


def test_account_without_fallback_still_waits():
    acct, why = picker.pick_account(
        {"hey": m(10), "b": m(100)}, {}, NOW, FB, forced="b"
    )
    assert acct is None and "100" in why


def test_moves_prefer_the_fallback_over_more_headroom():
    s = {**FB, "account_limits": {"hey": {"move_at": 80}}}
    meters = {"hey": m(85), "default": m(60), "second": m(10)}
    assert picker.move_to(meters, s, "hey", {}, NOW) == "default"
    acct, why = picker.pick_account(meters, {}, NOW, s, forced="hey")
    assert acct == "default" and "move line" in why
    # the fallback has no room: the most headroom as before
    meters["default"] = m(97)
    assert picker.move_to(meters, s, "hey", {}, NOW) == "second"


def test_task_last_on_a_full_account_prefers_its_fallback():
    meters = {"hey": m(100), "default": m(60), "second": m(10)}
    acct, why = picker.pick_account(
        meters, {}, NOW, FB, prefer="hey", prefer_ended=NOW - 60
    )
    assert acct == "default" and "fallback" in why
    # hey has room: the old rules (warm cache) hold
    meters["hey"] = m(50)
    acct, _ = picker.pick_account(
        meters, {}, NOW, FB, prefer="hey", prefer_ended=NOW - 60
    )
    assert acct == "hey"


def test_account_fallback_setting_saves_as_a_dict():
    saved = store.save_settings({"account_fallback": '{"default": "second"}'})
    assert saved["account_fallback"] == {"default": "second"}
