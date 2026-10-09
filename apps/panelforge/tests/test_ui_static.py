"""UI static-serving checks for helper-6's frontend.

Two things, run against the real FastAPI app (no server needed):

1. index.html and every static asset it references (css/js) are actually
   served with a 200 -- catches a typo'd <script src> or a file that never
   got written.
2. Every `/api/...` path used in a fetch()/PF.getJson()/PF.postJson()/... call
   anywhere under static/js matches one of the endpoint patterns CONTRACTS.md
   promises. This is a static check (regex against the JS source, not a live
   call), so it still passes while the other helpers' backends are missing --
   it is only checking that the *frontend* is calling contract-shaped URLs.
"""

import re
from pathlib import Path

from fastapi.testclient import TestClient

import web_app

APP_ROOT = Path(__file__).resolve().parent.parent
STATIC = APP_ROOT / "static"
CONTRACTS = (APP_ROOT / "CONTRACTS.md").read_text()

client = TestClient(web_app.app)

# {s} -> series slug, {c} -> chapter slug, {id}/{pid}/{cast_id}/{job_id} -> any
# single path segment. Kept in the same order CONTRACTS.md lists them so a
# failure is easy to trace back to a line there.
CONTRACT_PATTERNS = [
    r"^/api/series$",
    r"^/api/series/[^/]+$",
    r"^/api/series/[^/]+/chapters$",
    r"^/api/fetch/title$",
    r"^/api/fetch/chapters$",
    r"^/api/sources$",
    r"^/api/import/path$",
    r"^/api/import/upload$",
    r"^/api/mediaforge/downloads$",
    r"^/api/import/mediaforge$",
    r"^/api/export/pdf$",
    r"^/api/chapters/[^/]+/[^/]+/pages/[^/]+$",
    r"^/api/chapters/[^/]+/[^/]+/detect$",
    r"^/api/chapters/[^/]+/[^/]+/panels$",
    r"^/api/chapters/[^/]+/[^/]+/bubbles$",
    r"^/api/chapters/[^/]+/[^/]+/panels/[^/]+/image$",
    r"^/api/chapters/[^/]+/[^/]+/analyze$",
    r"^/api/chapters/[^/]+/[^/]+/scene$",
    r"^/api/series/[^/]+/cast$",
    r"^/api/series/[^/]+/cast/[^/]+/voice$",
    r"^/api/series/[^/]+/assets/[^/]+$",
    r"^/api/voices$",
    r"^/api/voices/audition$",
    r"^/api/series/[^/]+/narrator/voice$",
    r"^/api/chapters/[^/]+/[^/]+/script$",
    r"^/api/chapters/[^/]+/[^/]+/script/build$",
    r"^/api/chapters/[^/]+/[^/]+/voice$",
    r"^/api/chapters/[^/]+/[^/]+/audio/auto$",
    r"^/api/sfx$",
    r"^/api/music$",
    r"^/api/sfx/audition$",
    r"^/api/styles$",
    r"^/api/transitions$",
    r"^/api/chapters/[^/]+/[^/]+/timeline$",
    r"^/api/chapters/[^/]+/[^/]+/timeline/auto$",
    r"^/api/chapters/[^/]+/[^/]+/preview$",
    r"^/api/chapters/[^/]+/[^/]+/render$",
    r"^/api/renders$",
    r"^/api/jobs$",
    r"^/api/jobs/[^/]+$",
    r"^/api/jobs/[^/]+/cancel$",
    r"^/api/jobs/[^/]+/events$",
    r"^/api/health$",
    # Editing endpoints added after CONTRACTS.md was first written; the paths
    # below are the ones the backend actually serves (see the live-route test).
    r"^/api/chapters/[^/]+/[^/]+/lines/[^/]+/voice$",
    r"^/api/chapters/[^/]+/[^/]+/shots/[^/]+/render$",
    r"^/api/chapters/[^/]+/[^/]+/script/lines/[^/]+/emotion$",
    # session 4 (2026-09-19): the model page reading, the crop bench, bulk runs
    r"^/api/chapters/[^/]+/[^/]+/script/llm$",
    r"^/api/series/[^/]+/cast/appearances$",
    r"^/api/series/[^/]+/cast/unsorted$",
    r"^/api/series/[^/]+/run$",
    r"^/api/series/[^/]+/cast/voices/auto$",
    r"^/api/series/[^/]+/words$",
    r"^/api/chapters/[^/]+/[^/]+/bubbles/[^/]+/image$",
    r"^/api/sound$",
]
CONTRACT_RE = [re.compile(p) for p in CONTRACT_PATTERNS]

FETCH_CALL_RE = re.compile(
    r"""(?:fetch|PF\.getJson|PF\.postJson|PF\.putJson|PF\.postForm|PF\.readWithFallback|PF\.runJob)\(\s*`?(/api/[^"'`)]*)"""
)


def js_files():
    return sorted((STATIC / "js").rglob("*.js"))


def test_index_served():
    r = client.get("/")
    assert r.status_code == 200
    assert "PanelForge" in r.text


def test_index_references_are_served():
    html = (STATIC / "index.html").read_text()
    srcs = re.findall(r'(?:src|href)="(/(?:js|css|shared)/[^"]+)"', html)
    assert srcs, "index.html should reference at least one local script/style"
    for path in srcs:
        r = client.get(path)
        assert r.status_code == 200, f"{path} not served (HTTP {r.status_code})"


def test_all_js_modules_served():
    for f in js_files():
        rel = "/" + f.relative_to(STATIC).as_posix()
        r = client.get(rel)
        assert r.status_code == 200, f"{rel} not served (HTTP {r.status_code})"


def extract_api_paths(text):
    out = []
    for m in FETCH_CALL_RE.finditer(text):
        raw = m.group(1)
        # Collapse template-literal interpolations (${series}, ${s}/${c}, ...)
        # to a single-segment wildcard so it lines up with the {s}/{id} style
        # placeholders in CONTRACT_PATTERNS.
        norm = re.sub(r"\$\{[^}]*\}", "X", raw)
        norm = norm.split("?")[0].rstrip("/")
        if norm:
            out.append((raw, norm))
    return out


def test_fetch_paths_match_contract():
    problems = []
    for f in js_files():
        text = f.read_text()
        for raw, norm in extract_api_paths(text):
            if not any(p.match(norm) for p in CONTRACT_RE):
                problems.append(f"{f.relative_to(STATIC)}: {raw!r} -> {norm!r}")
    assert (
        not problems
    ), "fetch paths not matching any CONTRACTS endpoint:\n" + "\n".join(problems)


def test_health_endpoint_reachable():
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert "modules" in body and "failed" in body


def app_route_patterns():
    """Every path the running app serves, as a regex with one wildcard per
    `{placeholder}` segment.

    Read from the OpenAPI schema rather than `app.routes`, because this
    FastAPI keeps an included router's own routes inside a wrapper object
    instead of flattening them onto the app.
    """
    out = []
    for path in web_app.app.openapi().get("paths", {}):
        if path.startswith("/api/"):
            out.append(re.compile("^" + re.sub(r"\{[^}]+\}", "[^/]+", path) + "$"))
    return out


def test_every_frontend_api_url_exists_on_the_app():
    """The frontend must call paths the backend really serves.

    The contract check above compares the JS against a written list, so a URL
    can match the list and still 404 in the app -- which is exactly what
    happened to per-shot re-render and per-line re-speak. This compares the
    same URLs against the app's own routing table instead.
    """
    routes = app_route_patterns()
    assert routes, "no /api routes found on the app"
    problems = []
    for f in js_files():
        for raw, norm in extract_api_paths(f.read_text()):
            if not any(r.match(norm) for r in routes):
                problems.append(f"{f.relative_to(STATIC)}: {raw!r} -> {norm!r}")
    assert not problems, "frontend calls paths the app does not serve:\n" + "\n".join(
        problems
    )
