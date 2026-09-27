"""T09 security checklist and failure paths (fresh review, adversarial pass).

``-k xss``: an HTML payload in a filing comes back as inert JSON text, every response
carries ``X-Content-Type-Options: nosniff`` and the page ships a Content-Security-Policy
that forbids inline script (so even a future ``innerHTML`` regression cannot run an
``onerror`` handler). ``-k traversal``: ``/static`` never leaves web/static and a sample id
is matched against seed/samples.json, never used as a path (raw ASGI requests, so the
client cannot normalise ``..`` away before the server sees it). ``-k limits``: a chunked
body without ``Content-Length`` is cut off at 4 MB instead of being spooled whole; a
60-page filing with 250+ citations finishes (truncated) inside the 60 s function budget.
Also: the per-run log line carries hashes only, five concurrent sample runs, a corpus that
dies mid-run, malformed CAP JSON, an advisory client that raises, and the "fabricated"
wording rule (DECISION-RULE §6.3, UI-SPEC §9).
"""

from __future__ import annotations

import ast
import asyncio
import io
import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import unquote

import httpx
import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
SEED_CACHE = ROOT / "seed" / "cache" / "cap"
SAMPLE_TXT = ROOT / "seed" / "sample-motion.txt"
SAMPLE_PDF = ROOT / "seed" / "sample-motion.pdf"
PAYLOAD = "<img src=x onerror=alert(1)>"


@pytest.fixture(scope="module")
def offline_env():
    import os

    saved = {k: os.environ.get(k) for k in ("CITEMEMO_OFFLINE", "ANTHROPIC_API_KEY", "COURTLISTENER_TOKEN")}
    os.environ["CITEMEMO_OFFLINE"] = "1"
    os.environ.pop("ANTHROPIC_API_KEY", None)
    os.environ.pop("COURTLISTENER_TOKEN", None)
    yield
    for k, v in saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


@pytest.fixture(scope="module")
def client(offline_env):
    import main

    with TestClient(main.app) as c:
        yield c


def _xff(ip: str) -> dict:
    return {"X-Forwarded-For": ip}


def _asgi(method: str, raw_path: str, headers=(), chunks=None) -> tuple[int, bytes, dict, int]:
    """One request straight into ``main.app`` with the path exactly as a server would decode it.

    Returns ``(status, body, headers, request_bytes_consumed)``. ``chunks`` is an iterable
    of request-body chunks (sent without ``Content-Length`` unless ``headers`` has one).
    """
    import main

    it = iter(chunks or [b""])
    consumed = [0]
    pending = [next(it, None)]

    async def receive():
        cur = pending[0]
        if cur is None:
            return {"type": "http.disconnect"}
        nxt = next(it, None)
        pending[0] = nxt
        consumed[0] += len(cur)
        return {"type": "http.request", "body": cur, "more_body": nxt is not None}

    sent: list[dict] = []

    async def send(message):
        sent.append(message)

    path = unquote(raw_path.split("?", 1)[0])
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": raw_path.split("?", 1)[0].encode(),
        "query_string": b"",
        "root_path": "",
        "headers": [(k.lower().encode(), v.encode()) for k, v in headers],
        "client": ("198.51.100.250", 50000),
        "server": ("testserver", 80),
    }
    asyncio.run(main.app(scope, receive, send))
    start = next(m for m in sent if m["type"] == "http.response.start")
    body = b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body")
    hdrs = {k.decode().lower(): v.decode() for k, v in start.get("headers", [])}
    return start["status"], body, hdrs, consumed[0]


# --------------------------------------------------------------------------- #
# Client exposure: HTML in a filing is data, never markup
# --------------------------------------------------------------------------- #


def test_xss_payload_round_trips_as_plain_json_text(client):
    text = (
        f'Plaintiff {PAYLOAD} v. United Airlines, Inc., 174 F.3d 366 (2d Cir. 1999). '
        f'The court held that "{PAYLOAD} carriers are liable." Greenleaf v. Garlock, Inc., 174 F.3d 352, 355 (3d Cir. 1999).'
    )
    r = client.post("/api/memo", data={"text": text}, headers=_xff("198.51.100.20"))
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("application/json")
    assert r.headers.get("x-content-type-options") == "nosniff"
    memo = r.json()
    quotes = [row["quote_check"]["quote"] for row in memo["results"] if row.get("quote_check")]
    assert f"{PAYLOAD} carriers are liable." in quotes  # verbatim: not escaped, not stripped, not executed
    # the payload never turns a real case red and never reaches a reason sentence as markup
    for row in memo["results"]:
        assert "<img" not in " ".join(row["reasons"])
    # a file name is echoed back verbatim as JSON text as well
    r = client.post(
        "/api/memo",
        files={"file": (f"{PAYLOAD}.pdf", io.BytesIO(SAMPLE_PDF.read_bytes()), "application/pdf")},
        headers=_xff("198.51.100.21"),
    )
    assert r.status_code == 200, r.text
    assert r.headers.get("x-content-type-options") == "nosniff"
    assert r.json()["filing"]["filename"] == f"{PAYLOAD}.pdf"
    # error envelopes that echo input are JSON with nosniff too
    r = client.post(f"/api/memo/sample/{PAYLOAD}")
    assert r.status_code == 404
    assert r.headers["content-type"].startswith("application/json")
    assert r.headers.get("x-content-type-options") == "nosniff"


def test_xss_page_ships_a_csp_without_inline_script(client):
    if not (ROOT / "web" / "index.html").exists():
        pytest.skip("web/index.html not built")
    r = client.get("/")
    assert r.status_code == 200
    assert r.headers.get("x-content-type-options") == "nosniff"
    csp = r.headers.get("content-security-policy", "")
    directives = {d.strip().split(" ", 1)[0]: d.strip() for d in csp.split(";") if d.strip()}
    assert "script-src" in directives, csp
    assert "'unsafe-inline'" not in directives["script-src"] and "'unsafe-eval'" not in directives["script-src"]
    assert "object-src 'none'" in csp and "base-uri 'none'" in csp and "frame-ancestors 'none'" in csp
    # the page itself needs nothing the policy forbids: one same-origin script, no inline handlers
    page = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    assert "<script>" not in page and " onerror=" not in page and " onclick=" not in page


# --------------------------------------------------------------------------- #
# Validation: no path escapes
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "raw",
    [
        "/static/../main.py",
        "/static/%2e%2e/main.py",
        "/static/..%2fmain.py",
        "/static/%2e%2e%2f%2e%2e%2fetc%2fpasswd",
        "/static/../../../../etc/passwd",
        "/static/..%5cmain.py",
        "/static/",
    ],
)
def test_traversal_static_serves_only_web_static(offline_env, raw):
    status, body, headers, _ = _asgi("GET", raw)
    assert status == 404, (raw, status, body[:200])
    assert json.loads(body)["error"]["code"] == "not_found"
    assert b"FastAPI" not in body and b"root:" not in body


@pytest.mark.parametrize("sample_id", ["../../etc/passwd", "..%2f..%2fetc%2fpasswd", "%2e%2e", "..", "sample-motion%00", "..%2fsamples.json"])
def test_traversal_sample_id_is_matched_never_a_path(offline_env, sample_id):
    status, body, _, _ = _asgi("POST", f"/api/memo/sample/{sample_id}")
    assert status == 404, (sample_id, status, body[:200])
    err = json.loads(body)["error"]
    assert err["code"] == "not_found"
    assert "root:" not in body.decode() and "sample-motion.pdf" not in body.decode()


def test_traversal_sample_lookup_does_not_touch_the_filesystem(offline_env, monkeypatch):
    from citememo import memo as memo_mod

    def boom(*_a, **_k):  # pragma: no cover - the assertion is that it is never called
        raise AssertionError("sample id reached the filesystem")

    monkeypatch.setattr(memo_mod, "run_sample", boom)
    status, _, _, _ = _asgi("POST", "/api/memo/sample/..%2f..%2fetc%2fpasswd")
    assert status == 404
    assert memo_mod.sample_record("../../etc/passwd") is None


# --------------------------------------------------------------------------- #
# Limits: a chunked body is refused at 4 MB, not spooled whole
# --------------------------------------------------------------------------- #


def test_limits_chunked_body_is_cut_off_at_4_mb(offline_env):
    from citememo import limits

    boundary = "t09-b0undary"
    head = (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="file"; filename="big.pdf"\r\n'
        "Content-Type: application/pdf\r\n\r\n%PDF-1.4\n"
    ).encode()
    mb = b"0" * (1 << 20)
    total_mb = 40

    def chunks():
        yield head
        for _ in range(total_mb):
            yield mb
        yield f"\r\n--{boundary}--\r\n".encode()

    headers = [("content-type", f"multipart/form-data; boundary={boundary}"), ("x-forwarded-for", "198.51.100.30")]
    status, body, _, consumed = _asgi("POST", "/api/memo", headers=headers, chunks=chunks())
    assert status == 413, body[:300]
    assert json.loads(body)["error"]["code"] == "too_large"
    # the server stopped reading shortly after the limit instead of taking all 40 MB
    assert consumed <= limits.MAX_BODY_BYTES + 2 * (1 << 20), consumed


def test_limits_sixty_page_filing_with_260_citations_finishes_truncated(client):
    """Offline: 60 pages, 260 full citations into cached volumes → 250 rows, a Truncated: line, well inside 60 s."""
    from citememo import limits

    seeds = [
        "Air France v. Saks, 470 U.S. 392 (1985)",
        "Greenleaf v. Garlock, Inc., 174 F.3d 352 (3d Cir. 1999)",
        "Miller v. United Airlines, Inc., 174 F.3d 366 (2d Cir. 1999)",
        "J.D. v. Azar, 925 F.3d 1291 (D.C. Cir. 2019)",
        "Varghese v. China Southern Airlines Co., 925 F.3d 1339 (11th Cir. 2019)",
        "Olympic Airways v. Husain, 540 U.S. 644 (2004)",
        "El Al Israel Airlines, Ltd. v. Tsui Yuan Tseng, 525 U.S. 155 (1999)",
        "Eastern Airlines, Inc. v. Floyd, 499 U.S. 530 (1991)",
    ]
    filler = "The movant restates the facts of the flight and the injury in plain words. " * 6
    parts = []
    for i in range(260):
        parts.append(f"{filler}See {seeds[i % len(seeds)]}.")
        if i % 5 == 4:
            parts.append("\f")
    text = " ".join(parts)
    assert text.count("\f") >= 50
    assert len(text) < limits.MAX_TEXT_CHARS
    t0 = time.time()  # wall clock, not perf_counter (F-0003)
    r = client.post("/api/memo", data={"text": text}, headers=_xff("198.51.100.40"))
    wall = time.time() - t0
    assert r.status_code == 200, r.text[:500]
    memo = r.json()
    assert memo["counts"]["total"] == limits.MAX_CITATIONS
    assert any(w.startswith("Truncated:") for w in memo["warnings"])
    assert memo["filing"]["pages"] >= 50
    assert wall < 60.0, wall
    real = [row for row in memo["results"] if not row["cite_text"].startswith(("Miller", "Varghese"))]
    assert all(row["class"] != "likely_fabricated" for row in real)


# --------------------------------------------------------------------------- #
# Concurrency and failure paths
# --------------------------------------------------------------------------- #


def test_five_concurrent_sample_runs_complete(client):
    def run(_):
        r = client.post("/api/memo/sample/sample-motion")
        return r.status_code, r.json()

    with ThreadPoolExecutor(max_workers=5) as ex:
        out = list(ex.map(run, range(5)))
    assert [s for s, _ in out] == [200] * 5
    classes = [[row["class"] for row in body["results"]] for _, body in out]
    assert all(c == classes[0] for c in classes)
    assert len({body["run_id"] for _, body in out}) == 5


def _seed_handler(override):
    def handler(request: httpx.Request) -> httpx.Response:
        rel = request.url.path.lstrip("/")
        hit = override(rel)
        if hit is not None:
            return hit
        p = SEED_CACHE / rel
        if p.exists():
            return httpx.Response(200, content=p.read_bytes(), headers={"content-type": "application/json"})
        return httpx.Response(404, text="<html>not found</html>")

    return handler


def test_corpus_dies_mid_run_gives_a_partial_memo(tmp_path, monkeypatch):
    """Lookups succeed, then the corpus goes away before the opinion texts: memo still returns, nothing turns red."""
    monkeypatch.delenv("CITEMEMO_OFFLINE", raising=False)
    from citememo import memo as memo_mod
    from citememo.cache import DiskCache
    from citememo.cap import CapClient

    def override(rel):
        if "/cases/" in rel:
            raise httpx.ConnectError("corpus went away", request=httpx.Request("GET", "https://cap.invalid/" + rel))
        return None

    cache = DiskCache(write_dir=tmp_path / "cap", read_dirs=[tmp_path / "cap"])
    cap = CapClient(cache=cache, transport=httpx.MockTransport(_seed_handler(override)), offline=False, retries=0)
    memo = memo_mod.run_memo(text=SAMPLE_TXT.read_text(), filename="sample-motion.txt", cap=cap)
    assert memo.counts.total == 23
    assert any("did not answer for the opinion text" in w for w in memo.warnings), memo.warnings
    by_cite = {r.cite_text: r for r in memo.results}
    azar = by_cite["J.D. v. Azar, 925 F.3d 1291 (D.C. Cir. 2019)"]
    assert azar.class_ == "verified" and azar.quote_check is not None and azar.quote_check.status == "not_checked"
    assert by_cite["Varghese v. China Southern Airlines Co., 925 F.3d 1339 (11th Cir. 2019)"].class_ == "likely_fabricated"
    assert memo.counts.likely_fabricated == 3  # the same three as the full run (Miller, Varghese, Petersen)


@pytest.mark.parametrize("body", ['{"weird": 1}', '[{"weird": 1}, 5, "x", null]', '"text"', "null", "{not json"])
def test_malformed_cap_json_never_500s_or_reds(client, tmp_path, monkeypatch, body):
    import main
    from citememo.cache import DiskCache
    from citememo.cap import CapClient

    def override(rel):
        if rel == "f3d/174/CasesMetadata.json":
            return httpx.Response(200, text=body, headers={"content-type": "application/json"})
        return None

    cache = DiskCache(write_dir=tmp_path / "cap", read_dirs=[tmp_path / "cap"])
    cap = CapClient(cache=cache, transport=httpx.MockTransport(_seed_handler(override)), offline=False, retries=0)
    monkeypatch.setattr(main.state, "cap", cap)
    text = "Greenleaf v. Garlock, Inc., 174 F.3d 352 (3d Cir. 1999). Air France v. Saks, 470 U.S. 392 (1985)."
    r = client.post("/api/memo", data={"text": text}, headers=_xff("198.51.100.50"))
    assert r.status_code == 200, r.text
    rows = r.json()["results"]
    assert rows[0]["class"] in ("not_checked", "not_in_free_corpus"), rows[0]
    assert rows[1]["class"] == "verified"


def test_advisory_client_raising_gives_advisory_none(offline_env):
    from citememo import memo as memo_mod

    class Boom:
        class messages:  # noqa: N801 - duck-typed SDK surface
            @staticmethod
            def create(**_kwargs):
                raise RuntimeError("model unavailable")

    memo = memo_mod.run_memo(text=SAMPLE_TXT.read_text(), filename="sample-motion.txt", advisory_client=Boom())
    assert all(r.advisory is None for r in memo.results)
    assert memo.counts.total == 23 and memo.counts.likely_fabricated == 3


# --------------------------------------------------------------------------- #
# Logging: hashes only
# --------------------------------------------------------------------------- #


def test_log_line_has_no_filing_text_or_file_name(offline_env, monkeypatch, capsys):
    from citememo import memo as memo_mod

    monkeypatch.delenv("CITEMEMO_QUIET", raising=False)
    filename = "Jane Q. Litigant - motion to dismiss (SSN 123-45-6789).pdf"
    text = "Jane Q. Litigant asks the court to rely on Air France v. Saks, 470 U.S. 392 (1985)."
    memo_mod.run_memo(text=text, filename=filename)
    lines = [ln for ln in capsys.readouterr().out.splitlines() if ln.startswith("{")]
    assert len(lines) == 1
    raw = lines[0]
    rec = json.loads(raw)
    assert rec["event"] == "memo"
    assert "Litigant" not in raw and "123-45-6789" not in raw and "Air France" not in raw
    assert filename not in raw
    assert len(rec["sha256"]) == 64
    assert len(rec["filename_sha256"]) == 64


# --------------------------------------------------------------------------- #
# Wording: "fabricated" only as the class key (DECISION-RULE §6.3, UI-SPEC §9)
# --------------------------------------------------------------------------- #


def _string_constants(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = getattr(node, "body", [])
            if body and isinstance(body[0], ast.Expr) and isinstance(getattr(body[0], "value", None), ast.Constant):
                docstrings.add(id(body[0].value))
    return [n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docstrings]


def test_wording_fabricated_only_as_a_class_key(offline_env):
    files = sorted((ROOT / "citememo").glob("*.py")) + [ROOT / "main.py"]
    bad = []
    for f in files:
        for s in _string_constants(f):
            if "fabricat" in s.lower():
                rest = s.replace("likely_fabricated", "").replace("real_cases_marked_fabricated", "")
                if "fabricat" in rest.lower():
                    bad.append((f.name, s[:120]))
    assert bad == []
    from citememo import memo as memo_mod
    from citememo.models import LABELS

    assert LABELS["likely_fabricated"] == "Likely not a real case."
    memo = memo_mod.run_memo(text=SAMPLE_TXT.read_text(), filename="sample-motion.txt")
    for r in memo.results:
        assert "fabricat" not in (r.label + " " + " ".join(r.reasons)).lower(), r.row
    assert "fabricat" not in (memo.read_these_first or "").lower()


@pytest.mark.parametrize(
    "rel,body",
    [
        ("f3d/174/CasesMetadata.json", '{"weird": 1}'),
        ("f3d/174/CasesMetadata.json", '[{"weird": 1}, 5, "x", null]'),
        ("f3d/VolumesMetadata.json", '{"weird": 1}'),
        ("f3d/VolumesMetadata.json", '[{"weird": 1}]'),
    ],
)
def test_malformed_cap_json_shape_is_not_checked_and_never_cached(tmp_path, monkeypatch, rel, body):
    """Valid JSON of the wrong shape is an unreadable reply (§6.1 → not_checked), not "not in the free library", and is not cached."""
    monkeypatch.delenv("CITEMEMO_OFFLINE", raising=False)
    from citememo import memo as memo_mod
    from citememo.cache import DiskCache
    from citememo.cap import CapClient

    def override(r):
        if r == rel:
            return httpx.Response(200, text=body, headers={"content-type": "application/json"})
        return None

    cache = DiskCache(write_dir=tmp_path / "cap", read_dirs=[tmp_path / "cap"])
    cap = CapClient(cache=cache, transport=httpx.MockTransport(_seed_handler(override)), offline=False, retries=0)
    memo = memo_mod.run_memo(text="Greenleaf v. Garlock, Inc., 174 F.3d 352 (3d Cir. 1999).", filename="pasted-text", cap=cap)
    row = memo.results[0]
    assert row.class_ == "not_checked", row.reasons
    assert "unreadable reply" in row.reasons[0]
    assert "None" not in row.reasons[0]
    assert not (tmp_path / "cap" / rel).exists()
