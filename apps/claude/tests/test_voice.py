"""What gets spoken: markdown and code are turned into words worth hearing,
and long replies are cut at a sentence end."""

import voice


def test_markdown_code_and_links_become_plain_speech():
    said = voice.clean_text(
        "## Done\n**Tests passed.** See [the log](http://x/y) and `pytest`.\n"
        "```py\nprint('no')\n```\n| a | b |\n|---|---|\n- one item"
    )
    assert said == "Done Tests passed. See the log and pytest. (code) one item"


def test_long_replies_stop_at_a_sentence_end():
    text = "This is a sentence. " * 60
    said = voice.clean_text(text, limit=100)
    assert len(said) <= 100 and said.endswith(".")


def test_bare_addresses_are_not_read_out():
    assert voice.clean_text("open https://example.com/a?b=c now") == "open a link now"
