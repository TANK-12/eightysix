import prompts


def test_work_prompt_carries_the_critic_rule():
    """Emerson 2026-10-07 (standing): deep coding, game and program tasks get
    a critic subagent before they are called done."""
    text = prompts.work(
        {"id": 7, "title": "x", "path": "/tmp/t.md"}, "the terminal", "/tmp"
    )
    assert "critic subagent" in text and "model opus" in text
    assert "findings" in text and "plan before you build" in text
