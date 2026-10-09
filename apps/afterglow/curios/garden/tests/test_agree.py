"""Python's mirror of lsys.js and words.js must give the browser's answers:
the same strings at every generation, the same top generation, the same
growth stage, the same verdict on a genome string. The JS side runs in node
(tests/agree.mjs) on the very cases built here."""

from __future__ import annotations

import hashlib
import json
import random
import shutil
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
STARTERS = json.loads((HERE.parent / "starters.json").read_text(encoding="utf-8"))
SEEDS = [
    json.loads(p.read_text(encoding="utf-8"))
    for p in sorted((HERE.parent / "seeds").glob("*.json"))
]

pytestmark = pytest.mark.skipif(
    shutil.which("node") is None, reason="node is not on PATH"
)


@pytest.fixture
def m(load_curio):
    return load_curio("garden")


def sha(text: str) -> str:
    return hashlib.sha1(text.encode()).hexdigest()


def run_node(cases: dict) -> dict:
    out = subprocess.run(
        ["node", str(HERE / "agree.mjs")],
        input=json.dumps(cases),
        capture_output=True,
        text=True,
        timeout=60,
        check=True,
    )
    return json.loads(out.stdout)


def build_genomes(m) -> list[dict]:
    genomes = [m.clean_genome(p["genome"]) for p in STARTERS["plants"]]
    genomes += [m.clean_genome(s["data"]["genome"]) for s in SEEDS]
    genomes += [m.random_genome(seed) for seed in range(40)]
    for i in range(20):
        a, b = genomes[i], genomes[-1 - i]
        genomes.append(m.cross(a, b, 1000 + i))
    # built to explode: the caps must stop both sides at the same generation
    hostile = [
        {"axiom": "F", "rules": {"F": ["F" * 60]}, "max_gen": 7, "seed": 1},
        {
            "axiom": "X",
            "rules": {"X": ["[X][X][X][X][X][X][X][X][X][X][X][X][X][X][X]"]},
            "max_gen": 7,
        },
        {
            "axiom": "XYZ",
            "rules": {"X": ["XYZXYZ"], "Y": ["FZFZ", "ZZZ"], "Z": ["XFXF"]},
            "max_gen": 7,
        },
        {
            "axiom": "F",
            "rules": {"F": ["F+F-F[F]F", "FF[+F]"]},
            "max_gen": 7,
            "seed": 99,
        },
    ]
    genomes += [m.clean_genome(h) for h in hostile]
    return genomes


def test_python_and_js_agree(m):
    genomes = build_genomes(m)
    start = datetime(2026, 10, 9, 9, 45, tzinfo=timezone(timedelta(hours=1)))
    plants, py_stages = [], []
    for i, g in enumerate(genomes[:30]):
        top = m.effective_max_gen(g)
        for hours in (-3, 0, 0.25, 7.5, 31, 24 * 9, 24 * 400):
            now = start + timedelta(hours=hours)
            plant = {
                "planted": start.isoformat(),
                "head_start_hours": i % 5 * 3.5,
                "genome": g,
            }
            plants.append(
                {"plant": plant, "now_ms": now.timestamp() * 1000, "max_gen": top}
            )
            py_stages.append(m.growth_stage(plant, top, now))
    rnd = random.Random(125)
    strings = ["", "F", "F[+X]", "F[", "][", "F\n", "f", "F ", "[[]]", "É"]
    strings += [
        "".join(rnd.choice("FXY+-[]f1 \n") for _ in range(rnd.randint(0, 9)))
        for _ in range(800)
    ]
    rule_texts = [
        "X = F[+X]FX | F[-X]FX\nF = FF",
        "X = F|FF|FFF",
        "Y = [Y]",
        "X = F[\n",
        "x = F",
    ]
    rule_texts += [
        "\n".join(
            f"{rnd.choice('XYF')} = "
            + " | ".join(
                rnd.choice(["F[+X]X", "F[", "FX", "F" * 61, "[Y]Y"])
                for _ in range(rnd.randint(1, 4))
            )
            for _ in range(rnd.randint(1, 4))
        )
        for _ in range(200)
    ]
    js = run_node(
        {
            "genomes": genomes,
            "plants": plants,
            "strings": strings,
            "rule_texts": rule_texts,
        }
    )

    for g, want in zip(genomes, js["genomes"], strict=True):
        assert m.effective_max_gen(g) == want["top"], g
        for gen, step in enumerate(want["steps"]):
            text, fresh, reached = m.expand(g, gen)
            got = {
                "gen": reached,
                "len": len(text),
                "str": sha(text),
                "fresh": sha("".join(map(str, fresh))),
            }
            assert got == step, (g, gen)
        text, fresh, _ = m.expand(g, want["top"])
        t = m.turtle(g, text, fresh)
        xs = [0.0] + [p for s in t["segs"] for p in (s[0], s[2])]
        ys = [0.0] + [p for s in t["segs"] for p in (s[1], s[3])]
        tw = want["turtle"]
        assert len(t["segs"]) == tw["segs"]
        assert len(t["buds"]) == tw["buds"]
        assert sum(1 for b in t["buds"] if b[4]) == tw["flowers"]
        for got, key in ((min(xs), "minX"), (max(xs), "maxX"), (max(ys), "maxY")):
            assert abs(got - tw[key]) < 1e-9, key

    assert py_stages == pytest.approx(js["stages"], abs=1e-9)

    def py_ok(text: str) -> bool:
        try:
            m._string(text, "it", 10**6)
        except m.store.StoreError:
            return False
        return True

    assert [py_ok(s) for s in strings] == js["ok"]
    accepted = [r for r in js["rules"] if r is not None]
    assert len(accepted) > 10
    for rules in accepted:  # what the genome editor accepts, the server takes too
        m.clean_genome({"axiom": "X", "rules": rules})
