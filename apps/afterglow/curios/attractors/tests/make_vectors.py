"""Rebuild vectors.json, the fixed cases both test suites check.

    cd ~/Forge/apps/afterglow && .venv/bin/python curios/attractors/tests/make_vectors.py

The Python side writes the numbers; test_attractors.py checks Python still
gives them and attractors.test.mjs checks the JS gives the same, so a drift
on either side fails a test. Only rebuild after a deliberate change to the
map, the hunt or the measurements.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
APP = HERE.parents[2]
sys.path.insert(0, str(APP))

import registry  # noqa: E402


def main() -> None:
    m = registry.load_server("attractors")
    named = {
        "FIRCDERRPVLD": "Sprott's example in the book, chaotic",
        "MMMMMMMMMMMM": "all zero, lands on the origin at once",
        "YYYYYYYYYYYY": "everything 1.2, flies off",
    }
    sweep_codes = []
    r = m.mulberry32(2026)
    while len(sweep_codes) < 400:
        sweep_codes.append(m.random_code(r))
    sweep = []
    for code in sweep_codes:
        f = m.try_code(code)
        sweep.append(
            {
                "code": code,
                "status": f["result"]["status"],
                "lyapunov": f["result"]["lyapunov"],
                "dimension": f["dimension"],
                "accepted": f["accepted"],
            }
        )
    # one of each kind from the sweep, so every status has a named example
    for kind in ("fixed", "cycle", "loop", "escapes", "chaotic"):
        first = next(s for s in sweep if s["status"] == kind)
        named.setdefault(first["code"], f"first {kind} in the sweep")
    cases = []
    for code, why in named.items():
        f = m.try_code(code)
        cases.append(
            {
                "code": code,
                "why": why,
                "status": f["result"]["status"],
                "lyapunov": f["result"]["lyapunov"],
                "dimension": f["dimension"],
                "at": f["result"]["at"],
                "describe": m.describe(f["result"]["lyapunov"], f["dimension"]),
            }
        )
    hunts = []
    for seed in range(1, 9):
        f = m.hunt(seed)
        assert f is not None
        hunts.append({"seed": seed, "code": f["code"], "tried": f["tried"]})
    stream = m.mulberry32(1)
    out = {
        "tolerance": {"lyapunov": 1e-9, "dimension": 1e-9},
        "rng_seed_1": [stream() for _ in range(6)],
        "cases": cases,
        "hunts": hunts,
        "sweep": sweep,
    }
    (HERE / "vectors.json").write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
