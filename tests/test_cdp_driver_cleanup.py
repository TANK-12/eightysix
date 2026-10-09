"""A UI check must not leave its headless Chrome running (2026-09-27: about
300 leaked test browsers held the CPU at 100%). Starts a real Chrome.
Run: apps/claude/.venv/bin/python -m pytest -q tests/test_cdp_driver_cleanup.py"""

import asyncio
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import cdp_driver  # noqa: E402


def test_no_browser_is_left_after_a_check():
    sandbox = Path(tempfile.mkdtemp(prefix="cdp-clean-"))

    async def run():
        async with cdp_driver.chrome_page(sandbox) as page:
            assert await page.js("1 + 1") == 2
            assert cdp_driver.browsers_using(sandbox / "chrome-profile")

    asyncio.run(run())
    assert cdp_driver.browsers_using(sandbox / "chrome-profile") == []
