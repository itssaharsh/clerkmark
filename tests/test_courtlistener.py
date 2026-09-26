"""Tests for citememo.courtlistener (optional second source, AC-15).

No live call is ever made: the network is an httpx.MockTransport. Without
COURTLISTENER_TOKEN the client reports configured=False and never touches the
network. With a token, lookup(text) POSTs the v4 citation-lookup endpoint with
"Authorization: Token …" and maps the per-citation statuses.
"""

from __future__ import annotations

import json
from urllib.parse import parse_qs

import httpx
import pytest

from citememo.courtlistener import (
    CL_LOOKUP_URL,
    MAX_CHARS,
    MAX_CITATIONS,
    STATUS_MAP,
    USER_AGENT,
    CitationLookup,
    CourtListenerClient,
    CourtListenerResult,
)

TOKEN = "s3cr3t-token-value"

FOUND = {
    "citation": "516 U.S. 217",
    "normalized_citations": ["516 U.S. 217"],
    "start_index": 0,
    "end_index": 12,
    "status": 200,
    "error_message": "",
    "clusters": [
        {
            "id": 117991,
            "case_name": "Zicherman v. Korean Air Lines Co.",
            "absolute_url": "/opinion/117991/zicherman-v-korean-air-lines-co/",
            "date_filed": "1996-01-16",
            "citations": [{"volume": 516, "reporter": "U.S.", "page": "217", "type": 1}],
        }
    ],
}
AMBIGUOUS = {"citation": "1 U.S. 1", "normalized_citations": ["1 U.S. 1"], "start_index": 14, "end_index": 22, "status": 300, "error_message": "Multiple citations found", "clusters": [{"id": 1}, {"id": 2}]}
NOT_FOUND = {"citation": "600 U.S. 477", "normalized_citations": ["600 U.S. 477"], "start_index": 24, "end_index": 36, "status": 404, "error_message": "Citation not found: '600 U.S. 477'", "clusters": []}
INVALID = {"citation": "88 Fed. Air Rptr. 3d 412", "normalized_citations": [], "start_index": 38, "end_index": 62, "status": 400, "error_message": "Invalid citation or reporter", "clusters": []}
THROTTLED = {"citation": "925 F.3d 1339", "normalized_citations": ["925 F.3d 1339"], "start_index": 64, "end_index": 77, "status": 429, "error_message": "Too many requests", "clusters": []}


@pytest.fixture
def cache_env(monkeypatch, tmp_path):
    monkeypatch.setenv("CITEMEMO_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.delenv("CITEMEMO_OFFLINE", raising=False)
    return tmp_path / "cache"


def make(handler, token=TOKEN, **kw):
    return CourtListenerClient(token=token, transport=httpx.MockTransport(handler), **kw)


def test_constants():
    assert CL_LOOKUP_URL == "https://www.courtlistener.com/api/rest/v4/citation-lookup/"
    assert USER_AGENT == "cite-intake-memo/0.1"
    assert MAX_CITATIONS == 250
    assert MAX_CHARS == 64000
    assert STATUS_MAP == {200: "found", 300: "ambiguous", 404: "not_found", 400: "invalid_reporter", 429: "throttled"}


# --------------------------------------------------------------------------- #
# Not configured: no network, configured=False
# --------------------------------------------------------------------------- #


def test_unset_token_means_not_configured_and_no_call(monkeypatch, cache_env):
    monkeypatch.delenv("COURTLISTENER_TOKEN", raising=False)

    def handler(request):
        raise AssertionError(f"CourtListener called without a token: {request.url}")

    c = CourtListenerClient(transport=httpx.MockTransport(handler))
    assert c.configured is False
    res = c.lookup("516 U.S. 217")
    assert isinstance(res, CourtListenerResult)
    assert res.status == "not_configured"
    assert res.ok is False
    assert res.entries == []
    assert res.by_citation("516 U.S. 217") is None


def test_empty_token_is_not_configured(monkeypatch, cache_env):
    monkeypatch.setenv("COURTLISTENER_TOKEN", "   ")
    assert CourtListenerClient().configured is False
    assert CourtListenerClient(token="").configured is False


def test_token_from_env(monkeypatch, cache_env):
    monkeypatch.setenv("COURTLISTENER_TOKEN", TOKEN)
    c = CourtListenerClient()
    assert c.configured is True
    assert TOKEN not in repr(c)
    assert TOKEN not in str(c)


# --------------------------------------------------------------------------- #
# Configured: POST with the token header, statuses mapped
# --------------------------------------------------------------------------- #


def test_lookup_posts_and_maps_statuses(cache_env):
    seen = {}

    def handler(request):
        seen["method"] = request.method
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("authorization")
        seen["ua"] = request.headers.get("user-agent")
        seen["ctype"] = request.headers.get("content-type")
        seen["form"] = parse_qs(request.content.decode())
        return httpx.Response(200, json=[FOUND, AMBIGUOUS, NOT_FOUND, INVALID, THROTTLED], request=request)

    c = make(handler)
    text = "516 U.S. 217, 1 U.S. 1, 600 U.S. 477, 88 Fed. Air Rptr. 3d 412, 925 F.3d 1339"
    res = c.lookup(text)
    assert seen["method"] == "POST"
    assert seen["url"] == CL_LOOKUP_URL
    assert seen["auth"] == f"Token {TOKEN}"
    assert seen["ua"] == USER_AGENT
    assert seen["ctype"].startswith("application/x-www-form-urlencoded")
    assert seen["form"] == {"text": [text]}

    assert res.status == "ok" and res.ok is True
    assert [e.status for e in res.entries] == ["found", "ambiguous", "not_found", "invalid_reporter", "throttled"]
    assert [e.http_status for e in res.entries] == [200, 300, 404, 400, 429]
    assert res.throttled is True  # a 429 appeared among the rows

    z = res.by_citation("516 U.S. 217")
    assert isinstance(z, CitationLookup)
    assert z.found is True
    assert z.case_name == "Zicherman v. Korean Air Lines Co."
    assert z.date_filed == "1996-01-16"
    assert z.url == "https://www.courtlistener.com/opinion/117991/zicherman-v-korean-air-lines-co/"
    assert z.cluster_ids == [117991]
    assert (z.start_index, z.end_index) == (0, 12)

    nf = res.by_citation("600 U.S. 477")
    assert nf.found is False and nf.status == "not_found"
    assert nf.error_message.startswith("Citation not found")
    assert res.by_citation("1 U.S. 1").cluster_ids == [1, 2]
    assert res.by_citation("88 Fed. Air Rptr. 3d 412").normalized_citations == []
    assert res.by_citation("nope") is None
    assert res.found_citations() == ["516 U.S. 217"]


def test_unknown_per_citation_status_maps_to_other(cache_env):
    def handler(request):
        return httpx.Response(200, json=[dict(FOUND, status=418)], request=request)

    res = make(handler).lookup("516 U.S. 217")
    assert res.entries[0].status == "other"
    assert res.entries[0].found is False


@pytest.mark.parametrize(
    "http_status, expected",
    [(401, "unauthorized"), (403, "unauthorized"), (429, "throttled"), (500, "unavailable"), (503, "unavailable")],
)
def test_whole_response_errors_never_raise(cache_env, http_status, expected):
    def handler(request):
        return httpx.Response(http_status, json={"detail": "nope"}, request=request)

    res = make(handler).lookup("516 U.S. 217")
    assert res.ok is False
    assert res.status == expected
    assert res.entries == []
    assert str(http_status) in res.reason
    assert res.throttled is (http_status == 429)


def test_timeout_and_connection_errors_are_unavailable(cache_env):
    calls = []

    def slow(request):
        calls.append(1)
        raise httpx.ReadTimeout("slow", request=request)

    res = make(slow).lookup("516 U.S. 217")
    assert res.status == "unavailable" and "timeout" in res.reason
    assert len(calls) == 1  # CourtListener is optional: no retry burns quota

    def refused(request):
        raise httpx.ConnectError("refused", request=request)

    assert make(refused).lookup("516 U.S. 217").status == "unavailable"


def test_non_json_body_is_unavailable(cache_env):
    def handler(request):
        return httpx.Response(200, text="<html>maintenance</html>", request=request)

    res = make(handler).lookup("516 U.S. 217")
    assert res.status == "unavailable" and "json" in res.reason.lower()


def test_empty_text_makes_no_call(cache_env):
    def handler(request):
        raise AssertionError("called")

    res = make(handler).lookup("   ")
    assert res.ok is True and res.entries == []


# --------------------------------------------------------------------------- #
# Caching: every response cached (BUILD-NOTES §1); offline mode makes no call
# --------------------------------------------------------------------------- #


def test_responses_are_cached_on_disk_and_in_memory(cache_env):
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(200, json=[FOUND], request=request)

    c = make(handler)
    assert c.lookup("516 U.S. 217").ok
    assert c.lookup("516 U.S. 217").ok
    assert len(calls) == 1
    files = list((cache_env / "courtlistener").glob("*.json"))
    assert len(files) == 1
    assert json.loads(files[0].read_text())[0]["citation"] == "516 U.S. 217"
    # a second client (fresh memory) reads the disk cache
    c2 = make(handler)
    assert c2.lookup("516 U.S. 217").by_citation("516 U.S. 217").found
    assert len(calls) == 1
    # error responses are not cached
    def bad(request):
        calls.append(1)
        return httpx.Response(503, text="x", request=request)

    c3 = make(bad)
    assert c3.lookup("other text").status == "unavailable"
    assert c3.lookup("other text").status == "unavailable"
    assert len(calls) == 3


def test_offline_mode_uses_cache_only(monkeypatch, cache_env):
    def handler(request):
        return httpx.Response(200, json=[FOUND], request=request)

    make(handler).lookup("516 U.S. 217")  # warms the disk cache
    monkeypatch.setenv("CITEMEMO_OFFLINE", "1")

    def never(request):
        raise AssertionError("network in offline mode")

    c = make(never)
    assert c.configured is True
    assert c.lookup("516 U.S. 217").by_citation("516 U.S. 217").found
    miss = c.lookup("600 U.S. 477")
    assert miss.ok is False and miss.status == "unavailable" and "offline" in miss.reason


# --------------------------------------------------------------------------- #
# lookup_citations: chunked at 250 per request, stop on the first 429
# --------------------------------------------------------------------------- #


def test_lookup_citations_chunks_and_maps(cache_env):
    bodies = []

    def handler(request):
        text = parse_qs(request.content.decode())["text"][0]
        bodies.append(text)
        rows = []
        for line in text.split("\n"):
            rows.append(dict(FOUND, citation=line, normalized_citations=[line]))
        return httpx.Response(200, json=rows, request=request)

    cites = [f"{v} U.S. 1" for v in range(1, 302)]  # 301 citations → 2 requests
    out = make(handler).lookup_citations(cites)
    assert len(bodies) == 2
    assert len(bodies[0].split("\n")) == MAX_CITATIONS
    assert set(out) == set(cites)
    assert out["1 U.S. 1"].found and out["301 U.S. 1"].found


def test_lookup_citations_stops_on_throttle(cache_env):
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(429, json={"detail": "throttled"}, request=request)

    cites = [f"{v} U.S. 1" for v in range(1, 502)]  # would be 3 requests
    c = make(handler)
    out = c.lookup_citations(cites)
    assert len(calls) == 1
    assert all(v.status == "throttled" for v in out.values())
    assert len(out) == 501
    assert c.last_result.throttled is True


def test_lookup_citations_dedupes_and_skips_when_not_configured(monkeypatch, cache_env):
    monkeypatch.delenv("COURTLISTENER_TOKEN", raising=False)
    c = CourtListenerClient(transport=httpx.MockTransport(lambda r: (_ for _ in ()).throw(AssertionError())))
    assert c.lookup_citations(["1 U.S. 1", "1 U.S. 1"]) == {}
