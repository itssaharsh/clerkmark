"""T05 integration: the orchestrator (memo.py), the eval (evaluate.py) and the API (main.py).

Everything runs from the committed ``seed/cache/cap`` (no network): the sample memo,
the 20-item eval, the error envelopes, and the AC-6 per-volume degrade (a mock CAP
transport that fails for one volume). ``-k eval`` is AC-1, ``-k no_text`` AC-5,
``-k unreachable`` AC-6, ``-k offline`` AC-7, ``-k eval_route`` AC-11.
"""

from __future__ import annotations

import io
import json
import time
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
SEED_CACHE = ROOT / "seed" / "cache" / "cap"
SAMPLE_PDF = ROOT / "seed" / "sample-motion.pdf"
SAMPLE_TXT = ROOT / "seed" / "sample-motion.txt"
GROUND_TRUTH = json.loads((ROOT / "seed" / "ground_truth.json").read_text())


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #


@pytest.fixture(scope="module")
def offline_env():
    import os

    old = os.environ.get("CITEMEMO_OFFLINE")
    os.environ["CITEMEMO_OFFLINE"] = "1"
    os.environ.pop("ANTHROPIC_API_KEY", None)
    os.environ.pop("COURTLISTENER_TOKEN", None)
    yield
    if old is None:
        os.environ.pop("CITEMEMO_OFFLINE", None)
    else:
        os.environ["CITEMEMO_OFFLINE"] = old


@pytest.fixture(scope="module")
def client(offline_env):
    import main

    with TestClient(main.app) as c:
        yield c


@pytest.fixture(scope="module")
def sample_memo(client):
    t0 = time.perf_counter()
    r = client.post("/api/memo/sample/sample-motion")
    wall = time.perf_counter() - t0
    assert r.status_code == 200, r.text
    body = r.json()
    body["_wall_s"] = wall
    return body


def blank_pdf_bytes() -> bytes:
    """A one-page PDF with no text layer (a 'scan' without OCR)."""
    from fpdf import FPDF

    pdf = FPDF()
    pdf.add_page()
    pdf.set_fill_color(200, 200, 200)
    pdf.rect(20, 20, 100, 100, style="F")
    out = pdf.output()
    return bytes(out)


# --------------------------------------------------------------------------- #
# Health, samples, root, static
# --------------------------------------------------------------------------- #


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    h = r.json()
    assert h["ok"] is True
    assert h["version"] == "0.1.0"
    assert h["offline"] is True
    assert h["courtlistener"] is False
    assert h["advisory"] is False
    assert isinstance(h["replay_available"], bool)
    assert h["cache_dir"]


def test_samples(client):
    r = client.get("/api/samples")
    assert r.status_code == 200
    samples = r.json()
    assert len(samples) == 1
    s = samples[0]
    assert s["id"] == "sample-motion"
    assert s["filename"] == "sample-motion.pdf"
    assert s["pages"] == 6
    assert s["scored"] == 20
    assert s["citations"] == 23
    assert s["synthetic"] is True
    assert "Synthetic" in s["label"] or "SYNTHETIC" in s["label"]


def test_root_and_web_assets(client):
    r = client.get("/favicon.svg")
    assert r.status_code == 200
    assert "svg" in r.headers["content-type"]
    r = client.get("/tokens.css")
    assert r.status_code == 200
    assert "css" in r.headers["content-type"]
    r = client.get("/wordmark.svg")
    assert r.status_code == 200
    r = client.get("/static/fixture-memo.json")
    assert r.status_code == 200
    assert r.json()["fixture"] is True
    r = client.get("/?demo=1")
    if (ROOT / "web" / "index.html").exists():
        assert r.status_code == 200
        assert "text/html" in r.headers["content-type"]
    else:  # T06 has not landed the page yet: an envelope, never a bare 404
        assert r.status_code == 404
        assert r.json()["error"]["code"] == "not_found"


def test_unknown_sample_is_not_found_envelope(client):
    r = client.post("/api/memo/sample/nope")
    assert r.status_code == 404
    body = r.json()
    assert body["error"]["code"] == "not_found"
    assert "nope" in body["error"]["message"]


# --------------------------------------------------------------------------- #
# AC-7: the sample from cache, offline, quickly
# --------------------------------------------------------------------------- #


def test_sample_offline_runs_from_cache_in_time(sample_memo):
    memo = sample_memo
    assert memo["_wall_s"] <= 5.0, f"offline sample took {memo['_wall_s']:.2f} s"
    assert memo["offline"] is True
    assert memo["replay"] is False
    assert memo["fixture"] is False
    assert memo["sample_id"] == "sample-motion"
    assert memo["filing"]["filename"] == "sample-motion.pdf"
    assert memo["filing"]["pages"] == 6
    assert memo["filing"]["label"]
    assert memo["filing"]["bytes"] == SAMPLE_PDF.stat().st_size
    assert memo["sources_used"] == {"cap": True, "courtlistener": False, "advisory": False}
    assert memo["elapsed_ms"] > 0
    st = memo["stage_timings_ms"]
    assert st["extract"] > 0 and st["lookup"] >= 0 and st["classify"] >= 0 and st["quotes"] >= 0
    assert st["advisory"] is None
    assert memo["run_id"]
    assert memo["created_at"]


def test_sample_rows_are_in_filing_order_and_complete(sample_memo):
    rows = sample_memo["results"]
    assert [r["row"] for r in rows] == list(range(1, len(rows) + 1))
    assert sample_memo["counts"]["total"] == 23
    by_text = {r["cite_text"]: r for r in rows}
    # every scored ground-truth item is a row, matched by cite_text
    for item in GROUND_TRUTH["items"]:
        assert item["cite_text"] in by_text, item["id"]
    # the page-1 label cite and the two skipped cites are rows too
    assert GROUND_TRUTH["extra_in_label"]["cite_text"] in by_text
    assert sample_memo["counts"]["skipped"] == 2
    assert any(r["class"] == "skipped" and r["citation"]["kind"] == "id" for r in rows)
    assert any(r["class"] == "skipped" and r["citation"]["kind"] == "statute" for r in rows)
    # every row carries the derived display fields
    for r in rows:
        assert r["label"]
        assert r["reasons"], r["cite_text"]
        assert r["mark"] and r["register"]
        assert r["citation"]["text"]


def test_sample_demo_rows(sample_memo):
    rows = {r["cite_text"]: r for r in sample_memo["results"]}
    miller = rows["Miller v. United Airlines, Inc., 174 F.3d 366 (2d Cir. 1999)"]
    assert miller["class"] == "likely_fabricated"
    assert miller["label"] == "Likely not a real case."
    assert miller["mark"] == "circle-all" and miller["register"] == "red"
    assert miller["evidence"]["real_case_at_page"]["name"] == "Greenleaf v. Garlock, Inc."
    assert miller["evidence"]["running_head"].startswith("174 F.3d 352 · GREENLEAF v. GARLOCK, INC.")
    assert miller["evidence"]["running_head"].endswith("begins at 352")
    assert miller["evidence"]["page_marker"] == "366"
    assert miller["drawer"] == "page"

    shaboon = rows["Shaboon v. Egyptair, 2013 IL App (1st) 111279"]
    assert shaboon["class"] == "not_in_free_corpus"
    assert shaboon["label"] == "Not in the free library. Check Westlaw or Lexis."
    assert shaboon["mark"] == "underline-pencil"

    varghese = rows["Varghese v. China Southern Airlines Co., 925 F.3d 1339 (11th Cir. 2019)"]
    assert varghese["class"] == "likely_fabricated"
    assert varghese["evidence"]["real_case_at_page"]["name"] == "J.D. v. Azar"
    assert varghese["evidence"]["running_head"].startswith("925 F.3d 1291 · J.D. v. AZAR")
    assert varghese["evidence"]["page_marker"] == "1339"
    assert varghese["evidence"]["links"][:2] == [
        "https://static.case.law/f3d/VolumesMetadata.json",
        "https://static.case.law/f3d/925/CasesMetadata.json",
    ]

    azar = rows["J.D. v. Azar, 925 F.3d 1291 (D.C. Cir. 2019)"]
    assert azar["class"] == "verified"
    assert azar["label"] == "Found. Quote matches."
    assert azar["quote_check"]["status"] == "verbatim"
    assert azar["evidence"]["excerpt"] and "Rule 23 class" in azar["evidence"]["excerpt"]
    assert azar["evidence"]["excerpt_highlight"] is not None
    assert azar["evidence"]["closest_passage"]["status"] == "verbatim"
    assert azar["evidence"]["links"][-1] == "https://static.case.law/f3d/925/cases/1291-01.json"
    assert azar["source"] == "CAP"

    iqbal = rows["Ashcroft v. Iqbal, 556 U.S. 662 (2009)"]
    assert iqbal["class"] == "quote_not_found"
    assert iqbal["quote_check"]["status"] in ("differs", "not_found")
    assert iqbal["evidence"]["closest_passage"]["text"]
    assert 70 <= iqbal["quote_check"]["similarity"] <= 95

    chan = rows["Chan v. Korean Air Lines, Ltd., 490 U.S. 122 (1989)"]
    assert chan["class"] == "quote_not_found"

    z230 = rows["Zicherman v. Korean Air Lines Co., 516 U.S. 230 (1996)"]
    assert z230["class"] == "wrong_cite_exists"
    assert z230["mark"] == "strike-correct"

    alvarez = rows["Alvarez v. Skyline Cargo, 88 Fed. Air Rptr. 3d 412 (2018)"]
    assert alvarez["class"] == "unrecognized_reporter"
    assert alvarez["drawer"] is None

    biden = rows["Biden v. Nebraska, 600 U.S. 477 (2023)"]
    assert biden["class"] == "not_in_free_corpus"
    assert biden["evidence"]["volume_range"]["vmax"] == 572
    assert biden["drawer"] == "shelf"

    c = sample_memo["counts"]
    assert c["likely_fabricated"] == 3
    assert c["quote_not_found"] == 2
    assert c["wrong_cite_exists"] == 1
    assert c["unrecognized_reporter"] == 1
    assert c["verified"] == 8
    assert c["not_checked"] == 0
    assert sample_memo["read_these_first"].startswith("Read these first: 3 likely not real cases, 1 no reporter by this name, 2 quotes not in the opinion, 1 exists at another page. Then: 8 found;")
    assert sample_memo["read_these_first"].endswith("Of 23 citations.")


def test_no_real_case_is_red_on_the_sample(sample_memo):
    rows = {r["cite_text"]: r for r in sample_memo["results"]}
    for item in GROUND_TRUTH["items"]:
        if item["expected_class"] != "likely_fabricated":
            assert rows[item["cite_text"]]["class"] != "likely_fabricated", item["id"]


# --------------------------------------------------------------------------- #
# AC-1 / AC-11: the eval
# --------------------------------------------------------------------------- #


def test_eval_route_reports_ground_truth(client):
    r = client.get("/api/eval")
    assert r.status_code == 200, r.text
    rep = r.json()
    assert rep["total"] == 20
    assert rep["correct"] >= 18
    assert rep["real_cases_marked_fabricated"] == 0
    assert rep["real_total"] >= 10
    assert abs(rep["accuracy"] - rep["correct"] / 20) < 1e-9
    assert set(rep["per_class"]) == {"expected", "predicted"}
    assert sum(rep["per_class"]["expected"].values()) == 20
    assert sum(rep["per_class"]["predicted"].values()) == 20
    assert rep["elapsed_ms"] > 0
    assert rep["offline"] is True
    assert rep["run_id"] and rep["run_created_at"] and rep["generated_at"]
    ids = {row["id"] for row in rep["rows"]}
    assert ids == {i["id"] for i in GROUND_TRUTH["items"]}
    for row in rep["rows"]:
        assert row["line"] is not None, row["id"]
        assert row["predicted"] is not None, row["id"]
        assert row["ok"] == (row["predicted"] in row["accepted"])
        assert row["reason"]
    # the label cite is not scored
    assert GROUND_TRUTH["extra_in_label"]["cite_text"] not in {row["cite_text"] for row in rep["rows"]}


def test_eval_rerun_is_fresh(client):
    r1 = client.get("/api/eval").json()
    r2 = client.get("/api/eval?rerun=1").json()
    assert r2["run_id"] != r1["run_id"]
    assert r2["correct"] == r1["correct"]


def test_eval_module_scores_by_accepted_classes():
    from citememo import evaluate
    from citememo.models import CitationResult, Filing, Memo

    gt = json.loads((ROOT / "seed" / "ground_truth.json").read_text())
    rows = []
    for i, item in enumerate(gt["items"], start=1):
        pred = item["accepted_classes"][-1]  # the alternative accepted class counts as correct
        rows.append(CitationResult(row=i, cite_text=item["cite_text"], class_=pred, reasons=["x"]))
    memo = Memo(run_id="t", filing=Filing(filename="x", pages=1, words=1), results=rows, elapsed_ms=1.0)
    rep = evaluate.evaluate(memo, gt)
    assert rep.total == 20 and rep.correct == 20 and rep.accuracy == 1.0
    assert rep.real_cases_marked_fabricated == 0
    # a real case predicted likely_fabricated is counted, and is wrong
    bad = [r.model_copy(update={"class_": "likely_fabricated"}) if r.cite_text.startswith("J.D. v. Azar") else r for r in rows]
    rep2 = evaluate.evaluate(memo.model_copy(update={"results": bad}), gt)
    assert rep2.real_cases_marked_fabricated == 1
    assert rep2.correct == 19
    # a missing row scores as wrong with predicted None
    rep3 = evaluate.evaluate(memo.model_copy(update={"results": rows[:-1]}), gt)
    assert rep3.correct == 19
    missing = [r for r in rep3.rows if r.predicted is None]
    assert len(missing) == 1 and missing[0].line is None and missing[0].ok is False


# --------------------------------------------------------------------------- #
# AC-5 wiring: error envelopes
# --------------------------------------------------------------------------- #


def test_no_text_layer_envelope(client):
    data = blank_pdf_bytes()
    assert data.startswith(b"%PDF-")
    r = client.post("/api/memo", files={"file": ("scan.pdf", io.BytesIO(data), "application/pdf")})
    assert r.status_code == 422, r.text
    body = r.json()
    assert body["error"]["code"] == "no_text_layer"
    assert body["error"]["message"].startswith("No text layer in this PDF.")
    assert body["error"]["hint"]


def test_unsupported_type_envelope(client):
    r = client.post("/api/memo", files={"file": ("notes.txt", io.BytesIO(b"hello there, 470 U.S. 392"), "text/plain")})
    assert r.status_code == 415
    body = r.json()
    assert body["error"]["code"] == "unsupported_type"
    assert body["error"]["message"] == "This file is not a PDF."


def test_empty_envelope(client):
    r = client.post("/api/memo")
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "empty"
    r = client.post("/api/memo", data={"text": "   \n"})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "empty"


def test_text_without_citations_is_not_an_error(client):
    r = client.post("/api/memo", data={"text": "Nothing to see here. Just prose about a flight and a cart."})
    assert r.status_code == 200
    memo = r.json()
    assert memo["results"] == []
    assert memo["counts"]["total"] == 0
    assert memo["read_these_first"] == "Nothing to read first: 0 found. Of 0 citations."
    assert memo["filing"]["filename"] == "pasted-text"
    assert memo["filing"]["label"] is None


def test_text_input_runs_the_pipeline(client):
    text = (
        'The Court said: "Any injury is the product of a chain of causes, and we require only that the '
        'passenger be able to prove that some link in the chain was an unusual or unexpected event external '
        'to the passenger." Air France v. Saks, 470 U.S. 392 (1985). See also Id. at 400.'
    )
    r = client.post("/api/memo", data={"text": text})
    assert r.status_code == 200, r.text
    memo = r.json()
    assert memo["counts"]["total"] == 2
    saks = memo["results"][0]
    assert saks["class"] == "verified"
    assert saks["quote_check"]["status"] == "verbatim"
    assert memo["results"][1]["class"] == "skipped"
    assert memo["filing"]["pages"] == 1
    assert memo["filing"]["words"] > 10


def test_pdf_upload_runs_the_sample_pipeline(client):
    r = client.post("/api/memo", files={"file": ("sample-motion.pdf", io.BytesIO(SAMPLE_PDF.read_bytes()), "application/pdf")})
    assert r.status_code == 200, r.text
    memo = r.json()
    assert memo["filing"]["filename"] == "sample-motion.pdf"
    assert memo["filing"]["label"] is None
    assert memo["sample_id"] is None
    assert memo["counts"]["total"] == 23
    assert memo["counts"]["likely_fabricated"] == 3


# --------------------------------------------------------------------------- #
# Replay
# --------------------------------------------------------------------------- #


def test_replay_route(client):
    r = client.get("/api/replay")
    if (ROOT / "seed" / "replay.json").exists():
        assert r.status_code == 200
        memo = r.json()
        assert memo["replay"] is True
        assert memo["created_at"]
        assert memo["counts"]["total"] >= 20
    else:
        assert r.status_code == 404
        body = r.json()
        assert body["error"]["code"] == "not_found"
        assert body["error"]["hint"] == "Run scripts/record_replay.py."


# --------------------------------------------------------------------------- #
# Orchestrator pieces: parallel groups, subsequent history, duplicates
# --------------------------------------------------------------------------- #


def test_parallel_cites_collapse_into_one_row(offline_env):
    from citememo import memo as memo_mod

    text = (
        "As held in Zicherman v. Korean Air Lines Co., 516 U.S. 217, 116 S. Ct. 629 (1996), the treaty is a pass-through. "
        "See Smith v. Jones, 100 F.3d 1 (2d Cir. 1996), cert. denied, 520 U.S. 1000 (1997)."
    )
    memo = memo_mod.run_memo(text=text, filename="pasted-text")
    assert memo.counts.total == 3
    zich = memo.results[0]
    assert zich.class_ == "verified"
    assert zich.cite_text.startswith("Zicherman v. Korean Air Lines Co., 516 U.S. 217")
    assert any("116 S. Ct. 629" in p and "confirmed by the CAP record" in p for p in zich.parallel_cites)
    smith = memo.results[1]
    assert smith.citation.text == "100 F.3d 1"
    cert = memo.results[2]
    assert cert.class_ == "skipped"
    assert "cert. denied" in cert.reasons[0].lower() or "subsequent-history" in cert.reasons[0].lower()


def test_run_limit_marks_later_volumes_not_checked(offline_env, monkeypatch):
    from citememo import memo as memo_mod

    monkeypatch.setattr(memo_mod, "MAX_VOLUMES", 2)
    text = " ".join(f"A v. B, {v} U.S. 100 (1990)." for v in (470, 490, 499, 516))
    memo = memo_mod.run_memo(text=text, filename="pasted-text")
    classes = [r.class_ for r in memo.results]
    assert classes[2:] == ["not_checked", "not_checked"]
    assert "run limit" in memo.results[2].reasons[0]


# --------------------------------------------------------------------------- #
# AC-6: a volume the corpus does not answer for
# --------------------------------------------------------------------------- #


def _seed_transport(fail_rel: str, status: int = 503) -> httpx.MockTransport:
    """Serve the committed seed cache over a mock CAP; ``fail_rel`` answers ``status``."""

    def handler(request: httpx.Request) -> httpx.Response:
        rel = request.url.path.lstrip("/")
        if rel == fail_rel:
            return httpx.Response(status, text="upstream error")
        p = SEED_CACHE / rel
        if p.exists():
            return httpx.Response(200, content=p.read_bytes(), headers={"content-type": "application/json"})
        return httpx.Response(404, text="<html>not found</html>")

    return httpx.MockTransport(handler)


def test_unreachable_volume_degrades_only_its_rows(tmp_path, monkeypatch):
    monkeypatch.delenv("CITEMEMO_OFFLINE", raising=False)
    from citememo import memo as memo_mod
    from citememo.cache import DiskCache
    from citememo.cap import CapClient

    cache = DiskCache(write_dir=tmp_path / "cap", read_dirs=[tmp_path / "cap"])
    cap = CapClient(cache=cache, transport=_seed_transport("f3d/174/CasesMetadata.json"), offline=False, retries=0)
    memo = memo_mod.run_memo(text=SAMPLE_TXT.read_text(), filename="sample-motion.txt", cap=cap)
    rows = {r.cite_text: r for r in memo.results}
    miller = rows["Miller v. United Airlines, Inc., 174 F.3d 366 (2d Cir. 1999)"]
    greenleaf = rows["Greenleaf v. Garlock, Inc., 174 F.3d 352 (3d Cir. 1999)"]
    for r in (miller, greenleaf):
        assert r.class_ == "not_checked", r.reasons
        assert r.label == "Could not reach the free library."
        assert r.register_ == "coverage"
        assert "174 F.3d" in r.reasons[0]
    # other volumes still answer: Varghese stays red, Azar stays green with its quote
    assert rows["Varghese v. China Southern Airlines Co., 925 F.3d 1339 (11th Cir. 2019)"].class_ == "likely_fabricated"
    assert rows["J.D. v. Azar, 925 F.3d 1291 (D.C. Cir. 2019)"].class_ == "verified"
    assert memo.counts.not_checked == 2
    assert memo.read_these_first.endswith("2 not answered yet.")
    assert any("did not answer" in w for w in memo.warnings)
    assert memo.offline is False


def test_unreachable_volume_index_degrades_the_reporter(tmp_path, monkeypatch):
    monkeypatch.delenv("CITEMEMO_OFFLINE", raising=False)
    from citememo import memo as memo_mod
    from citememo.cache import DiskCache
    from citememo.cap import CapClient

    cache = DiskCache(write_dir=tmp_path / "cap", read_dirs=[tmp_path / "cap"])
    cap = CapClient(cache=cache, transport=_seed_transport("us/VolumesMetadata.json"), offline=False, retries=0)
    text = "Air France v. Saks, 470 U.S. 392 (1985). Greenleaf v. Garlock, Inc., 174 F.3d 352 (3d Cir. 1999)."
    memo = memo_mod.run_memo(text=text, filename="pasted-text", cap=cap)
    assert memo.results[0].class_ == "not_checked"
    assert memo.results[1].class_ == "verified"
    assert memo.counts.not_checked == 1


def test_offline_miss_is_not_checked_not_red(tmp_path):
    """Offline with an empty cache: nothing can be checked; nothing is ever red."""
    from citememo import memo as memo_mod
    from citememo.cache import DiskCache
    from citememo.cap import CapClient

    cache = DiskCache(write_dir=tmp_path / "cap", read_dirs=[tmp_path / "cap"])
    cap = CapClient(cache=cache, offline=True)
    memo = memo_mod.run_memo(text="Varghese v. China Southern Airlines Co., 925 F.3d 1339 (11th Cir. 2019).", filename="pasted-text", cap=cap)
    assert memo.results[0].class_ == "not_checked"
    assert memo.offline is True
