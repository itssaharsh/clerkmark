"""Tests for citememo.cap (CapClient) and citememo.cache (DiskCache).

Every test runs offline from the committed seed cache under seed/cache/cap,
with CITEMEMO_CACHE_DIR pointed at a temporary directory so nothing is ever
written into the repo. Network paths are exercised with httpx.MockTransport.
A single opt-in live test (CITEMEMO_LIVE=1) checks that a real fetch of an
uncached volume populates the cache.
"""

from __future__ import annotations

import asyncio
import json
import os
import stat
from pathlib import Path

import httpx
import pytest

from citememo import cache as cache_mod
from citememo.cache import ABSENT, MISSING, DiskCache, LRU, resolve_cache_dir
from citememo.cap import (
    CAP_BASE,
    CONCURRENCY,
    TIMEOUT_S,
    USER_AGENT,
    CapClient,
    CaseEntry,
    CorpusUnavailable,
    PageIndex,
    opinion_text,
    parse_pages,
    running_head,
    to_real_case,
)
from citememo.models import RealCase

REPO = Path(__file__).resolve().parents[1]
SEED = REPO / "seed" / "cache" / "cap"


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #


@pytest.fixture
def offline_env(monkeypatch, tmp_path):
    """Offline mode; writable cache in tmp; seed cache readable as fallback."""
    monkeypatch.setenv("CITEMEMO_OFFLINE", "1")
    monkeypatch.setenv("CITEMEMO_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.delenv("COURTLISTENER_TOKEN", raising=False)
    return tmp_path / "cache"


@pytest.fixture
def client(offline_env):
    return CapClient()


def _json_response(request: httpx.Request, data, status=200) -> httpx.Response:
    return httpx.Response(status, json=data, request=request)


def make_client(handler, tmp_path, monkeypatch, offline=False):
    """A CapClient whose network is the given httpx.MockTransport handler."""
    monkeypatch.setenv("CITEMEMO_CACHE_DIR", str(tmp_path / "cache"))
    if offline:
        monkeypatch.setenv("CITEMEMO_OFFLINE", "1")
    else:
        monkeypatch.delenv("CITEMEMO_OFFLINE", raising=False)
    return CapClient(transport=httpx.MockTransport(handler))


# --------------------------------------------------------------------------- #
# Constants the brief fixes
# --------------------------------------------------------------------------- #


def test_constants():
    assert CAP_BASE == "https://static.case.law"
    assert USER_AGENT == "cite-intake-memo/0.1"
    assert TIMEOUT_S == 20
    assert CONCURRENCY == 6


# --------------------------------------------------------------------------- #
# Cache directory resolution (BUILD-NOTES §6): env → seed if writable → /tmp
# --------------------------------------------------------------------------- #


def test_resolve_cache_dir_prefers_env(tmp_path):
    target = tmp_path / "custom"
    got = resolve_cache_dir(env={"CITEMEMO_CACHE_DIR": str(target)}, seed_dir=tmp_path / "seed")
    assert got == target
    assert target.is_dir()


def test_resolve_cache_dir_uses_seed_when_writable(tmp_path):
    seed = tmp_path / "seed"
    seed.mkdir()
    assert resolve_cache_dir(env={}, seed_dir=seed) == seed


def test_resolve_cache_dir_falls_back_to_tmp_when_seed_read_only(tmp_path):
    seed = tmp_path / "seed"
    seed.mkdir()
    seed.chmod(stat.S_IRUSR | stat.S_IXUSR)
    fallback = tmp_path / "fallback"
    try:
        if os.access(seed, os.W_OK):
            pytest.skip("filesystem ignores read-only mode (running as root?)")
        got = resolve_cache_dir(env={}, seed_dir=seed, tmp_dir=fallback)
    finally:
        seed.chmod(stat.S_IRWXU)
    assert got == fallback
    assert fallback.is_dir()


def test_default_seed_dir_is_the_committed_cache():
    assert cache_mod.SEED_CACHE_DIR == SEED
    assert cache_mod.TMP_CACHE_DIR == Path("/tmp/citememo-cache")


# --------------------------------------------------------------------------- #
# DiskCache: two levels (memory LRU over JSON files), seed as read fallback
# --------------------------------------------------------------------------- #


def test_lru_evicts_least_recently_used():
    lru = LRU(maxsize=2)
    lru.put("a", 1)
    lru.put("b", 2)
    assert lru.get("a") == 1  # touch a; b is now the oldest
    lru.put("c", 3)
    assert "b" not in lru
    assert "a" in lru and "c" in lru
    assert len(lru) == 2


def test_disk_cache_reads_seed_and_writes_only_to_write_dir(tmp_path):
    dc = DiskCache(write_dir=tmp_path / "w", read_dirs=[tmp_path / "w", SEED])
    vols = dc.get("us/VolumesMetadata.json")
    assert isinstance(vols, list) and len(vols) == 572
    assert dc.find("us/VolumesMetadata.json") == SEED / "us" / "VolumesMetadata.json"
    assert dc.get("nope/VolumesMetadata.json") is MISSING

    dc.put("f4th/VolumesMetadata.json", [{"volume_number": "1"}])
    written = tmp_path / "w" / "f4th" / "VolumesMetadata.json"
    assert written.is_file()
    assert json.loads(written.read_text())[0]["volume_number"] == "1"
    assert not (SEED / "f4th").exists()


def test_disk_cache_memory_layer_serves_after_file_removed(tmp_path):
    dc = DiskCache(write_dir=tmp_path / "w", read_dirs=[tmp_path / "w"])
    dc.put("x/VolumesMetadata.json", {"k": 1})
    (tmp_path / "w" / "x" / "VolumesMetadata.json").unlink()
    assert dc.get("x/VolumesMetadata.json") == {"k": 1}  # served from memory
    dc.clear_memory()
    assert dc.get("x/VolumesMetadata.json") is MISSING


def test_disk_cache_absent_marker(tmp_path):
    dc = DiskCache(write_dir=tmp_path / "w", read_dirs=[tmp_path / "w"])
    dc.put_absent("us/600/CasesMetadata.json")
    assert dc.get("us/600/CasesMetadata.json") is ABSENT
    # a marker never masquerades as the positive-result layout
    assert not (tmp_path / "w" / "us" / "600" / "CasesMetadata.json").exists()
    dc2 = DiskCache(write_dir=tmp_path / "w", read_dirs=[tmp_path / "w"])
    assert dc2.get("us/600/CasesMetadata.json") is ABSENT


# --------------------------------------------------------------------------- #
# reporter_slug — DECISION-RULE §1.3
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "short_name, slug",
    [
        ("F.3d", "f3d"),
        ("F. Supp. 2d", "f-supp-2d"),
        ("U.S.", "us"),
        ("Cal. Rptr. 3d", "cal-rptr-3d"),
        ("F.4th", None),
        ("So. 3d", "so3d"),
        ("F. App'x", "f-appx"),
        ("Mass. App. Div.", "mass-app-div"),
        ("Ct. Cl.", None),
        ("N.Y.S.3d", None),
        ("WL", None),
        ("", None),
    ],
)
def test_reporter_slug(client, short_name, slug):
    assert client.reporter_slug(short_name) == slug


def test_reporter_slug_never_slugifies_unknown(client):
    # slugifying would give "fake-rptr-3d"; the contract is None
    assert client.reporter_slug("Fake. Rptr. 3d") is None
    assert client.reporter_slug(None) is None


def test_reporters_and_years(client):
    reps = client.reporters()
    assert len(reps) == 401
    assert client.reporter_years("us") == (1754, 2014)
    assert client.reporter_years("f3d") == (1990, 2019)
    assert client.reporter_years("nope") == (None, None)
    assert client.reporter_short_name("f-supp-2d") == "F. Supp. 2d"


# --------------------------------------------------------------------------- #
# volumes / vmax — from the committed cache, offline
# --------------------------------------------------------------------------- #


def test_volumes_us_int_keyed_vmax_572(client):
    vols = client.volumes("us")
    assert isinstance(vols, dict)
    assert all(isinstance(k, int) for k in vols)
    assert max(vols) == 572
    assert client.vmax("us") == 572
    assert isinstance(vols[516], list) and vols[516][0]["reporter_slug"] == "us"


def test_volumes_f3d_and_f_supp_2d(client):
    assert client.vmax("f3d") == 935
    assert client.vmax("f-supp-2d") == 999
    assert client.volume_folders("f3d", 925) == ["925"]
    assert client.volume_folders("f3d", 9999) == []


def test_volumes_skips_non_numeric_and_groups_duplicates(tmp_path, monkeypatch):
    data = [
        {"volume_number": "1", "volume_folder": "1"},
        {"volume_number": "Index", "volume_folder": "index"},
        {"volume_number": "138", "volume_folder": "138"},
        {"volume_number": "138", "volume_folder": "138-2"},
    ]
    calls = []

    def handler(request):
        calls.append(str(request.url))
        assert request.headers["user-agent"] == USER_AGENT
        return _json_response(request, data)

    c = make_client(handler, tmp_path, monkeypatch)
    vols = c.volumes("a3d")
    assert set(vols) == {1, 138}
    assert [v["volume_folder"] for v in vols[138]] == ["138", "138-2"]
    assert c.vmax("a3d") == 138
    assert c.volume_folders("a3d", 138) == ["138", "138-2"]
    assert calls == [f"{CAP_BASE}/a3d/VolumesMetadata.json"]
    # populated the cache in the exact layout
    assert (tmp_path / "cache" / "a3d" / "VolumesMetadata.json").is_file()
    # second call served from memory: no new HTTP call
    c.volumes("a3d")
    assert len(calls) == 1


def test_cap_end_year(client):
    assert client.cap_end_year("us") == 2014
    assert client.cap_end_year("f3d") == 2019


# --------------------------------------------------------------------------- #
# cases_in_volume / page_index — DECISION-RULE §1.5
# --------------------------------------------------------------------------- #


def test_cases_in_volume_from_cache(client):
    cases = client.cases_in_volume("f3d", 925)
    assert isinstance(cases, list) and len(cases) == 116
    names = {c["name_abbreviation"] for c in cases}
    assert "J.D. v. Azar" in names


def test_page_index_925_f3d_1339_spans_jd_v_azar(client):
    idx = client.page_index("f3d", 925)
    assert isinstance(idx, PageIndex)
    hit = idx.lookup(1339)
    assert hit.exact_hits == []
    assert [c.name for c in hit.spanning] == ["J.D. v. Azar"]
    assert hit.gap is None
    case = hit.spanning[0]
    assert (case.first, case.last) == (1291, 1349)
    assert (case.first_page_raw, case.last_page_raw) == ("1291", "1349")
    assert case.file_name == "1291-01"
    assert case.official_cite == "925 F.3d 1291"
    assert case.decision_date == "2019-06-14"
    assert case.decision_year == 2019
    assert case.court_name == "Court of Appeals of the District of Columbia"
    assert case.court_abbreviation == "D.C. Cir."


def test_page_index_925_f3d_1291_exact(client):
    hit = client.page_index("f3d", 925).lookup(1291)
    assert [c.name for c in hit.exact_hits] == ["J.D. v. Azar"]
    # the previous case ends on the page where this one begins (West layout)
    assert [c.name for c in hit.spanning] == ["United Steel v. Mine Safety & Health Admin."]
    assert hit.spanning[0].last == 1291
    assert hit.gap is None
    assert [c.name for c in hit.candidates] == ["J.D. v. Azar"]
    assert [c.name for c in hit.official_hits] == ["J.D. v. Azar"]


def test_page_index_925_f3d_1349_last_page_and_next_first_page(client):
    # West starts the next case on the page where the previous one ends
    hit = client.page_index("f3d", 925).lookup(1349)
    assert [c.name for c in hit.exact_hits] == ["Philipp v. Fed. Republic of Ger."]
    assert [c.name for c in hit.spanning] == ["J.D. v. Azar"]


def test_page_index_925_f3d_1400_beyond_end(client):
    idx = client.page_index("f3d", 925)
    assert idx.max_last == 1384
    hit = idx.lookup(1400)
    assert hit.exact_hits == [] and hit.spanning == []
    assert hit.gap == "beyond_end"
    assert idx.volume_years == (2016, 2019)


def test_page_index_official_cite_differs_from_first_page(client):
    idx = client.page_index("us", 516)
    holder = idx.official("516 U.S. 545")
    assert [c.name for c in holder] == ["Holder v. Harlem Men's Shelter"]
    assert holder[0].first == 803
    assert len(idx.official("516 U.S. 1003")) == 3
    assert max(len(v) for v in idx.by_first.values()) == 16
    z = idx.lookup(217)
    assert [c.name for c in z.exact_hits] == ["Zicherman ex rel. Estate of Kole v. Korean Air Lines Co."]
    assert z.exact_hits[0].parallel_cites == ["133 L. Ed. 2d 596", "116 S. Ct. 629"]
    assert "1996 U.S. LEXIS 469" in z.exact_hits[0].all_cites


def test_page_index_odd_page_shapes(client):
    la = [c for c in client.page_index("us", 525).cases if c.name == "United States v. Louisiana"][0]
    assert (la.first_page_raw, la.last_page_raw) == ("1", "0")
    assert (la.first, la.last) == (1, 1)  # last < first → last = first
    idx = client.page_index("f3d", 174)
    miller = [c for c in idx.cases if c.name == "Miller v. City of Philadelphia"][0]
    assert (miller.first, miller.last) == (368, 391)
    assert miller.last_page_raw == "377-391"
    assert [c.name for c in idx.lookup(366).spanning] == ["Greenleaf v. Garlock, Inc."]


def test_parse_pages():
    assert parse_pages("1291", "1349") == (1291, 1349)
    assert parse_pages("368", "377-391") == (368, 391)
    assert parse_pages("1", "0") == (1, 1)
    assert parse_pages("12", None) == (12, 12)
    assert parse_pages("", "5") == (None, None)
    assert parse_pages(None, None) == (None, None)


def test_page_index_hole_and_no_digit_cases():
    cases = [
        {"id": 1, "name_abbreviation": "A v. B", "first_page": "10", "last_page": "20", "citations": [{"type": "official", "cite": "1 X 10"}], "decision_date": "2001-01-01", "court": {"name": "C"}},
        {"id": 2, "name_abbreviation": "C v. D", "first_page": "30", "last_page": "40", "citations": [], "decision_date": "2002-02-02", "court": {"name": "C"}},
        {"id": 3, "name_abbreviation": "No Pages", "first_page": "", "last_page": "", "citations": [], "decision_date": "2003-03-03", "court": {"name": "C"}},
        {"id": 1, "name_abbreviation": "A v. B", "first_page": "10", "last_page": "20", "citations": [], "decision_date": "2001-01-01", "court": {"name": "C"}},  # duplicate id
    ]
    idx = PageIndex.from_cases("x", 1, cases)
    assert len(idx.cases) == 3  # deduped by id, no-digit case kept for name search
    assert [c.name for c in idx.page_cases] == ["A v. B", "C v. D"]
    assert idx.lookup(25).gap == "hole"
    assert idx.lookup(45).gap == "beyond_end"
    assert idx.lookup(15).gap is None
    assert idx.max_last == 40
    assert idx.covered == set(range(10, 21)) | set(range(30, 41))
    assert idx.volume_years == (2001, 2003)
    assert idx.first_pages == (10, 40)


def test_to_real_case_builds_models_realcase(client):
    hit = client.page_index("f3d", 925).lookup(1339)
    rc = to_real_case(hit.spanning[0])
    assert isinstance(rc, RealCase)
    assert rc.model_dump() == {
        "name": "J.D. v. Azar",
        "first_page": 1291,
        "last_page": 1349,
        "decision_date": "2019-06-14",
        "court": "Court of Appeals of the District of Columbia",
        "court_abbreviation": "D.C. Cir.",
        "cite": "925 F.3d 1291",
        "file_name": "1291-01",
        "id": 12521273,
        "parallel_cites": [],
    }


# --------------------------------------------------------------------------- #
# case_json / opinion_text / running_head
# --------------------------------------------------------------------------- #


def test_case_json_opinion_text_running_head(client):
    case = client.case_json("f3d", 925, "1291-01")
    assert case["name_abbreviation"] == "J.D. v. Azar"
    text = opinion_text(case)
    assert len(text) == 179251
    assert text.startswith("Dissenting opinion filed by Senior Circuit Judge Silberman.")
    assert running_head(case) == "925 F.3d 1291 · J.D. v. AZAR"
    assert client.opinion_text(case) == text
    assert client.running_head(case) == "925 F.3d 1291 · J.D. v. AZAR"


def test_zicherman_from_cache(client):
    case = client.case_json("us", 516, "0217-01")
    assert running_head(case) == "516 U.S. 217 · ZICHERMAN EX REL. ESTATE OF KOLE v. KOREAN AIR LINES CO."
    entry = client.page_index("us", 516).lookup(217).exact_hits[0]
    assert running_head(entry) == running_head(case)
    assert client.case_json("us", 516, entry.file_name) is case  # memory LRU


def test_opinion_text_joins_with_two_newlines():
    case = {"casebody": {"opinions": [{"type": "majority", "text": "A"}, {"type": "dissent", "text": "B"}]}}
    assert opinion_text(case) == "A\n\nB"
    assert opinion_text({"casebody": {}}) == ""
    assert opinion_text({}) == ""


def test_running_head_fallbacks():
    assert running_head({"citations": [{"type": "parallel", "cite": "1 P 2"}, {"type": "official", "cite": "3 O 4"}], "name_abbreviation": "x v. y"}) == "3 O 4 · X v. Y"
    assert running_head({"citations": [{"type": "parallel", "cite": "1 P 2"}], "name_abbreviation": "x v. y"}) == "1 P 2 · X v. Y"
    assert running_head({"name_abbreviation": "In re Foo"}) == "IN RE FOO"


def test_links(client):
    assert client.volumes_url("us") == f"{CAP_BASE}/us/VolumesMetadata.json"
    assert client.cases_url("f3d", 925) == f"{CAP_BASE}/f3d/925/CasesMetadata.json"
    assert client.case_url("f3d", 925, "1291-01") == f"{CAP_BASE}/f3d/925/cases/1291-01.json"
    assert client.links_for("f3d", 925, "1291-01") == [
        f"{CAP_BASE}/f3d/VolumesMetadata.json",
        f"{CAP_BASE}/f3d/925/CasesMetadata.json",
        f"{CAP_BASE}/f3d/925/cases/1291-01.json",
    ]


# --------------------------------------------------------------------------- #
# Offline mode: typed failure, never a silent empty result
# --------------------------------------------------------------------------- #


def test_offline_uncached_raises_corpus_unavailable(client):
    assert client.offline is True
    with pytest.raises(CorpusUnavailable) as ei:
        client.volumes("f4th")
    assert ei.value.reason == "offline"
    assert ei.value.url == f"{CAP_BASE}/f4th/VolumesMetadata.json"
    assert "f4th/VolumesMetadata.json" in str(ei.value)
    with pytest.raises(CorpusUnavailable) as ei2:
        client.cases_in_volume("us", 571)  # listed (vmax 572) but not in the seed cache
    assert ei2.value.url == f"{CAP_BASE}/us/571/CasesMetadata.json"
    with pytest.raises(CorpusUnavailable):
        client.page_index("f3d", 900)
    # not listed at all → Absent (None), decided from the cached volume index, no network needed
    assert client.cases_in_volume("us", 600) is None
    assert client.page_index("us", 600) is None
    with pytest.raises(CorpusUnavailable):
        client.case_json("f3d", 925, "0001-01")


def test_offline_makes_no_http_call(tmp_path, monkeypatch):
    def handler(request):
        raise AssertionError(f"network call in offline mode: {request.url}")

    c = make_client(handler, tmp_path, monkeypatch, offline=True)
    assert c.vmax("us") == 572
    with pytest.raises(CorpusUnavailable):
        c.volumes("f4th")


def test_offline_flag_override(tmp_path, monkeypatch):
    monkeypatch.setenv("CITEMEMO_OFFLINE", "1")
    monkeypatch.setenv("CITEMEMO_CACHE_DIR", str(tmp_path / "cache"))
    c = CapClient(offline=False)
    assert c.offline is False
    monkeypatch.setenv("CITEMEMO_OFFLINE", "0")
    assert CapClient().offline is False
    monkeypatch.setenv("CITEMEMO_OFFLINE", "true")
    assert CapClient().offline is True


# --------------------------------------------------------------------------- #
# Network semantics — DECISION-RULE §1.4: Present / Absent / Failed
# --------------------------------------------------------------------------- #


def test_404_is_absent_and_cached(tmp_path, monkeypatch):
    calls = []

    def handler(request):
        calls.append(str(request.url))
        if request.url.path == "/zz/VolumesMetadata.json":
            return _json_response(request, [{"volume_number": "600", "volume_folder": "600"}])
        return httpx.Response(404, text="<html>" + "x" * 100 + "</html>", request=request)

    c = make_client(handler, tmp_path, monkeypatch)
    assert c.cases_in_volume("zz", 600) is None
    assert c.cases_in_volume("zz", 600) is None
    assert c.page_index("zz", 600) is None
    assert calls == [f"{CAP_BASE}/zz/VolumesMetadata.json", f"{CAP_BASE}/zz/600/CasesMetadata.json"]  # absence cached
    assert (tmp_path / "cache" / "zz" / "600" / "CasesMetadata.json.404").is_file()
    assert c.volumes("f4th") is None
    assert c.vmax("f4th") is None
    assert c.cap_end_year("f4th") is None
    assert len(calls) == 3
    # a fresh client with the same cache dir still knows both are absent
    c2 = make_client(handler, tmp_path, monkeypatch)
    assert c2.volumes("f4th") is None
    assert c2.cases_in_volume("zz", 600) is None
    assert len(calls) == 3


def test_timeout_retries_once_then_raises_with_url(tmp_path, monkeypatch):
    calls = []

    def handler(request):
        calls.append(str(request.url))
        raise httpx.ReadTimeout("slow", request=request)

    c = make_client(handler, tmp_path, monkeypatch)
    with pytest.raises(CorpusUnavailable) as ei:
        c.volumes("f4th")
    assert len(calls) == 2
    assert ei.value.reason == "timeout"
    assert ei.value.url == f"{CAP_BASE}/f4th/VolumesMetadata.json"
    assert ei.value.url in str(ei.value)
    # failures are not cached: the next call tries the network again
    with pytest.raises(CorpusUnavailable):
        c.volumes("f4th")
    assert len(calls) == 4


def test_server_error_retries_once_then_raises(tmp_path, monkeypatch):
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(503, text="down", request=request)

    c = make_client(handler, tmp_path, monkeypatch)
    with pytest.raises(CorpusUnavailable) as ei:
        c.volumes("f4th")
    assert len(calls) == 2
    assert ei.value.reason == "http 503"
    assert not (tmp_path / "cache" / "f4th").exists()  # failures are never cached


def test_connection_error_raises(tmp_path, monkeypatch):
    def handler(request):
        raise httpx.ConnectError("refused", request=request)

    c = make_client(handler, tmp_path, monkeypatch)
    with pytest.raises(CorpusUnavailable) as ei:
        c.volumes("f4th")
    assert ei.value.reason == "connection"


def test_200_non_json_body_is_failed_not_cached(tmp_path, monkeypatch):
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(200, text="<html>not json</html>", request=request)

    c = make_client(handler, tmp_path, monkeypatch)
    with pytest.raises(CorpusUnavailable) as ei:
        c.volumes("f4th")
    assert ei.value.reason == "non-json"
    assert not (tmp_path / "cache" / "f4th").exists()


def test_live_fetch_populates_cache_in_exact_layout(tmp_path, monkeypatch):
    vols = [{"volume_number": "1", "volume_folder": "1", "reporter_slug": "zz"}]
    cases = [
        {"id": 7, "name_abbreviation": "A v. B", "first_page": "5", "last_page": "9", "file_name": "0005-01",
         "citations": [{"type": "official", "cite": "1 Zz. 5"}], "decision_date": "1999-09-09", "court": {"name": "Court"}},
    ]
    case = {"id": 7, "name_abbreviation": "A v. B", "citations": [{"type": "official", "cite": "1 Zz. 5"}],
            "casebody": {"opinions": [{"type": "majority", "text": "Hello."}]}}
    calls = []

    def handler(request):
        calls.append(str(request.url))
        path = request.url.path
        if path == "/zz/VolumesMetadata.json":
            return _json_response(request, vols)
        if path == "/zz/1/CasesMetadata.json":
            return _json_response(request, cases)
        if path == "/zz/1/cases/0005-01.json":
            return _json_response(request, case)
        return httpx.Response(404, text="<html>", request=request)

    c = make_client(handler, tmp_path, monkeypatch)
    assert c.vmax("zz") == 1
    hit = c.page_index("zz", 1).lookup(7)
    assert [x.name for x in hit.spanning] == ["A v. B"]
    assert opinion_text(c.case_json("zz", 1, "0005-01")) == "Hello."
    root = tmp_path / "cache" / "zz"
    assert (root / "VolumesMetadata.json").is_file()
    assert (root / "1" / "CasesMetadata.json").is_file()
    assert (root / "1" / "cases" / "0005-01.json").is_file()
    assert len(calls) == 3
    # a new offline client now answers from the populated cache with no network
    monkeypatch.setenv("CITEMEMO_OFFLINE", "1")
    c2 = CapClient(transport=httpx.MockTransport(lambda r: (_ for _ in ()).throw(AssertionError(r.url))))
    assert c2.vmax("zz") == 1
    assert c2.case_json("zz", 1, "0005-01")["id"] == 7


def test_duplicate_volume_folders_are_unioned_and_deduped(tmp_path, monkeypatch):
    vols = [{"volume_number": "138", "volume_folder": "138"}, {"volume_number": "138", "volume_folder": "138-2"}]
    a = {"id": 1, "name_abbreviation": "A v. B", "first_page": "1", "last_page": "2", "citations": [], "decision_date": "2016-01-01", "court": {"name": "C"}}
    b = {"id": 2, "name_abbreviation": "C v. D", "first_page": "3", "last_page": "4", "citations": [], "decision_date": "2016-01-01", "court": {"name": "C"}}

    def handler(request):
        p = request.url.path
        if p == "/a3d/VolumesMetadata.json":
            return _json_response(request, vols)
        if p == "/a3d/138/CasesMetadata.json":
            return _json_response(request, [a, b])
        if p == "/a3d/138-2/CasesMetadata.json":
            return _json_response(request, [b])
        return httpx.Response(404, text="<html>", request=request)

    c = make_client(handler, tmp_path, monkeypatch)
    cases = c.cases_in_volume("a3d", 138)
    assert [x["id"] for x in cases] == [1, 2]
    assert (tmp_path / "cache" / "a3d" / "138-2" / "CasesMetadata.json").is_file()
    assert c.cases_url("a3d", "138-2") == f"{CAP_BASE}/a3d/138-2/CasesMetadata.json"


def test_cases_in_volume_for_volume_not_listed_is_none_without_fetch(tmp_path, monkeypatch):
    calls = []

    def handler(request):
        calls.append(str(request.url))
        if request.url.path == "/zz/VolumesMetadata.json":
            return _json_response(request, [{"volume_number": "1", "volume_folder": "1"}])
        raise AssertionError(request.url)

    c = make_client(handler, tmp_path, monkeypatch)
    assert c.cases_in_volume("zz", 2) is None
    assert c.page_index("zz", 2) is None
    assert calls == [f"{CAP_BASE}/zz/VolumesMetadata.json"]


# --------------------------------------------------------------------------- #
# Batch fetch: async with bounded concurrency 6, plus a sync facade
# --------------------------------------------------------------------------- #


def test_fetch_volumes_batch_bounded_concurrency(tmp_path, monkeypatch):
    in_flight = {"now": 0, "max": 0}
    vols = [{"volume_number": str(i), "volume_folder": str(i)} for i in range(1, 21)]

    async def handler(request):
        in_flight["now"] += 1
        in_flight["max"] = max(in_flight["max"], in_flight["now"])
        await asyncio.sleep(0.01)
        in_flight["now"] -= 1
        p = request.url.path
        if p == "/zz/VolumesMetadata.json":
            return _json_response(request, vols)
        if p.endswith("/CasesMetadata.json"):
            vol = p.split("/")[2]
            if vol == "13":
                return httpx.Response(404, text="<html>", request=request)
            if vol == "17":
                raise httpx.ReadTimeout("slow", request=request)
            return _json_response(request, [{"id": int(vol), "name_abbreviation": f"V{vol}", "first_page": "1", "last_page": "9", "citations": [], "decision_date": "2000-01-01", "court": {"name": "C"}}])
        return httpx.Response(404, text="<html>", request=request)

    c = make_client(handler, tmp_path, monkeypatch)
    pairs = [("zz", v) for v in range(1, 21)]
    out = c.fetch_volumes_batch(pairs)
    assert set(out) == set(pairs)
    assert out[("zz", 13)] is None
    assert isinstance(out[("zz", 17)], CorpusUnavailable)
    assert out[("zz", 17)].reason == "timeout"
    assert out[("zz", 1)][0]["name_abbreviation"] == "V1"
    assert 1 < in_flight["max"] <= CONCURRENCY
    # everything landed in the two-level cache: no more network needed
    assert c.page_index("zz", 5).lookup(3).spanning[0].name == "V5"
    assert (tmp_path / "cache" / "zz" / "5" / "CasesMetadata.json").is_file()


def test_fetch_volumes_batch_async_inside_running_loop(tmp_path, monkeypatch):
    def handler(request):
        if request.url.path == "/zz/VolumesMetadata.json":
            return _json_response(request, [{"volume_number": "1", "volume_folder": "1"}])
        return _json_response(request, [])

    c = make_client(handler, tmp_path, monkeypatch)

    async def go():
        out = await c.fetch_volumes_batch_async([("zz", 1), ("zz", 2), ("f3d", 925)])
        return out

    out = asyncio.run(go())
    assert out[("zz", 1)] == []
    assert out[("zz", 2)] is None
    assert len(out[("f3d", 925)]) == 116  # seed cache, no network


def test_fetch_volumes_batch_offline(client):
    out = client.fetch_volumes_batch([("f3d", 925), ("us", 516), ("f3d", 900), ("us", 600)])
    assert len(out[("f3d", 925)]) == 116
    assert any(c["name_abbreviation"].startswith("Zicherman") for c in out[("us", 516)])
    assert isinstance(out[("f3d", 900)], CorpusUnavailable)
    assert out[("f3d", 900)].reason == "offline"
    assert out[("us", 600)] is None


# --------------------------------------------------------------------------- #
# Opt-in live check (skipped by default): a real fetch populates the cache
# --------------------------------------------------------------------------- #


@pytest.mark.skipif(os.environ.get("CITEMEMO_LIVE") != "1", reason="set CITEMEMO_LIVE=1 to hit static.case.law")
def test_live_uncached_volume_populates_cache(tmp_path, monkeypatch):
    monkeypatch.delenv("CITEMEMO_OFFLINE", raising=False)
    monkeypatch.setenv("CITEMEMO_CACHE_DIR", str(tmp_path / "cache"))
    c = CapClient()
    idx = c.page_index("f-supp-2d", 905)  # volume index cached; cases file is committed too
    assert idx is not None
    cases = c.cases_in_volume("f3d", 1)  # not in the seed cache
    assert cases and (tmp_path / "cache" / "f3d" / "1" / "CasesMetadata.json").is_file()
