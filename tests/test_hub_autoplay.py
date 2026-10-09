"""#257: the hub's background music was silent after a start.

WebKitGTK's default autoplay policy refuses play() on an element with sound
until the page has been clicked; the hub starts its music without a click.
forge.hub_webview() allows it. The sound itself is measured by
tests/browser/check_music_webkit.py.
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "shared"))

import forge  # noqa: E402


def test_the_hub_may_start_sound_without_a_click():
    view = forge.hub_webview()
    policy = view.get_website_policies().get_autoplay_policy()
    assert policy == forge.WebKit2.AutoplayPolicy.ALLOW
