"""ForgeDialog: in-page popups that never freeze the page (S17).

    apps/dossier/.venv/bin/python tests/browser/check_dialog.py

Loads forge_dialog_check.html (loading the
real shared/forge_chrome.js) in headless Chrome in real time, and prints its
PASS/FAIL lines. Exit status 1 on any FAIL or no result.
"""

from __future__ import annotations

import asyncio
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from cdp_driver import chrome_page, free_port, wait_http  # noqa: E402


async def run(site: Path, port: int) -> str:
    async with chrome_page(site, size="800,600") as page:
        await page.go(f"http://127.0.0.1:{port}/forge_dialog_check.html")
        await page.wait("document.getElementById('results')", 40)
        text = await page.js(
            "(document.getElementById('results') || {}).textContent || ''"
        )
        await page.screenshot(Path.home() / ".cache" / "forge-dialog.png")
        return text


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="forge-dialog-") as tmp:
        site = Path(tmp)
        for name in ("forge_dialog_check.html",):
            shutil.copy(HERE / name, site / name)
        (site / "shared").symlink_to(HERE.parent.parent / "shared")
        port = free_port()
        server = subprocess.Popen(
            [sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"],
            cwd=site,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            wait_http(f"http://127.0.0.1:{port}/forge_dialog_check.html")
            text = asyncio.run(run(site, port))
        finally:
            server.terminate()
            server.wait(timeout=5)
    lines = [ln for ln in text.splitlines() if ln.startswith(("PASS", "FAIL"))]
    print("\n".join(lines) or "FAIL :: the dialog page reported nothing")
    return 0 if lines and all(ln.startswith("PASS") for ln in lines) else 1


if __name__ == "__main__":
    sys.exit(main())
