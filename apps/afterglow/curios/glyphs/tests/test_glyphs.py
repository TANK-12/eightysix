"""The Python half of Glyphs: the Python-vs-JS agreement sweep (agree.mjs runs
the same corpus through lang.js and compose.js), the routes, the play.py
commands and the hostile input both languages must refuse."""

from __future__ import annotations

import json
import math
import shutil
import struct
import subprocess
import sys
import threading
import zlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

HERE = Path(__file__).resolve().parent
APP = HERE.parents[2]

# Formulas both languages must accept. Chosen to hit every rule that could
# drift: precedence, %, & and |, round, NaN and Infinity, noise, rand.
GOOD = [
    "sin(t - hypot(x - 7.5, y - 7.5))",
    "x",
    "t",
    "i / n",
    "u + v",
    "r",
    "a",
    "(x - y) % 3",
    "-x % 3",
    "x % -3",
    "-7 % 2",
    "mod(-x, 3)",
    "mod(x, -4)",
    "x & y",
    "x | y",
    "(x * 1e10) & 255",
    "1e20 | 0",
    "-1e20 | 0",
    "-1.9 | 0",
    "2147483648 | 0",
    "4294967295 & x",
    "123456789 * 987654321 & 65535",
    "1e300 * 1e300",
    "1e999",
    "-1e999 + x",
    "1 / 0",
    "0 / 0",
    "-1 / 0",
    "x / (y - 3)",
    "sqrt(-1)",
    "sqrt(x)",
    "log(0)",
    "log(x)",
    "exp(1000)",
    "exp(-u)",
    "pow(-8, 1/3)",
    "(-8) ** (1/3)",
    "pow(0, -1)",
    "pow(1e308, 2)",
    "hypot(1e308, 1e308)",
    "2 ** 3 ** 2",
    "-2 ** 2",
    "2 ^ -1",
    "- - x",
    "+-+x",
    "!x",
    "!!x",
    "x < y ? 1 : -1",
    "x > 3 ? y > 3 ? 1 : 0.5 : -1",
    "x == y || -1",
    "x && y",
    "x || y && 0",
    "x > 3 && y > 3",
    "x >= 5 != y <= 2",
    "1 + 2 * 3 - 4 / 2",
    "1 + 2 & 3 | 4 < 5",
    "round(-2.5)",
    "round(2.5)",
    "round(u)",
    "floor(-1.5) + ceil(-1.5)",
    "fract(-1.25)",
    "fract(u / 3)",
    "sign(u)",
    "abs(v)",
    "min(x, y, 3)",
    "max(x)",
    "max(u, v, -2, 1)",
    "clamp(u, -2, 2)",
    "mix(x, y, 0.25)",
    "noise(x / 4, y / 4, t)",
    "noise(x)",
    "noise(u, v)",
    "noise(1e12, -1e12, t)",
    "noise(-x * 0.37, y * 1.3, -t)",
    "rand()",
    "rand(x)",
    "rand(-3.5)",
    "rand(1e15)",
    "atan2(v, u)",
    "tan(x)",
    "cos(a * 3) * sin(r - t)",
    "PI * TAU",
    "pi - tau",
    "x ^ 2",
    ".5 + 5. + 1e3 + 2E-2 + 1e+2",
    "  x  +\n y\t ",
    "y > 7 ? sin(t * 3 - r) : cos(a * 2)",
    "mod(x, 0)",
    "x % 0",
    "(x)",
    "((((x))))",
    "-" * 31 + "x",
    "(" * 31 + "x" + ")" * 31,
    "x+" * 199 + "x",
]

TOO_LONG = "x+" * 200 + "x"
TOO_DEEP_PARENS = "(" * 33 + "x" + ")" * 33
TOO_DEEP_MINUS = "-" * 33 + "x"
TOO_DEEP_CALLS = "sin(" * 33 + "x" + ")" * 33
TOO_DEEP_IF = "x ? " * 33 + "1" + " : 0" * 33

HOSTILE_NAMES = [
    "constructor",
    "__proto__",
    "prototype",
    "toString",
    "valueOf",
    "this",
    "globalThis",
    "process",
    "window",
    "import",
    "hasOwnProperty",
    "__class__",
    "__import__",
    "eval",
]

# Formulas both languages must refuse, with the same message and column.
BAD = [
    "",
    "   ",
    "x +",
    "sin(",
    "sin(x",
    "sin x",
    "sin",
    "foo",
    "sni(t)",
    "sinn(t)",
    "hypt(x, y)",
    "nosie(x)",
    "tt",
    "x = y",
    "x $ y",
    "x y",
    "2 3",
    "2(x)",
    "(x",
    "x)",
    "x ? 1",
    "x ? 1 2",
    "hypot(x)",
    "min()",
    "rand(1, 2)",
    "clamp(1, 2)",
    "t(1)",
    "PI(2)",
    ",",
    "x ,",
    "x +* y",
    "x === y",
    "1 + \U0001f600",
    "\U0001f600",
    "é",
    "x;",
    "sin.constructor",
    "x[0]",
    "'a'",
    '"x"',
    "`x`",
    "x => x",
    "@",
    "x\\y",
    TOO_LONG,
    TOO_DEEP_PARENS,
    TOO_DEEP_MINUS,
    TOO_DEEP_CALLS,
    TOO_DEEP_IF,
    *HOSTILE_NAMES,
    *(f"{name}(x)" for name in HOSTILE_NAMES),
    *(f"x + {name}" for name in HOSTILE_NAMES),
]

TIMES_AND_SIZES = [(0.0, 16), (1.7, 5), (-3.25, 1), (1000.5, 8)]
SEEDS = [*range(300), 2**31 - 1, 2**31, 2**32 - 1, 123456789]


@pytest.fixture
def m(load_curio):
    return load_curio("glyphs")


def close(a: float, b: float) -> bool:
    return abs(a - b) <= 1e-9 * max(1.0, abs(a), abs(b))


def run_js(cases: list[dict], seeds: list[int]) -> dict:
    node = shutil.which("node")
    assert node, "node is needed for the agreement sweep"
    job = json.dumps({"cases": cases, "seeds": seeds})
    done = subprocess.run(
        [node, str(HERE / "agree.mjs")],
        input=job,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


def py_case(m, src: str, t: float, n: int) -> dict:
    try:
        ast = m.parse(src)
    except m.GlyphError as exc:
        return {"error": {"message": exc.message, "col": exc.col}}
    return {"show": m.show(ast), "values": m.frame(src, t, n)}


def png_info(path: Path) -> tuple[int, int, bytes]:
    data = path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    w, h = struct.unpack(">II", data[16:24])
    idat = data.index(b"IDAT")
    (size,) = struct.unpack(">I", data[idat - 4 : idat])
    return w, h, zlib.decompress(data[idat + 4 : idat + 4 + size])


# --- the agreement sweep ------------------------------------------------------


def test_python_and_js_agree_on_everything(m):
    composed = [m.compose(s) for s in SEEDS]
    seeds_dir = HERE.parent / "seeds"
    shipped = [
        json.loads(p.read_text(encoding="utf-8"))["data"]["formula"]
        for p in sorted(seeds_dir.glob("*.json"))
    ]
    formulas = [*GOOD, *BAD, *shipped, *{c["formula"] for c in composed}]
    cases = [{"src": f, "t": t, "n": n} for f in formulas for t, n in TIMES_AND_SIZES]
    js = run_js(cases, SEEDS)

    assert js["seeds"] == composed
    assert len(js["cases"]) == len(cases)
    good = set(GOOD) | set(shipped) | {c["formula"] for c in composed}
    checked = 0
    for case, theirs in zip(cases, js["cases"]):
        ours = py_case(m, case["src"], case["t"], case["n"])
        label = f"{case['src'][:60]!r} t={case['t']} n={case['n']}"
        if case["src"] in good:
            assert "error" not in ours, f"{label}: Python refused it: {ours}"
        else:
            assert "error" in ours, f"{label}: Python accepted it"
        if "error" in ours:
            assert theirs == ours, label
            continue
        assert "error" not in theirs, f"{label}: JS refused it: {theirs}"
        assert theirs["show"] == ours["show"], label
        assert len(theirs["values"]) == len(ours["values"]) == case["n"] ** 2
        for k, (a, b) in enumerate(zip(ours["values"], theirs["values"])):
            assert math.isfinite(a), f"{label} dot {k}: {a}"
            assert close(a, b), f"{label} dot {k}: Python {a} vs JS {b}"
            checked += 1
    assert checked > 100_000


def test_compose_always_parses_and_is_deterministic(m):
    recipes = set()
    for seed in range(400):
        piece = m.compose(seed)
        assert piece == m.compose(seed)
        assert piece["seed"] == seed
        m.parse(piece["formula"])
        assert piece["title"] and piece["title"][0].isupper()
        recipes.add(piece["recipe"])
    assert recipes == set(m.RECIPES)
    assert m.compose(-1)["seed"] == 2**32 - 1
    assert m.compose(2**32 + 5) == m.compose(5)


# --- the language, from Python ------------------------------------------------


def test_precedence_and_the_javascript_rules(m):
    def one(src: str) -> float:
        return m.frame(src, 0.0, 1)[0]

    assert m.show(m.parse("1 + 2 * 3")) == "(1 + (2 * 3))"
    assert m.show(m.parse("-2 ** 2")) == "(-(2 ** 2))"
    assert m.show(m.parse("2 ** 3 ** 2")) == "(2 ** (3 ** 2))"
    assert m.show(m.parse("a ? r ? 1 : 2 : 3")) == "(a ? (r ? 1 : 2) : 3)"
    assert one("-7 % 2") == -1 and one("7 % -2") == 1
    assert one("mod(-7, 2)") == 1
    assert one("round(-2.5)") == -2 and one("round(2.5)") == 3
    assert one("2147483648 | 0") == -2147483648
    assert one("-1.9 | 0") == -1
    assert one("6 & 3") == 2 and one("6 | 3") == 7
    for src in ("1/0", "0/0", "-1/0", "1e999", "1e308 * 10", "x % 0", "log(0)"):
        assert one(src) == 0, src
    for src in ("sqrt(-1)", "exp(1000)", "pow(-8, 1/3)", "pow(0, -1)"):
        assert one(src) == 0, src


def test_noise_and_rand_are_steady(m):
    assert m.noise(1.3, 2.7, 0.5) == m.noise(1.3, 2.7, 0.5)
    assert all(-1 <= m.noise(k * 0.37, k * 0.11, -k) <= 1 for k in range(500))
    assert m.rand(3) == m.rand(3.9) != m.rand(4)
    assert all(0 <= m.rand(k) <= 1 for k in range(-200, 200))


def test_hostile_input_is_refused_in_python(m):
    with pytest.raises(m.GlyphError, match="under 400 characters") as long_err:
        m.parse(TOO_LONG)
    assert long_err.value.col == m.MAX_LENGTH + 1
    for deep in (TOO_DEEP_PARENS, TOO_DEEP_MINUS, TOO_DEEP_CALLS, TOO_DEEP_IF):
        with pytest.raises(m.GlyphError, match="Nested too deeply"):
            m.parse(deep)
    for name in HOSTILE_NAMES:
        for src, col in ((name, 1), (f"{name}(x)", 1), (f"x + {name}", 5)):
            with pytest.raises(m.GlyphError, match=f"Unknown name '{name}'") as e:
                m.parse(src)
            assert e.value.col == col, src
    with pytest.raises(m.GlyphError, match=r"did you mean 'sin'\?"):
        m.parse("sni(t)")
    with pytest.raises(m.GlyphError, match=r"did you mean 'hypot'\?"):
        m.parse("hypt(x, y)")
    assert m.frame("t", math.inf, 2) == [0.0] * 4
    assert m.frame("t", math.nan, 2) == [0.0] * 4


# --- nothing at import, routes, play.py ---------------------------------------


def test_nothing_happens_at_import(data_dir):
    before = threading.active_count()
    code = (
        "import sys; sys.path.insert(0, sys.argv[1]); import registry, os;"
        "registry.load_server('glyphs');"
        "print(os.path.exists(os.environ['AFTERGLOW_DATA']))"
    )
    done = subprocess.run(
        [sys.executable, "-c", code, str(APP)],
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    assert done.stdout.strip() == "False"
    assert not data_dir.exists()
    assert threading.active_count() == before


def test_the_module_offers_three_commands(m):
    assert set(m.COMMANDS) == {"try", "compose", "keep"}


@pytest.fixture
def client():
    import web_app

    return TestClient(web_app.app)


def test_route_compose(client, m):
    res = client.get("/api/curio/glyphs/compose", params={"seed": 42})
    assert res.status_code == 200
    assert res.json() == m.compose(42)
    assert client.get("/api/curio/glyphs/compose?seed=-1").json()["seed"] == 2**32 - 1
    assert client.get("/api/curio/glyphs/compose?seed=abc").status_code == 422


def test_route_frame(client, m):
    res = client.get(
        "/api/curio/glyphs/frame", params={"formula": "sin(t - r)", "t": 2, "n": 6}
    )
    assert res.status_code == 200
    body = res.json()
    assert body["n"] == 6 and len(body["values"]) == 36
    assert body["values"] == m.frame("sin(t - r)", 2.0, 6)
    assert body["text"].startswith("┌")
    big = client.get("/api/curio/glyphs/frame", params={"formula": "x", "n": 10**6})
    assert big.json()["n"] == 64
    small = client.get("/api/curio/glyphs/frame", params={"formula": "x", "n": -3})
    assert small.json()["n"] == 2


@pytest.mark.parametrize(
    "formula, words",
    [
        ("sni(t)", "did you mean 'sin'"),
        ("x +", "ends too soon"),
        ("constructor", "Unknown name 'constructor'"),
        ("__proto__", "Unknown name '__proto__'"),
        (TOO_LONG, "under 400 characters"),
        (TOO_DEEP_PARENS, "Nested too deeply"),
        ("", "Write a formula"),
    ],
)
def test_route_frame_refuses_bad_formulas_clearly(client, formula, words):
    res = client.get("/api/curio/glyphs/frame", params={"formula": formula})
    assert 400 <= res.status_code < 500, res.text
    assert words in res.json()["detail"]


@pytest.mark.parametrize("t", ["inf", "-inf", "nan", "1e308"])
def test_route_frame_never_500s_on_odd_numbers(client, t):
    res = client.get("/api/curio/glyphs/frame", params={"formula": "t * x", "t": t})
    assert res.status_code < 500, res.text
    if res.status_code == 200:
        assert all(math.isfinite(v) for v in res.json()["values"])


def test_route_frame_without_a_formula_is_a_4xx(client):
    assert client.get("/api/curio/glyphs/frame").status_code == 422


def test_cli_try_prints_text_art(m, capsys, data_dir):
    assert m.cli_try(["sin(t - r)", "--n", "8", "--t", "0.5"]) == 0
    out = capsys.readouterr().out
    lines = out.splitlines()
    assert lines[0] == "┌" + "─" * 16 + "┐"
    assert len(lines[1]) == 18 and lines[1][0] == lines[1][-1] == "│"
    assert "t = 0.5, 8 x 8 dots" in out
    assert not data_dir.exists()


def test_cli_try_shows_where_the_error_is(m, capsys):
    assert m.cli_try(["x + sni(t)"]) == 1
    out = capsys.readouterr().out
    assert "    ^ column 5: Unknown name 'sni' (did you mean 'sin'?)" in out


def test_cli_try_png_lands_in_the_data_folder(m, capsys, data_dir):
    assert m.cli_try(["x / (y + 1) / 2", "--n", "4", "--png"]) == 0
    line = [s for s in capsys.readouterr().out.splitlines() if s.startswith("pic")]
    path = Path(line[0].split(": ", 1)[1])
    assert path.resolve().is_relative_to(data_dir.resolve())
    w, h, raw = png_info(path)
    assert (w, h) == (4 * 24, 4 * 24)
    assert len(raw) == h * (1 + 3 * w)


def test_cli_compose(m, capsys):
    assert m.cli_compose(["--seed", "7", "--n", "6"]) == 0
    out = capsys.readouterr().out.splitlines()
    piece = m.compose(7)
    assert out[0].startswith(piece["title"]) and "seed 7" in out[0]
    assert out[1] == piece["formula"]
    assert out[2] == "┌" + "─" * 12 + "┐"


def test_cli_keep_saves_and_loads_back(m, capsys, data_dir):
    import store

    assert (
        m.cli_keep(
            [
                "sin(t - r)",
                "--name",
                "Pond",
                "--note",
                "a test",
                "--grid",
                "500",
                "--speed",
                "-2",
                "--palette",
                "sea",
            ]
        )
        == 0
    )
    slug = capsys.readouterr().out.split("Kept glyphs/", 1)[1].strip()
    kept = store.load_keepsake("glyphs", slug)
    assert kept["name"] == "Pond" and kept["note"] == "a test"
    assert kept["data"] == {
        "formula": "sin(t - r)",
        "grid": 64,
        "speed": 0.0,
        "palette": "sea",
        "shape": "circle",
    }
    assert str(data_dir) in str(store.data_dir())


def test_cli_keep_refuses_a_broken_formula(m, capsys, data_dir):
    import store

    before = len(store.list_keepsakes("glyphs"))
    assert m.cli_keep(["sin(", "--name", "Broken"]) == 1
    assert "Not kept: column 5" in capsys.readouterr().out
    assert len(store.list_keepsakes("glyphs")) == before


def test_play_py_runs_the_command(data_dir):
    done = subprocess.run(
        [sys.executable, str(APP / "play.py"), "glyphs", "try", "x - y", "--n", "4"],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert done.returncode == 0, done.stderr
    assert done.stdout.startswith("┌" + "─" * 8 + "┐")


def test_every_seed_is_a_clean_piece(m):
    for path in sorted((HERE.parent / "seeds").glob("*.json")):
        seed = json.loads(path.read_text(encoding="utf-8"))
        data = seed["data"]
        m.parse(data["formula"])
        assert 4 <= data["grid"] <= 64, path.name
        assert 0 <= data["speed"] <= 4, path.name
        assert data["palette"] in m.PALETTES and data["shape"] in m.SHAPES
        assert seed["name"] and seed["note"] and seed["made"]
