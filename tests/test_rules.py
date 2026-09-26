"""DECISION-RULE.md §7 matrix for ``citememo.rules`` and ``citememo.names``.

Every row builds a ``RuleContext`` from the committed cache under ``seed/cache/cap``
(json.load, no network) or from a small synthetic context where the matrix marks a
fixture "+ to add" (rows 21–23, 39, 41–44, 59). Rows that belong to ``extract.py``
(20's regex catch, 31, 50), ``quotes.py`` (51–55) or ``memo.py`` (48–49 grouping, 60)
are exercised at the ``rules`` boundary: the classifier is handed the ``CitationInput``
kind or the ``QuoteCheck`` those modules produce.

Wording: ``reasons[0]`` follows the brief's verbatim sentences (UI-SPEC §9 rule lines)
where they are quoted; the §7 "contains" fragments are checked case-insensitively and
adapted only where the brief's sentence supersedes them (see the report's RULINGS).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from citememo import names, rules
from citememo.models import CitationInput, CitationResult, DiffToken, QuoteCheck
from citememo.rules import ReporterMeta, RuleContext

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "seed" / "cache" / "cap"
GROUND_TRUTH = json.loads((ROOT / "seed" / "ground_truth.json").read_text())

# --------------------------------------------------------------------------- #
# Fixtures: reporter metadata (reporters_db 3.2.66 + data/cap/ReportersMetadata.json,
# values as DECISION-RULE §1.3/§3 lists them) and cache loaders
# --------------------------------------------------------------------------- #

META: dict[str, ReporterMeta] = {
    "U.S.": ReporterMeta(
        reporter="U.S.", cite_type="federal", edition_start=1875, edition_end=None,
        cap_start_year=1754, cap_end_year=2014, slug="us",
    ),
    "F.3d": ReporterMeta(
        reporter="F.3d", cite_type="federal", edition_start=1993, edition_end=None,
        cap_start_year=1990, cap_end_year=2019, slug="f3d",
        successor="F.4th", successor_start="2021-01-01",
    ),
    "F.2d": ReporterMeta(
        reporter="F.2d", cite_type="federal", edition_start=1924, edition_end=1993,
        cap_start_year=1910, cap_end_year=1993, slug="f2d",
        successor="F.3d", successor_start="1993-01-01",
    ),
    "F. Supp.": ReporterMeta(
        reporter="F. Supp.", cite_type="federal", edition_start=1932, edition_end=1988,
        cap_start_year=1839, cap_end_year=1998, slug="f-supp",
        successor="F. Supp. 2d", successor_start="1988-01-01",
    ),
    "F. Supp. 2d": ReporterMeta(
        reporter="F. Supp. 2d", cite_type="federal", edition_start=1988, edition_end=2014,
        cap_start_year=1982, cap_end_year=2014, slug="f-supp-2d",
        successor="F. Supp. 3d", successor_start="2014-03-04",
    ),
    "F. Supp. 3d": ReporterMeta(
        reporter="F. Supp. 3d", cite_type="federal", edition_start=2014, edition_end=None,
        cap_start_year=1968, cap_end_year=2019, slug="f-supp-3d",
    ),
    "S. Ct.": ReporterMeta(
        reporter="S. Ct.", cite_type="federal", edition_start=1882, edition_end=None,
        cap_start_year=2013, cap_end_year=2020, slug="s-ct",
    ),
    "So. 3d": ReporterMeta(
        reporter="So. 3d", cite_type="state", edition_start=2000, edition_end=None,
        cap_start_year=2000, cap_end_year=2019, slug="so3d",
    ),
    "F.4th": ReporterMeta(
        reporter="F.4th", cite_type="federal", edition_start=2021, edition_end=None, slug=None,
    ),
    "N.Y.S.3d": ReporterMeta(
        reporter="N.Y.S.3d", cite_type="state", edition_start=2012, edition_end=None, slug=None,
    ),
    "WL": ReporterMeta(reporter="WL", cite_type="specialty_west", slug=None),
    "LEXIS": ReporterMeta(reporter="LEXIS", cite_type="specialty_lexis", slug=None),
    "U.S. Dist. LEXIS": ReporterMeta(reporter="U.S. Dist. LEXIS", cite_type="specialty_lexis", slug=None),
    "IL App (1st)": ReporterMeta(reporter="IL App (1st)", cite_type="neutral", slug=None),
}

_VOLUMES_CACHE: dict[str, dict[str, list[dict]]] = {}
_CASES_CACHE: dict[tuple[str, int], list[dict]] = {}


def load_volumes(slug: str) -> dict[str, list[dict]]:
    if slug not in _VOLUMES_CACHE:
        rows = json.loads((CACHE / slug / "VolumesMetadata.json").read_text())
        vols: dict[str, list[dict]] = {}
        for row in rows:
            vols.setdefault(str(row["volume_number"]), []).append(row)
        _VOLUMES_CACHE[slug] = vols
    return _VOLUMES_CACHE[slug]


def load_cases(slug: str, volume: int) -> list[dict]:
    key = (slug, volume)
    if key not in _CASES_CACHE:
        _CASES_CACHE[key] = json.loads((CACHE / slug / str(volume) / "CasesMetadata.json").read_text())
    return _CASES_CACHE[key]


def ctx_for(reporter: str, volume: int | None = None, **over) -> RuleContext:
    """A RuleContext from the committed cache; ``over`` replaces fields (e.g. cases=None)."""
    meta = META[reporter]
    kwargs: dict = {"slug": meta.slug, "reporter": meta}
    if meta.slug and (CACHE / meta.slug / "VolumesMetadata.json").exists():
        vols = load_volumes(meta.slug)
        kwargs["volumes"] = vols
        kwargs["vmax"] = max(int(v) for v in vols)
        if volume is not None and (CACHE / meta.slug / str(volume) / "CasesMetadata.json").exists():
            kwargs["cases"] = load_cases(meta.slug, volume)
    kwargs.update(over)
    return RuleContext(**kwargs)


def synthetic_volumes(vmin: int, vmax: int, *, skip: tuple[int, ...] = (), years: dict[int, tuple[int, int]] | None = None) -> dict[str, list[dict]]:
    vols: dict[str, list[dict]] = {}
    for v in range(vmin, vmax + 1):
        if v in skip:
            continue
        sy, ey = (years or {}).get(v, (0, 0))
        vols[str(v)] = [{"volume_number": str(v), "start_year": sy, "end_year": ey}]
    return vols


def case_row(name: str, first, last, *, date: str = "1999-01-01", court: str = "Court", cid: int | None = None, cite: str | None = None) -> dict:
    cid = cid if cid is not None else abs(hash((name, str(first), str(last)))) % 10_000_000
    return {
        "id": cid,
        "name": name,
        "name_abbreviation": name,
        "decision_date": date,
        "first_page": str(first),
        "last_page": str(last),
        "citations": [{"type": "official", "cite": cite}] if cite else [],
        "court": {"name": court, "name_abbreviation": court, "id": 1},
        "file_name": f"{int(re.findall(r'\d+', str(first))[0]):04d}-01" if re.findall(r"\d+", str(first)) else None,
    }


_CITE_RE = re.compile(r"^(\d+)\s+(.+?)\s+(\d+)$")


def cite(text: str, *, plaintiff: str | None = None, defendant: str | None = None, year: int | None = None,
         court: str | None = None, kind: str = "full", pin_cite: str | None = None, quotes: tuple[str, ...] = (),
         reporter: str | None = None) -> CitationInput:
    m = _CITE_RE.match(text)
    volume = page = None
    if m:
        volume, reporter, page = int(m.group(1)), reporter or m.group(2), int(m.group(3))
    return CitationInput(
        text=text, volume=volume, reporter=reporter, page=page, year=year, court=court,
        plaintiff=plaintiff, defendant=defendant, kind=kind, pin_cite=pin_cite, quotes=list(quotes),
    )


def parties(s: str) -> tuple[str | None, str | None]:
    if " v. " in s:
        a, b = s.split(" v. ", 1)
        return a, b
    return None, s


def has(result: CitationResult, fragment: str) -> bool:
    return fragment.lower() in result.reasons[0].lower()


def any_reason(result: CitationResult, fragment: str) -> bool:
    return any(fragment.lower() in r.lower() for r in result.reasons)


# --------------------------------------------------------------------------- #
# §7 matrix, rows 1–47, 56–62 (cite, ctx, expected class, reasons[0] fragment)
# --------------------------------------------------------------------------- #

def _us5_ctx() -> RuleContext:
    cases = [
        case_row("Turner v. Fendall", 117, 137, date="1801-12-01", cite="5 U.S. 117"),
        case_row("Marbury v. Madison", 137, 180, date="1803-02-24", court="Supreme Court of the United States", cite="5 U.S. 137"),
    ]
    return RuleContext(slug="us", reporter=META["U.S."], volumes=load_volumes("us"), vmax=572, cases=cases)


def _fsupp3d_ctx() -> RuleContext:
    vols = synthetic_volumes(1, 392, skip=(183, 184, 203, 204, 205, 206), years={v: (2019, 2019) for v in range(350, 393)})
    return RuleContext(slug="f-supp-3d", reporter=META["F. Supp. 3d"], volumes=vols, vmax=392)


def _f2d_ctx() -> RuleContext:
    return RuleContext(slug="f2d", reporter=META["F.2d"], volumes=synthetic_volumes(1, 999), vmax=999)


def _fsupp_999_ctx() -> RuleContext:
    cases = [case_row("Smith v. Jones", 1, 20, date="1998-03-01", court="United States District Court for the Southern District of New York", cite="999 F. Supp. 1")]
    return RuleContext(slug="f-supp", reporter=META["F. Supp."], volumes=synthetic_volumes(1, 999), vmax=999, cases=cases)


def _so3d_ctx() -> RuleContext:
    cases = [case_row("Doe v. Roe", 456, 470, date="2013-06-01", court="Supreme Court of Florida", cite="123 So. 3d 456")]
    return RuleContext(slug="so3d", reporter=META["So. 3d"], volumes=synthetic_volumes(1, 300), vmax=300, cases=cases)


MATRIX = [
    # (matrix id, CitationInput, RuleContext factory, expected class, reasons[0] contains (ci))
    ("01-seed-mata-varghese", cite("925 F.3d 1339", plaintiff="Varghese", defendant="China Southern Airlines Co.", year=2019, court="11th Cir."),
     lambda: ctx_for("F.3d", 925), "likely_fabricated", "belongs to J.D. v. Azar"),
    ("02-seed-mata-petersen", cite("905 F. Supp. 2d 121", plaintiff="Petersen", defendant="Iran Air", year=2012, court="D.D.C."),
     lambda: ctx_for("F. Supp. 2d", 905), "likely_fabricated", "United States v. ISS Marine Services, Inc."),
    ("03-seed-mata-miller", cite("174 F.3d 366", plaintiff="Miller", defendant="United Airlines, Inc.", year=1999, court="2d Cir."),
     lambda: ctx_for("F.3d", 174), "likely_fabricated", "belongs to Greenleaf v. Garlock, Inc."),
    ("04-seed-mata-shaboon", cite("2013 IL App (1st) 111279", plaintiff="Shaboon", defendant="Egyptair", reporter="IL App (1st)"),
     lambda: ctx_for("IL App (1st)"), "not_in_free_corpus", "public-domain neutral citation"),
    ("05-seed-mata-martinez", cite("2019 WL 4639462", plaintiff="Martinez", defendant="Delta Air Lines, Inc.", year=2019, court="Tex. App."),
     lambda: ctx_for("WL"), "not_in_free_corpus", "proprietary citation"),
    ("06-seed-mata-durden", cite("2017 WL 2418825", plaintiff="Estate  Durden", defendant="KLM Royal Dutch Airlines", year=2017, court="Ga. Ct. App."),
     lambda: ctx_for("WL"), "not_in_free_corpus", "proprietary citation"),
    ("07-seed-real-zicherman", cite("516 U.S. 217", plaintiff="Zicherman", defendant="Korean Air Lines Co.", year=1996),
     lambda: ctx_for("U.S.", 516), "verified", "Zicherman ex rel. Estate of Kole v. Korean Air Lines Co."),
    ("08-seed-real-tseng", cite("525 U.S. 155", plaintiff="El Al Israel Airlines, Ltd.", defendant="Tsui Yuan Tseng", year=1999),
     lambda: ctx_for("U.S.", 525), "verified", "525 U.S. 155"),
    ("09-seed-real-husain", cite("540 U.S. 644", plaintiff="Olympic Airways", defendant="Husain", year=2004),
     lambda: ctx_for("U.S.", 540), "verified", "540 U.S. 644"),
    ("10-seed-real-saks", cite("470 U.S. 392", plaintiff="Air France", defendant="Saks", year=1985),
     lambda: ctx_for("U.S.", 470), "verified", "470 U.S. 392"),
    ("11-seed-real-floyd", cite("499 U.S. 530", plaintiff="Eastern Airlines, Inc.", defendant="Floyd", year=1991),
     lambda: ctx_for("U.S.", 499), "verified", "499 U.S. 530"),
    ("12-seed-real-azar", cite("925 F.3d 1291", plaintiff="J.D.", defendant="Azar", year=2019, court="D.C. Cir."),
     lambda: ctx_for("F.3d", 925), "verified", "925 F.3d 1291"),
    ("13-seed-real-greenleaf", cite("174 F.3d 352", plaintiff="Greenleaf", defendant="Garlock, Inc.", year=1999, court="3d Cir."),
     lambda: ctx_for("F.3d", 174), "verified", "174 F.3d 352"),
    ("14-seed-real-twombly", cite("550 U.S. 544", plaintiff="Bell Atlantic Corp.", defendant="Twombly", year=2007),
     lambda: ctx_for("U.S.", 550), "verified", "550 U.S. 544"),
    # 15, 16 (quote rows) are tested through apply_quote_check below; the lookup half is verified:
    ("15-seed-misq-iqbal-lookup", cite("556 U.S. 662", plaintiff="Ashcroft", defendant="Iqbal", year=2009),
     lambda: ctx_for("U.S.", 556), "verified", "556 U.S. 662"),
    ("16-seed-misq-chan-lookup", cite("490 U.S. 122", plaintiff="Chan", defendant="Korean Air Lines, Ltd.", year=1989),
     lambda: ctx_for("U.S.", 490), "verified", "490 U.S. 122"),
    ("17-seed-cov-biden-nebraska-beyond", cite("600 U.S. 477", plaintiff="Biden", defendant="Nebraska", year=2023),
     lambda: ctx_for("U.S."), "not_in_free_corpus", "U.S. Reports volumes after 572 are not in the Caselaw Access Project."),
    ("18-seed-cov-loper-bright-beyond", cite("603 U.S. 369", plaintiff="Loper Bright Enterprises", defendant="Raimondo", year=2024),
     lambda: ctx_for("U.S."), "not_in_free_corpus", "volumes after 572"),
    ("19-seed-wrong-zicherman-230", cite("516 U.S. 230", plaintiff="Zicherman", defendant="Korean Air Lines Co.", year=1996),
     lambda: ctx_for("U.S.", 516), "wrong_cite_exists", "begins at 516 U.S. 217; page 230 is inside it (217–232)"),
    ("20-seed-unrec-alvarez", cite("88 Fed. Air Rptr. 3d 412", plaintiff="Alvarez", defendant="Skyline Cargo", year=2018, kind="unrecognized"),
     lambda: RuleContext(slug=None, reporter=None), "unrecognized_reporter", "'Fed. Air Rptr. 3d'"),
    ("21-label-mata-beyond", cite("678 F. Supp. 3d 443", plaintiff="Mata", defendant="Avianca, Inc.", year=2023, court="S.D.N.Y."),
     _fsupp3d_ctx, "not_in_free_corpus", "F. Supp. 3d volumes after 392"),
    ("22-marbury", cite("5 U.S. 137", plaintiff="Marbury", defendant="Madison", year=1803),
     _us5_ctx, "verified", "5 U.S. 137"),
    ("23-marbury-nominative", cite("5 U.S. 137", plaintiff="Marbury", defendant="Madison", year=1803),
     _us5_ctx, "verified", "5 U.S. 137"),
    ("24-papst-in-re", cite("905 F. Supp. 2d 43", plaintiff=None, defendant="Papst Licensing GmbH & Co. KG Litigation", year=2012, court="D.D.C."),
     lambda: ctx_for("F. Supp. 2d", 905), "verified", "In re Papst Licensing"),
    ("25-us-v-varghese", cite("905 F. Supp. 2d 121", plaintiff="United States", defendant="Varghese", year=2012, court="D.D.C."),
     lambda: ctx_for("F. Supp. 2d", 905), "likely_fabricated", "United States v. ISS Marine Services"),
    ("26-us-v-iran-air", cite("905 F. Supp. 2d 121", plaintiff="United States", defendant="Iran Air", year=2012, court="D.D.C."),
     lambda: ctx_for("F. Supp. 2d", 905), "likely_fabricated", "United States v. ISS Marine Services"),
    ("27-doe-v-garlock", cite("174 F.3d 352", plaintiff="Doe", defendant="Garlock", year=1999, court="3d Cir."),
     lambda: ctx_for("F.3d", 174), "wrong_cite_exists", "the case that begins at 174 F.3d 352 is Greenleaf v. Garlock, Inc."),
    ("28-saks-year-typo", cite("470 U.S. 392", plaintiff="Air France", defendant="Saks", year=1986),
     lambda: ctx_for("U.S.", 470), "verified", "470 U.S. 392"),
    ("29-iqbal-year-2010", cite("556 U.S. 662", plaintiff="Ashcroft", defendant="Iqbal", year=2010),
     lambda: ctx_for("U.S.", 556), "verified", "556 U.S. 662"),
    ("30-husain-wrong-page-year", cite("540 U.S. 700", plaintiff="Olympic Airways", defendant="Husain", year=2007),
     lambda: ctx_for("U.S.", 540), "wrong_cite_exists", "Olympic Airways v. Husain is in this volume at 540 U.S. 644, not page 700"),
    ("31-cert-denied-550-skipped", cite("550 U.S. 901", year=2007, kind="short"),
     lambda: ctx_for("U.S.", 550), "skipped", "short-form"),
    ("32-bare-orders-page", cite("556 U.S. 1104", year=2009),
     lambda: ctx_for("U.S.", 556), "not_in_free_corpus", "page 1104 of 556 U.S. is not in the free corpus"),
    ("33-holder-official-cite", cite("516 U.S. 545", plaintiff="Holder", defendant="Harlem Men's Shelter", year=1996),
     lambda: ctx_for("U.S.", 516), "verified", "516 U.S. 545"),
    ("34-orders-shared-page", cite("516 U.S. 1003", plaintiff="Ruyle", defendant="Continental Oil Co.", year=1996),
     lambda: ctx_for("U.S.", 516), "verified", "516 U.S. 1003"),
    ("35-orders-unknown-name", cite("516 U.S. 801", plaintiff="Nobody", defendant="Anyone", year=1996),
     lambda: ctx_for("U.S.", 516), "not_in_free_corpus", "orders pages of U.S. Reports are not fully held"),
    ("36-f4th", cite("60 F.4th 1", plaintiff="Smith", defendant="Jones", year=2023, court="2d Cir."),
     lambda: ctx_for("F.4th"), "not_in_free_corpus", "F.4th is not held by the Caselaw Access Project"),
    ("37-f3d-1000-beyond", cite("1000 F.3d 1", plaintiff="Smith", defendant="Jones", year=2021, court="9th Cir."),
     lambda: ctx_for("F.3d"), "not_in_free_corpus", "F.3d volumes after 935"),
    ("38-f3d-1100-beyond", cite("1100 F.3d 50", plaintiff="Smith", defendant="Jones", year=2023, court="9th Cir."),
     lambda: ctx_for("F.3d"), "not_in_free_corpus", "F.3d volumes after 935"),
    ("39-f2d-1005", cite("1005 F.2d 1", plaintiff="Smith", defendant="Jones", year=1994, court="9th Cir."),
     _f2d_ctx, "likely_fabricated", "F.2d ended at volume 999"),
    ("40-fsupp2d-1050", cite("1050 F. Supp. 2d 45", plaintiff="Doe", defendant="Roe", year=2015, court="S.D.N.Y."),
     lambda: ctx_for("F. Supp. 2d"), "likely_fabricated", "F. Supp. 2d ended at volume 999"),
    ("41-fsupp3d-700-beyond", cite("700 F. Supp. 3d 10", plaintiff="Doe", defendant="Roe", year=2024, court="S.D.N.Y."),
     _fsupp3d_ctx, "not_in_free_corpus", "F. Supp. 3d volumes after 392"),
    ("42-fsupp-1998", cite("999 F. Supp. 1", plaintiff="Smith", defendant="Jones", year=1998, court="S.D.N.Y."),
     _fsupp_999_ctx, "verified", "999 F. Supp. 1"),
    ("43-fsupp3d-missing-vol", cite("183 F. Supp. 3d 1", plaintiff="Doe", defendant="Roe", year=2016),
     _fsupp3d_ctx, "not_in_free_corpus", "volume 183 of F. Supp. 3d is not in the free corpus"),
    ("44-so3d-spelling", cite("123 So. 3d 456", plaintiff="Doe", defendant="Roe", year=2013, court="Fla."),
     _so3d_ctx, "verified", "123 So. 3d 456"),
    ("45-miller-real-368", cite("174 F.3d 368", plaintiff="Miller", defendant="City of Philadelphia", year=1999, court="3d Cir."),
     lambda: ctx_for("F.3d", 174), "verified", "174 F.3d 368"),
    ("46-griffith-real-1222", cite("174 F.3d 1222", plaintiff="Griffith", defendant="United States", year=1999, court="Fed. Cir."),
     lambda: ctx_for("F.3d", 174), "verified", "174 F.3d 1222"),
    ("47-louisiana-inverted", cite("525 U.S. 1", plaintiff="United States", defendant="Louisiana", year=1998),
     lambda: ctx_for("U.S.", 525), "verified", "525 U.S. 1"),
    ("56-not-checked-timeout", cite("516 U.S. 217", plaintiff="Zicherman", defendant="Korean Air Lines Co.", year=1996),
     lambda: ctx_for("U.S.", 516, cases=None, cases_failed="timeout"), "not_checked", "did not answer for"),
    ("57-not-checked-html-200", cite("516 U.S. 217", plaintiff="Zicherman", defendant="Korean Air Lines Co.", year=1996),
     lambda: ctx_for("U.S.", 516, cases=None, cases_failed="unreadable reply"), "not_checked", "unreadable reply"),
    ("57b-not-checked-volumes-failed", cite("516 U.S. 217", plaintiff="Zicherman", defendant="Korean Air Lines Co.", year=1996),
     lambda: RuleContext(slug="us", reporter=META["U.S."], volumes_failed="server error"), "not_checked", "server error"),
    ("58-absent-404-volume", cite("600 U.S. 477", plaintiff="Biden", defendant="Nebraska", year=2023),
     lambda: ctx_for("U.S.", cases=None), "not_in_free_corpus", "volumes after 572"),
    ("60-run-limit", cite("516 U.S. 217", plaintiff="Zicherman", defendant="Korean Air Lines Co.", year=1996),
     lambda: RuleContext(slug="us", reporter=META["U.S."], not_checked_reason="run limit: more than 60 volumes in one filing; run the rest separately"),
     "not_checked", "run limit"),
    ("61-id-skipped", cite("Id. at 230.", kind="id"), lambda: RuleContext(slug=None, reporter=None), "skipped", "short-form citation"),
    ("61b-supra-skipped", cite("Zicherman, supra, at 230", kind="supra"), lambda: RuleContext(slug=None, reporter=None), "skipped", "short-form citation"),
    ("62-statute-skipped", cite("28 U.S.C. § 1332", kind="statute"), lambda: RuleContext(slug=None, reporter=None), "skipped", "statute"),
]


@pytest.mark.parametrize("row_id,cite_in,ctx_factory,expected,fragment", MATRIX, ids=[m[0] for m in MATRIX])
def test_matrix(row_id, cite_in, ctx_factory, expected, fragment):
    result = rules.classify(cite_in, ctx_factory())
    assert isinstance(result, CitationResult)
    assert result.class_ == expected, f"{row_id}: {result.class_} != {expected}; reasons={result.reasons}"
    assert result.reasons, f"{row_id}: no reasons"
    assert has(result, fragment), f"{row_id}: reasons[0]={result.reasons[0]!r} lacks {fragment!r}"
    # reasons are observations: the word "fabricated" never appears in a reason sentence
    assert all("fabricat" not in r.lower() for r in result.reasons), result.reasons
    # the row label is the UI-SPEC §9 label for the class
    assert result.label == rules.label_for_result(result)


# --------------------------------------------------------------------------- #
# Row-specific evidence assertions (AC-2, AC-3 and the §7 notes column)
# --------------------------------------------------------------------------- #

def test_varghese_evidence_ac2():
    c = cite("925 F.3d 1339", plaintiff="Varghese", defendant="China Southern Airlines Co.", year=2019, court="11th Cir.")
    r = rules.classify(c, ctx_for("F.3d", 925))
    assert r.class_ == "likely_fabricated"
    assert r.reasons[0] == (
        "Page 1339 belongs to J.D. v. Azar, 925 F.3d 1291–1349. No case named Varghese in volume 925."
    )
    rc = r.evidence.real_case_at_page
    assert rc is not None
    assert rc.name == "J.D. v. Azar" and rc.first_page == 1291 and rc.last_page == 1349
    assert rc.cite == "925 F.3d 1291"
    assert rc.decision_date == "2019-06-14"
    assert "Varghese" in r.evidence.searched_names
    assert r.evidence.nearest_caption is not None
    assert r.source == "CAP"
    assert r.register_ == "red" and r.mark == "circle-all"
    assert r.label == "Likely not a real case."
    assert r.drawer == "page"


def test_petersen_page_hit_wording():
    c = cite("905 F. Supp. 2d 121", plaintiff="Petersen", defendant="Iran Air", year=2012, court="D.D.C.")
    r = rules.classify(c, ctx_for("F. Supp. 2d", 905))
    assert r.class_ == "likely_fabricated"
    assert r.reasons[0] == (
        "United States v. ISS Marine Services, Inc. begins at page 121; no case named Petersen in volume 905."
    )
    assert r.evidence.real_case_at_page.first_page == 121


def test_miller_partial_hits_dropped_by_circuit():
    c = cite("174 F.3d 366", plaintiff="Miller", defendant="United Airlines, Inc.", year=1999, court="2d Cir.")
    r = rules.classify(c, ctx_for("F.3d", 174))
    assert r.class_ == "likely_fabricated"
    assert "1291" not in r.reasons[0]
    assert "352–368" in r.reasons[0]
    assert r.evidence.real_case_at_page.name == "Greenleaf v. Garlock, Inc."
    # the nearest caption is a Miller case; it is recorded, not used
    assert r.evidence.nearest_caption is not None and "Miller" in r.evidence.nearest_caption.name
    assert r.evidence.name_hit is None


def test_miller_partial_hit_kept_when_circuit_consistent():
    """Same names, court text 3d Cir.: the Third Circuit Miller hit is consistent -> amber, never red."""
    c = cite("174 F.3d 366", plaintiff="Miller", defendant="United Airlines, Inc.", year=1999, court="3d Cir.")
    r = rules.classify(c, ctx_for("F.3d", 174))
    assert r.class_ == "wrong_cite_exists"
    assert "Miller v. City of Philadelphia" in r.reasons[0]
    assert r.evidence.name_hit is not None and r.evidence.name_hit.match == "partial"


def test_zicherman_wrong_page_evidence():
    c = cite("516 U.S. 230", plaintiff="Zicherman", defendant="Korean Air Lines Co.", year=1996)
    r = rules.classify(c, ctx_for("U.S.", 516))
    assert r.class_ == "wrong_cite_exists"
    assert r.reasons[0].startswith("Zicherman ex rel. Estate of Kole v. Korean Air Lines Co. begins at 516 U.S. 217; page 230 is inside it")
    assert r.evidence.real_case_at_page.first_page == 217
    assert r.label == "Exists, but not at this page."
    assert r.mark == "strike-correct"


def test_biden_nebraska_beyond_coverage_ac3():
    c = cite("600 U.S. 477", plaintiff="Biden", defendant="Nebraska", year=2023)
    r = rules.classify(c, ctx_for("U.S."))
    assert r.class_ == "not_in_free_corpus"
    assert r.reasons[0] == "U.S. Reports volumes after 572 are not in the Caselaw Access Project."
    vr = r.evidence.volume_range
    assert vr is not None and vr.vmax == 572 and vr.cited == 600 and vr.held is False
    assert vr.cap_end_year == 2014
    assert r.drawer == "shelf"
    assert r.label == "Not in the free library. Check Westlaw or Lexis."
    # plausibility: bound = 572 + (2026-2014+2)*2*3 = 656 -> 600 is not improbable
    assert r.evidence.plausibility is None


def test_biden_nebraska_verified_by_courtlistener():
    c = cite("600 U.S. 477", plaintiff="Biden", defendant="Nebraska", year=2023)
    r = rules.classify(c, ctx_for("U.S.", courtlistener_status=200))
    assert r.class_ == "verified"
    assert r.source == "CourtListener"
    assert any_reason(r, "confirmed by CourtListener")
    assert r.quote_check is None


def test_beyond_coverage_courtlistener_non_200_stays_coverage():
    c = cite("600 U.S. 477", plaintiff="Biden", defendant="Nebraska", year=2023)
    for status in (404, 429, 400):
        r = rules.classify(c, ctx_for("U.S.", courtlistener_status=status))
        assert r.class_ == "not_in_free_corpus", status


def test_beyond_coverage_improbable_volume_note():
    c = cite("900 U.S. 1", plaintiff="Smith", defendant="Jones", year=2026)
    r = rules.classify(c, ctx_for("U.S."))
    assert r.class_ == "not_in_free_corpus"
    assert r.evidence.plausibility is not None and "improbable" in r.evidence.plausibility


def test_f3d_1000_plausibility_note_mentions_999_and_f4th():
    c = cite("1000 F.3d 1", plaintiff="Smith", defendant="Jones", year=2021, court="9th Cir.")
    r = rules.classify(c, ctx_for("F.3d"))
    assert r.class_ == "not_in_free_corpus"
    assert r.reasons[0] == "F.3d volumes after 935 are not in the Caselaw Access Project."
    assert r.evidence.plausibility is not None
    assert "999" in r.evidence.plausibility and "F.4th" in r.evidence.plausibility
    assert r.evidence.volume_range.vmax == 935


def test_f2d_1000_ceiling_ac3_wording():
    c = cite("1000 F.2d 1", plaintiff="Smith", defendant="Jones", year=1994, court="9th Cir.")
    r = rules.classify(c, _f2d_ctx())
    assert r.class_ == "likely_fabricated"
    assert r.reasons[0] == "F.2d ended at volume 999; volume 1000 cannot exist."
    assert r.evidence.volume_range.vmax == 999


def test_ceiling_requires_closed_edition():
    """F.3d is open in reporters_db: even if CAP held it to 999, 1000 F.3d stays coverage (§3.1)."""
    meta = META["F.3d"]
    ctx = RuleContext(slug="f3d", reporter=meta, volumes=synthetic_volumes(1, 999), vmax=999)
    r = rules.classify(cite("1000 F.3d 1", plaintiff="Smith", defendant="Jones", year=2021), ctx)
    assert r.class_ == "not_in_free_corpus"


def test_fsupp2d_1050_no_arithmetic_error_with_zero_years():
    c = cite("1050 F. Supp. 2d 45", plaintiff="Doe", defendant="Roe", year=2015, court="S.D.N.Y.")
    r = rules.classify(c, ctx_for("F. Supp. 2d"))
    assert r.class_ == "likely_fabricated"
    assert r.reasons[0] == "F. Supp. 2d ended at volume 999; volume 1050 cannot exist."


def test_wl_lexis_neutral_wording_and_evidence():
    r = rules.classify(cite("2019 WL 4639462", plaintiff="Martinez", defendant="Delta Air Lines, Inc.", year=2019), ctx_for("WL"))
    assert r.class_ == "not_in_free_corpus"
    assert r.reasons[0].startswith("Westlaw-only citation; no free text exists.")
    assert r.evidence.cite_type == "specialty_west" and r.source == "none"
    r = rules.classify(cite("2019 U.S. Dist. LEXIS 12345", plaintiff="A", defendant="B", reporter="U.S. Dist. LEXIS"), ctx_for("U.S. Dist. LEXIS"))
    assert r.class_ == "not_in_free_corpus"
    assert r.reasons[0].startswith("Lexis-only citation; no free text exists.")
    r = rules.classify(cite("2013 IL App (1st) 111279", plaintiff="Shaboon", defendant="Egyptair", reporter="IL App (1st)"), ctx_for("IL App (1st)"))
    assert r.class_ == "not_in_free_corpus"
    assert r.evidence.cite_type == "neutral"
    assert r.drawer is None


def test_unrecognized_reporter_wording():
    c = cite("88 Fed. Air Rptr. 3d 412", plaintiff="Alvarez", defendant="Skyline Cargo", year=2018, kind="unrecognized")
    r = rules.classify(c, RuleContext(slug=None, reporter=None))
    assert r.class_ == "unrecognized_reporter"
    assert r.reasons[0] == "No reporter called 'Fed. Air Rptr. 3d' in reporters_db or the Caselaw Access Project."
    assert any_reason(r, "Check the reporter abbreviation by hand")
    assert r.evidence.matched_text == "88 Fed. Air Rptr. 3d 412"
    assert r.label == "No reporter by this name."
    assert r.source == "none" and r.drawer is None


def test_unknown_reporter_without_kind_flag_is_unrecognized_not_red():
    """A full cite whose reporter has neither reporters_db meta nor a slug: unknown reporter, never red."""
    c = cite("88 Fed. Air Rptr. 3d 412", plaintiff="Alvarez", defendant="Skyline Cargo", year=2018)
    r = rules.classify(c, RuleContext(slug=None, reporter=None))
    assert r.class_ == "unrecognized_reporter"


def test_no_slug_step_3b_evidence():
    r = rules.classify(cite("60 F.4th 1", plaintiff="Smith", defendant="Jones", year=2023), ctx_for("F.4th"))
    assert r.class_ == "not_in_free_corpus"
    assert r.reasons[0].startswith("F.4th is not held by the Caselaw Access Project")
    assert r.source == "none"
    r = rules.classify(cite("123 N.Y.S.3d 456", plaintiff="Smith", defendant="Jones", year=2020), ctx_for("N.Y.S.3d"))
    assert r.class_ == "not_in_free_corpus"


def test_missing_volume_within_range():
    r = rules.classify(cite("183 F. Supp. 3d 1", plaintiff="Doe", defendant="Roe", year=2016), _fsupp3d_ctx())
    assert r.class_ == "not_in_free_corpus"
    assert r.evidence.volume_range is not None and r.evidence.volume_range.held is False
    assert r.evidence.volume_range.cited == 183


def test_cases_absent_is_coverage_not_failure():
    ctx = ctx_for("U.S.", 516, cases=None)
    r = rules.classify(cite("516 U.S. 217", plaintiff="Zicherman", defendant="Korean Air Lines Co.", year=1996), ctx)
    assert r.class_ == "not_in_free_corpus"
    assert "cases are not in the free corpus" in r.reasons[0].lower()


def test_volume_index_absent_for_listed_reporter():
    ctx = RuleContext(slug="s-ct", reporter=META["S. Ct."], volumes=None)
    r = rules.classify(cite("140 S. Ct. 1", plaintiff="Smith", defendant="Jones", year=2020), ctx)
    assert r.class_ == "not_in_free_corpus"
    assert "volume index is not published" in r.reasons[0]


def test_not_checked_wording_and_label():
    r = rules.classify(cite("516 U.S. 217", plaintiff="Zicherman", defendant="Korean Air Lines Co.", year=1996),
                       ctx_for("U.S.", 516, cases=None, cases_failed="timeout"))
    assert r.class_ == "not_checked"
    assert r.reasons[0] == "Could not be checked: the free corpus did not answer for 516 U.S. (timeout). Run again or check by hand."
    assert r.label == "Could not reach the free library."
    assert r.register_ == "coverage" and r.drawer is None


def test_year_note_never_changes_class():
    r = rules.classify(cite("470 U.S. 392", plaintiff="Air France", defendant="Saks", year=1986), ctx_for("U.S.", 470))
    assert r.class_ == "verified"
    assert any_reason(r, "the filing gives year 1986; the opinion is dated 1985-03-04")
    assert r.evidence.year_mismatch is not None
    assert r.evidence.year_mismatch.cited == 1986 and r.evidence.year_mismatch.decided == "1985-03-04"
    # the right year: no note
    r = rules.classify(cite("470 U.S. 392", plaintiff="Air France", defendant="Saks", year=1985), ctx_for("U.S.", 470))
    assert r.class_ == "verified" and r.evidence.year_mismatch is None
    # no year: no note
    r = rules.classify(cite("470 U.S. 392", plaintiff="Air France", defendant="Saks"), ctx_for("U.S.", 470))
    assert r.class_ == "verified" and r.evidence.year_mismatch is None
    # row 29: 2010 for Iqbal (2009) is a note only, never red
    r = rules.classify(cite("556 U.S. 662", plaintiff="Ashcroft", defendant="Iqbal", year=2010), ctx_for("U.S.", 556))
    assert r.class_ == "verified" and r.evidence.year_mismatch is not None
    assert any_reason(r, "the filing gives year 2010; the opinion is dated 2009-05-18")
    # wrong page + wrong year on a real case: amber with the note, never red
    r = rules.classify(cite("540 U.S. 700", plaintiff="Olympic Airways", defendant="Husain", year=2007), ctx_for("U.S.", 540))
    assert r.class_ == "wrong_cite_exists" and r.evidence.year_mismatch is not None
    assert r.evidence.name_hit is not None and r.evidence.name_hit.first_page == 644


def test_husain_other_entries_are_orders():
    r = rules.classify(cite("540 U.S. 644", plaintiff="Olympic Airways", defendant="Husain", year=2004), ctx_for("U.S.", 540))
    assert r.class_ == "verified"
    assert sorted(e.first_page for e in r.evidence.other_entries) == [807, 964]
    assert r.evidence.real_case_at_page.first_page == 644


def test_tseng_opinion_beats_order_entry():
    r = rules.classify(cite("525 U.S. 155", plaintiff="El Al Israel Airlines, Ltd.", defendant="Tsui Yuan Tseng", year=1999), ctx_for("U.S.", 525))
    assert r.class_ == "verified"
    assert r.evidence.real_case_at_page.first_page == 155 and r.evidence.real_case_at_page.last_page == 181


def test_azar_6a_before_6b():
    r = rules.classify(cite("925 F.3d 1291", plaintiff="J.D.", defendant="Azar", year=2019, court="D.C. Cir."), ctx_for("F.3d", 925))
    assert r.class_ == "verified"
    assert r.evidence.real_case_at_page.name == "J.D. v. Azar"
    assert r.evidence.running_head is None or "Azar" in r.evidence.running_head


def test_holder_found_via_official_cite():
    r = rules.classify(cite("516 U.S. 545", plaintiff="Holder", defendant="Harlem Men's Shelter", year=1996), ctx_for("U.S.", 516))
    assert r.class_ == "verified"
    assert r.evidence.real_case_at_page.first_page == 803


def test_nonstandard_page_strings_parse():
    idx = rules.index_volume(load_cases("f3d", 174))
    miller = [c for c in idx.cases if c.name == "Miller v. City of Philadelphia"][0]
    assert (miller.first_page, miller.last_page) == (368, 391)
    griffith = [c for c in idx.cases if c.name == "Griffith v. United States"][0]
    assert (griffith.first_page, griffith.last_page) == (1222, 1235)
    idx = rules.index_volume(load_cases("us", 525))
    louisiana = [c for c in idx.cases if c.name == "United States v. Louisiana"][0]
    assert (louisiana.first_page, louisiana.last_page) == (1, 1)


def test_dup_volume_rows_and_case_dedupe():
    cases = load_cases("f3d", 174)
    doubled = cases + [dict(c) for c in cases]
    idx = rules.index_volume(doubled)
    assert len(idx.cases) == len({c["id"] for c in cases})
    vols = {"138": [{"volume_number": "138", "start_year": 0, "end_year": 0}, {"volume_number": "138", "start_year": 0, "end_year": 0}]}
    ctx = RuleContext(slug="a3d", reporter=ReporterMeta(reporter="A.3d", cite_type="state", slug="a3d"), volumes=vols, vmax=138,
                      cases=[case_row("Smith v. Jones", 1, 10, cid=1), case_row("Smith v. Jones", 1, 10, cid=1), case_row("Roe v. Wade", 11, 20, cid=2)])
    r = rules.classify(cite("138 A.3d 11", plaintiff="Roe", defendant="Wade", year=2016), ctx)
    assert r.class_ == "verified"


def test_no_names_page_hit_verifies_and_inside_span_is_amber():
    r = rules.classify(cite("516 U.S. 217", year=1996), ctx_for("U.S.", 516))
    assert r.class_ == "verified"
    assert "no party names" in r.reasons[0]
    r = rules.classify(cite("516 U.S. 230", year=1996), ctx_for("U.S.", 516))
    assert r.class_ == "wrong_cite_exists"
    assert "which begins at 217" in r.reasons[0]


def test_gap_hole_no_names_is_coverage():
    r = rules.classify(cite("556 U.S. 1104", year=2009), ctx_for("U.S.", 556))
    assert r.class_ == "not_in_free_corpus"
    assert r.evidence.volume_range is not None and r.evidence.volume_range.held is True
    assert r.drawer == "shelf"


def test_gap_hole_with_names_is_coverage_never_red():
    r = rules.classify(cite("556 U.S. 1104", plaintiff="Nobody", defendant="Anyone", year=2009), ctx_for("U.S.", 556))
    assert r.class_ == "not_in_free_corpus"
    assert "no case named Nobody or Anyone" in r.reasons[0]


def test_gap_beyond_end_is_coverage_never_red():
    r = rules.classify(cite("550 U.S. 901", plaintiff="Nobody", defendant="Anyone", year=2007), ctx_for("U.S.", 550))
    assert r.class_ == "not_in_free_corpus"
    assert "ends at page 661; page 901 is beyond it" in r.reasons[0]
    assert r.evidence.volume_range.max_last_page == 661


def test_us_orders_page_rule():
    r = rules.classify(cite("516 U.S. 801", plaintiff="Nobody", defendant="Anyone", year=1996), ctx_for("U.S.", 516))
    assert r.class_ == "not_in_free_corpus"
    assert "Voinovich v. Quilter" in r.reasons[0]
    # a one-page entry below 801 in U.S. Reports is also an orders page
    idx = rules.index_volume(load_cases("us", 525))
    one_page = [c for c in idx.cases if c.first_page == c.last_page and c.first_page < 801]
    assert one_page, "fixture check: 525 U.S. has one-page entries below 801"
    p = one_page[0].first_page
    r = rules.classify(cite(f"525 U.S. {p}", plaintiff="Nobody", defendant="Anyone", year=1999), ctx_for("U.S.", 525))
    assert r.class_ == "not_in_free_corpus"


def test_all_generic_parties_never_red():
    """Generic-only captions cannot be searched for; the safer reading routes them like no_names."""
    r = rules.classify(cite("905 F. Supp. 2d 121", plaintiff="United States", defendant="Doe", year=2012), ctx_for("F. Supp. 2d", 905))
    assert r.class_ in ("verified", "wrong_cite_exists")
    r = rules.classify(cite("925 F.3d 1339", plaintiff="State", defendant="Roe", year=2019), ctx_for("F.3d", 925))
    assert r.class_ == "wrong_cite_exists"


def test_pin_cite_note_never_a_class():
    r = rules.classify(cite("516 U.S. 217", plaintiff="Zicherman", defendant="Korean Air Lines Co.", year=1996, pin_cite="at 230"), ctx_for("U.S.", 516))
    assert r.class_ == "verified" and r.pincite_unverified is True
    assert any_reason(r, "not verifiable: the free corpus text has no page numbers")
    assert r.label.endswith("Pin page not checked.")


def test_edition_year_note_only():
    # Marbury 1803: U.S. edition from 1875 in reporters_db but CAP holds us/5 -> inside the merged range, no note
    r = rules.classify(cite("5 U.S. 137", plaintiff="Marbury", defendant="Madison", year=1803), _us5_ctx())
    assert r.class_ == "verified" and not any_reason(r, "outside the years")
    # a year far outside both sources is a note, never a class
    r = rules.classify(cite("5 U.S. 137", plaintiff="Marbury", defendant="Madison", year=1700), _us5_ctx())
    assert r.class_ == "verified" and any_reason(r, "outside the years both sources give")
    assert r.evidence.edition_range is not None
    # row 42: 999 F. Supp. (1998) — reporters_db ends 1988 but CAP runs to 1998
    r = rules.classify(cite("999 F. Supp. 1", plaintiff="Smith", defendant="Jones", year=1998), _fsupp_999_ctx())
    assert r.class_ in ("verified", "wrong_cite_exists", "not_in_free_corpus")
    assert not any_reason(r, "outside the years both sources give")


def test_result_shape_and_cite_text():
    c = cite("516 U.S. 217", plaintiff="Zicherman", defendant="Korean Air Lines Co.", year=1996)
    r = rules.classify(c, ctx_for("U.S.", 516), row=7)
    assert r.row == 7
    assert r.cite_text == "Zicherman v. Korean Air Lines Co., 516 U.S. 217 (1996)"
    assert r.citation == c
    d = r.model_dump(by_alias=True)
    assert d["class"] == "verified" and d["register"] == "green"
    r2 = rules.classify(c, ctx_for("U.S.", 516), row=3, cite_text="custom text")
    assert r2.cite_text == "custom text" and r2.row == 3


def test_links_flow_into_evidence():
    links = ["https://static.case.law/us/VolumesMetadata.json", "https://static.case.law/us/516/CasesMetadata.json"]
    r = rules.classify(cite("516 U.S. 217", plaintiff="Zicherman", defendant="Korean Air Lines Co.", year=1996), ctx_for("U.S.", 516, links=links))
    assert r.evidence.links == links


def test_classify_is_pure():
    c = cite("516 U.S. 217", plaintiff="Zicherman", defendant="Korean Air Lines Co.", year=1996)
    ctx = ctx_for("U.S.", 516)
    before = json.dumps(ctx.cases, sort_keys=True)
    a = rules.classify(c, ctx)
    b = rules.classify(c, ctx)
    assert a.model_dump(by_alias=True) == b.model_dump(by_alias=True)
    assert json.dumps(ctx.cases, sort_keys=True) == before


# --------------------------------------------------------------------------- #
# apply_quote_check (rows 15, 16, 51–55) and parallel cites (rows 48, 49)
# --------------------------------------------------------------------------- #

def _verified_zicherman() -> CitationResult:
    return rules.classify(cite("516 U.S. 217", plaintiff="Zicherman", defendant="Korean Air Lines Co.", year=1996), ctx_for("U.S.", 516))


def test_quote_not_found_row15():
    r = _verified_zicherman()
    qc = QuoteCheck(status="not_found", quote="A claim has facial plausibility ...", similarity=90.5, segments=1,
                    diff=[DiffToken(filed="alleges", opinion="pleads"), DiffToken(filed="permits", opinion="allows"),
                          DiffToken(filed="a", opinion="the"), DiffToken(filed="responsible", opinion="liable")])
    out = rules.apply_quote_check(r, qc, closest_passage={"text": "A claim has facial plausibility when the plaintiff pleads ...", "similarity": 90.5, "status": "not_found"})
    assert out.class_ == "quote_not_found"
    assert has(out, "was not found in the opinion text; the closest passage is 9")
    assert out.quote_check == qc
    assert out.evidence.closest_passage is not None and out.evidence.closest_passage.similarity == 90.5
    assert out.label == "Found, but this quote is not in the opinion."
    assert out.mark == "underline-quote" and out.register_ == "amber"
    # the lookup sentence is kept as a later reason
    assert any_reason(out, "Found in the free corpus")
    # the input is not mutated
    assert r.class_ == "verified"


def test_quote_differs_row16_and_51():
    r = _verified_zicherman()
    qc = QuoteCheck(status="differs", quote="But where the text is clear ...", similarity=81.2, segments=1,
                    diff=[DiffToken(filed="authority", opinion="power"), DiffToken(filed="add", opinion="insert"), DiffToken(filed="exception", opinion="amendment")])
    out = rules.apply_quote_check(r, qc)
    assert out.class_ == "quote_not_found"
    assert has(out, "differs from the opinion text in 3 word(s)")
    assert "'authority' → 'power'" in out.reasons[0]
    qc1 = QuoteCheck(status="differs", quote="...", similarity=96.0, diff=[DiffToken(filed="respondents", opinion="petitioners")])
    out = rules.apply_quote_check(r, qc1)
    assert has(out, "differs from the opinion text in 1 word(s): 'respondents' → 'petitioners'")


def test_quote_verbatim_keeps_verified_rows53_54():
    r = _verified_zicherman()
    out = rules.apply_quote_check(r, QuoteCheck(status="verbatim", quote="...", similarity=100.0, segments=2))
    assert out.class_ == "verified"
    assert any_reason(out, "quoted passage found in the opinion text")
    assert any_reason(out, "omission marked by ellipsis")
    assert out.label == "Found. Quote matches."
    out = rules.apply_quote_check(r, QuoteCheck(status="verbatim", quote="...", similarity=100.0, segments=1))
    assert not any_reason(out, "ellipsis")


def test_quote_check_only_applies_to_verified_rows():
    amber = rules.classify(cite("516 U.S. 230", plaintiff="Zicherman", defendant="Korean Air Lines Co.", year=1996), ctx_for("U.S.", 516))
    qc = QuoteCheck(status="not_found", quote="x", similarity=40.0)
    out = rules.apply_quote_check(amber, qc)
    assert out.class_ == "wrong_cite_exists"
    assert out.quote_check is not None and out.quote_check.status == "not_checked"
    r = _verified_zicherman()
    assert rules.apply_quote_check(r, None).class_ == "verified"
    out = rules.apply_quote_check(r, QuoteCheck(status="not_checked"))
    assert out.class_ == "verified"


def test_parallel_cites_rows48_49():
    r = _verified_zicherman()
    out = rules.apply_parallel_cites(r, ["116 S. Ct. 629", "133 L. Ed. 2d 596"])
    assert out.class_ == "verified"
    assert out.parallel_cites == ["116 S. Ct. 629 — confirmed by the CAP record", "133 L. Ed. 2d 596 — confirmed by the CAP record"]
    out = rules.apply_parallel_cites(r, ["116 S. Ct. 926"])
    assert out.class_ == "verified"
    assert any_reason(out, "parallel cite 116 S. Ct. 926 differs from the record's 116 S. Ct. 629")
    assert out.evidence.parallel_mismatch is not None
    out = rules.apply_parallel_cites(r, ["99 A.L.R. 1"])
    assert out.parallel_cites == ["99 A.L.R. 1 — not listed in the CAP record; not checked"]


def test_best_class_order():
    assert rules.best_class(["not_in_free_corpus", "verified", "likely_fabricated"]) == "verified"
    assert rules.best_class(["likely_fabricated", "not_in_free_corpus"]) == "not_in_free_corpus"
    assert rules.best_class(["wrong_cite_exists", "quote_not_found"]) == "quote_not_found"


# --------------------------------------------------------------------------- #
# names.py (§5)
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("raw,expected", [
    ("Garlock, Inc.", "garlock"),
    ("ISS Marine Servs.", "iss marine services"),
    ("ISS Marine Services, Inc.", "iss marine services"),
    ("Bell Atl. Corp.", "bell atlantic"),
    ("Bell Atlantic Corp.", "bell atlantic"),
    ("Estate  Durden", "durden"),
    ("Estate of Durden", "durden"),
    ("In re Papst Licensing GmbH & Co. KG Litigation", "papst licensing gmbh and company kg litigation"),
    ("Korean Air Lines Co.", "korean air lines"),
    ("Korean Air Lines, Ltd.", "korean air lines"),
    ("El Al Israel Airlines, Ltd.", "el al israel airlines"),
    ("Sec'y of Health & Human Servs.", "secretary of health and human services"),
    ("Ex parte Young", "young"),
    ("Delta Air Lines, Inc., et al.", "delta air lines"),
])
def test_normalize_party(raw, expected):
    assert names.normalize_party(raw) == expected


@pytest.mark.parametrize("party,generic", [
    ("United States", True), ("Doe", True), ("Roe", True), ("Iran", True), ("Saks", True), ("J.D.", True),
    ("State", True), ("City of Philadelphia", False), ("Varghese", False), ("Garlock, Inc.", False),
    ("Estate of Durden", False), ("Inc.", True), ("", True), (None, True),
])
def test_is_generic(party, generic):
    assert names.is_generic(party) is generic


@pytest.mark.parametrize("pl,df,caption,expected", [
    ("Greenleaf", "Garlock, Inc.", "Greenleaf v. Garlock, Inc.", "full"),
    ("Doe", "Garlock", "Greenleaf v. Garlock, Inc.", "partial"),
    ("Zicherman", "Korean Air Lines Co.", "Zicherman ex rel. Estate of Kole v. Korean Air Lines Co.", "full"),
    ("Air France", "Saks", "Air France v. Saks", "full"),
    ("United States", "Louisiana", "United States v. Louisiana", "full"),
    ("United States", "Varghese", "United States v. ISS Marine Services, Inc.", "none"),
    ("United States", "Iran Air", "United States v. ISS Marine Services, Inc.", "none"),
    ("Petersen", "Iran Air", "United States v. ISS Marine Services, Inc.", "none"),
    ("Varghese", "China Southern Airlines Co.", "J.D. v. Azar", "none"),
    ("Doe", "Becerra", "J.D. v. Azar", "none"),
    (None, "Papst Licensing GmbH & Co. KG Litigation", "In re Papst Licensing GmbH & Co. KG Litigation", "full"),
    (None, None, "J.D. v. Azar", "no_names"),
    ("Miller", "United Airlines, Inc.", "Miller v. City of Philadelphia", "partial"),
    ("Miller", "United Airlines, Inc.", "Miller v. Woodharbor Molding & Millworks, Inc.", "partial"),
    ("Holder", "Harlem Men's Shelter", "Holder v. Harlem Men's Shelter", "full"),
    ("Olympic Airways", "Husain", "Olympic Airways v. Husain", "full"),
    (None, "United States", "United States v. Louisiana", "none"),
])
def test_match(pl, df, caption, expected):
    c = CitationInput(text="1 X 1", plaintiff=pl, defendant=df)
    assert names.match(c, {"name_abbreviation": caption}) == expected
    assert names.match(c, caption) == expected


def test_scores_measured_in_spec():
    assert names.score("Garlock", "Garlock, Inc.") == 100
    assert names.score("ISS Marine Servs.", "ISS Marine Services, Inc.") == 100
    assert names.score("Bell Atl. Corp.", "Bell Atlantic Corp.") == 100
    assert names.score("Iran Air", "ISS Marine Services, Inc.") < 40
    assert names.score("Becerra", "Azar") < 40


@pytest.mark.parametrize("filed,cap,consistent", [
    ("2d Cir.", "United States Court of Appeals for the Third Circuit", False),
    ("3d Cir.", "United States Court of Appeals for the Third Circuit", True),
    ("2d Cir.", "United States Court of Appeals for the Eighth Circuit", False),
    ("D.C. Cir.", "Court of Appeals of the District of Columbia", True),
    ("11th Cir.", "Court of Appeals of the District of Columbia", False),
    ("Fed. Cir.", "United States Court of Appeals for the Federal Circuit", True),
    ("ca2", "United States Court of Appeals for the Second Circuit", True),
    ("cadc", "Court of Appeals of the District of Columbia", True),
    ("S.D.N.Y.", "United States District Court for the Southern District of New York", True),
    (None, "United States Court of Appeals for the Third Circuit", True),
    ("2d Cir.", None, True),
    ("9th Cir.", "United States Court of Appeals for the Ninth", True),
])
def test_court_consistent(filed, cap, consistent):
    assert names.court_consistent(filed, cap) is consistent


# --------------------------------------------------------------------------- #
# reporter_meta helper (T05 builds RuleContext.reporter from it)
# --------------------------------------------------------------------------- #

def test_reporter_meta_from_reporters_db():
    cap_entry = {"short_name": "F.3d", "start_year": 1990, "end_year": 2019, "slug": "f3d"}
    m = rules.reporter_meta("F.3d", cap_entry)
    assert m.cite_type == "federal" and m.edition_start == 1993 and m.edition_end is None
    assert m.cap_start_year == 1990 and m.cap_end_year == 2019 and m.slug == "f3d"
    assert m.successor == "F.4th" and m.successor_start == "2021-01-01"
    m = rules.reporter_meta("F. Supp. 2d", {"slug": "f-supp-2d", "start_year": 1982, "end_year": 2014})
    assert m.edition_end == 2014 and m.successor == "F. Supp. 3d"
    m = rules.reporter_meta("F.2d", None)
    assert m.edition_end == 1993 and m.slug is None
    assert rules.reporter_meta("WL", None).cite_type == "specialty_west"
    assert rules.reporter_meta("IL App (1st)", None).cite_type == "neutral"
    assert rules.reporter_meta("Fed. Air Rptr. 3d", None) is None


# --------------------------------------------------------------------------- #
# The promise: no real case is ever likely_fabricated
# --------------------------------------------------------------------------- #

_PAREN = re.compile(r"\(([^()]*?)\s*((?:1[7-9]|20)\d{2})\)\s*$")


def _seed_cite(item: dict) -> CitationInput:
    """The seed item as extract.py would hand it over: parties split, court text from the parenthetical (§1.2)."""
    pl, df = parties(item["parties"])
    m = _PAREN.search(item["cite_text"])
    court = m.group(1).strip() or None if m else None
    return CitationInput(text=f"{item['volume']} {item['reporter']} {item['page']}", volume=item["volume"], reporter=item["reporter"],
                         page=item["page"], year=item.get("year"), court=court, plaintiff=pl, defendant=df)


def _seed_ctx(item: dict) -> RuleContext:
    reporter = item["reporter"]
    meta = META.get(reporter)
    if meta is None:
        return RuleContext(slug=None, reporter=None)
    if meta.slug and (CACHE / meta.slug / str(item["volume"]) / "CasesMetadata.json").exists():
        return ctx_for(reporter, item["volume"])
    return ctx_for(reporter)


def test_seed_ground_truth_classes():
    scored = [i for i in GROUND_TRUTH["items"] if i.get("expected_class")]
    assert len(scored) == 20
    correct = 0
    real_red = 0
    for item in scored:
        r = rules.classify(_seed_cite(item), _seed_ctx(item))
        expected = item["expected_class"]
        accepted = set(item["accepted_classes"])
        real = item.get("real_case_at_page") is not None and expected != "likely_fabricated"
        if real and r.class_ == "likely_fabricated":
            real_red += 1
        # quote rows resolve to quote_not_found only after quotes.py runs; the lookup half must verify
        if expected == "quote_not_found":
            accepted = {"verified"}
        if r.class_ in accepted:
            correct += 1
        else:
            pytest.fail(f"{item['id']}: {r.class_} not in {accepted}; reasons={r.reasons}")
    assert real_red == 0
    assert correct == 20


def test_every_real_case_at_its_own_page_is_never_red():
    """Every case in every cached volume, cited by its own caption at its first page: never likely_fabricated."""
    red = []
    for slug, reporter in (("us", "U.S."), ("f3d", "F.3d"), ("f-supp-2d", "F. Supp. 2d")):
        for vol_dir in sorted((CACHE / slug).iterdir()):
            if not vol_dir.is_dir():
                continue
            volume = int(vol_dir.name)
            ctx = ctx_for(reporter, volume)
            idx = rules.index_volume(ctx.cases)
            for case in idx.cases:
                pl, df = parties(case.name)
                c = CitationInput(text=f"{volume} {reporter} {case.first_page}", volume=volume, reporter=reporter,
                                  page=case.first_page, plaintiff=pl, defendant=df, year=int(case.decision_date[:4]))
                r = rules.classify(c, ctx)
                if r.class_ == "likely_fabricated":
                    red.append((volume, reporter, case.first_page, case.name, r.reasons[0]))
    assert red == []


def test_real_case_wrong_page_is_never_red():
    """A sample of real captions cited at a wrong page inside the volume: amber or coverage, never red."""
    red = []
    for slug, reporter in (("us", "U.S."), ("f3d", "F.3d"), ("f-supp-2d", "F. Supp. 2d")):
        for vol_dir in sorted((CACHE / slug).iterdir()):
            if not vol_dir.is_dir():
                continue
            volume = int(vol_dir.name)
            ctx = ctx_for(reporter, volume)
            idx = rules.index_volume(ctx.cases)
            opinions = [c for c in idx.cases if c.last_page - c.first_page >= 3]
            for case in opinions[::max(1, len(opinions) // 12)]:
                pl, df = parties(case.name)
                for page in (case.first_page + 2, case.first_page + 400):
                    c = CitationInput(text=f"{volume} {reporter} {page}", volume=volume, reporter=reporter,
                                      page=page, plaintiff=pl, defendant=df, year=1900)
                    r = rules.classify(c, ctx)
                    if r.class_ == "likely_fabricated":
                        red.append((volume, reporter, page, case.name, r.reasons[0]))
    assert red == []


def test_matrix_real_rows_never_red():
    real_rows = {"22-", "23-", "24-", "27-", "28-", "29-", "30-", "33-", "34-", "42-", "45-", "46-", "47-"}
    for row_id, cite_in, ctx_factory, expected, _ in MATRIX:
        if row_id[:3] in real_rows:
            r = rules.classify(cite_in, ctx_factory())
            assert r.class_ != "likely_fabricated", row_id


def test_classify_never_raises_on_odd_input():
    odd = [
        CitationInput(text="", kind="full"),
        CitationInput(text="925 F.3d", volume=925, reporter="F.3d", page=None),
        CitationInput(text="0 U.S. 0", volume=0, reporter="U.S.", page=0, plaintiff="A", defendant="B"),
        CitationInput(text="516 U.S. 99999", volume=516, reporter="U.S.", page=99999, plaintiff="Smith", defendant="Jones"),
    ]
    for c in odd:
        r = rules.classify(c, ctx_for("U.S.", 516))
        assert r.class_ != "likely_fabricated"
        assert r.reasons
