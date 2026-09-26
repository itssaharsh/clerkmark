"""T03 — citememo/extract.py: PDF text, eyecite extraction, quote attachment.

Offline: every fixture is the committed seed (seed/sample-motion.pdf, .txt,
seed/ground_truth.json) or a PDF generated in tmp_path with fpdf2.
"""

from __future__ import annotations

import io
import json
import re
from pathlib import Path

import pytest

from citememo import extract
from citememo.extract import NoTextLayer, extract_citations, pdf_to_text
from citememo.models import CitationInput

ROOT = Path(__file__).resolve().parents[1]
SEED_PDF = ROOT / "seed" / "sample-motion.pdf"
SEED_TXT = ROOT / "seed" / "sample-motion.txt"
GROUND_TRUTH = json.loads((ROOT / "seed" / "ground_truth.json").read_text())


def _norm(s: str) -> str:
    """Whitespace-collapsed, trailing punctuation stripped: the comparison the brief calls 'normalized text'."""
    return re.sub(r"\s+", " ", s).strip().rstrip(".;,")


def _pdf_bytes(lines: list[str]) -> bytes:
    from fpdf import FPDF

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font("Helvetica", size=11)
    for line in lines:
        pdf.cell(0, 6, text=line, new_x="LMARGIN", new_y="NEXT")
    return bytes(pdf.output())


@pytest.fixture(scope="module")
def seed_text() -> str:
    return pdf_to_text(SEED_PDF.read_bytes())


@pytest.fixture(scope="module")
def seed_cites(seed_text: str) -> list[CitationInput]:
    return extract_citations(seed_text)


def _by_core(cites: list[CitationInput], core: str) -> CitationInput:
    hits = [c for c in cites if _norm(c.text) == core]
    assert len(hits) == 1, f"{core}: {[(c.text, c.kind) for c in hits]}"
    return hits[0]


# --------------------------------------------------------------------------- #
# pdf_to_text
# --------------------------------------------------------------------------- #


def test_pdf_to_text_pages_joined_by_form_feed(seed_text: str) -> None:
    assert seed_text.count("\f") == 5  # six pages
    assert "Air France v. Saks" in seed_text
    assert isinstance(seed_text, str)


def test_pdf_to_text_repairs_line_break_hyphenation_conservatively(tmp_path: Path) -> None:
    data = _pdf_bytes(
        [
            "only enough facts to state a claim to relief that is plausi-",
            "ble on its face. Plaintiff Marisol Okonkwo-",
            "Reyes appeared pro se before the court in this matter.",
        ]
    )
    text = pdf_to_text(data)
    assert "plausible on its face" in text  # lowercase-lowercase: joined
    assert "OkonkwoReyes" not in text  # capitalised second half: hyphen kept
    assert "Okonkwo-" in text and "Reyes" in text


def test_pdf_to_text_raises_no_text_layer_for_blank_pdf() -> None:
    from fpdf import FPDF

    pdf = FPDF()
    pdf.add_page()
    with pytest.raises(NoTextLayer):
        pdf_to_text(bytes(pdf.output()))


def test_pdf_to_text_raises_no_text_layer_when_under_40_chars() -> None:
    with pytest.raises(NoTextLayer):
        pdf_to_text(_pdf_bytes(["short"]))


# --------------------------------------------------------------------------- #
# extract_citations on the seed: the 20 ground-truth citations
# --------------------------------------------------------------------------- #


def test_seed_pdf_yields_every_ground_truth_cite_text(seed_cites: list[CitationInput]) -> None:
    have = {_norm(c.cite_text) for c in seed_cites}
    missing = [it["cite_text"] for it in GROUND_TRUTH["items"] if _norm(it["cite_text"]) not in have]
    assert missing == [], f"missing cite_text: {missing}\nhave: {sorted(have)}"


def test_seed_pdf_yields_twenty_full_citations(seed_cites: list[CitationInput]) -> None:
    full = [c for c in seed_cites if c.kind == "full"]
    # 19 recognised seed citations + Mata v. Avianca from the page-1 label
    assert len(full) == 20, [c.text for c in full]
    assert _norm(_by_core(seed_cites, "678 F. Supp. 3d 443").cite_text) == _norm(GROUND_TRUTH["extra_in_label"]["cite_text"])


def test_seed_pdf_skipped_kinds(seed_cites: list[CitationInput]) -> None:
    ids = [c for c in seed_cites if c.kind == "id"]
    statutes = [c for c in seed_cites if c.kind == "statute"]
    assert len(ids) == 1 and ids[0].pin_cite == "at 230"
    assert len(statutes) == 1 and _norm(statutes[0].text) == "28 U.S.C. § 1332"
    assert not [c for c in seed_cites if c.kind in ("supra", "short")]


def test_seed_pdf_unrecognized_reporter_alvarez(seed_cites: list[CitationInput]) -> None:
    unrec = [c for c in seed_cites if c.kind == "unrecognized"]
    assert len(unrec) == 1
    a = unrec[0]
    assert a.reporter == "Fed. Air Rptr. 3d"
    assert a.volume == 88 and a.page == 412 and a.year == 2018
    assert _norm(a.text) == "88 Fed. Air Rptr. 3d 412"
    assert a.plaintiff == "Alvarez" and a.defendant == "Skyline Cargo"
    assert _norm(a.cite_text) == "Alvarez v. Skyline Cargo, 88 Fed. Air Rptr. 3d 412 (2018)"


def test_seed_quotes_attach_to_the_right_citation(seed_cites: list[CitationInput]) -> None:
    by_text = {_norm(c.cite_text): c for c in seed_cites}
    for item in GROUND_TRUTH["items"]:
        c = by_text[_norm(item["cite_text"])]
        if item["quote"]:
            assert c.quotes == [item["quote"]], (item["id"], c.quotes)
        else:
            assert c.quotes == [], (item["id"], c.quotes)
    # the label's Mata cite carries no quote either
    assert by_text[_norm(GROUND_TRUTH["extra_in_label"]["cite_text"])].quotes == []


def test_seed_fields_volume_reporter_page_year_court_parties(seed_cites: list[CitationInput]) -> None:
    saks = _by_core(seed_cites, "470 U.S. 392")
    assert (saks.volume, saks.reporter, saks.page, saks.year) == (470, "U.S.", 392, 1985)
    assert saks.court == "scotus"
    assert (saks.plaintiff, saks.defendant) == ("Air France", "Saks")
    assert saks.pin_cite is None

    floyd = _by_core(seed_cites, "499 U.S. 530")
    assert floyd.year == 1991  # eyecite metadata.year says 2019 here; the parenthetical regex wins

    greenleaf = _by_core(seed_cites, "174 F.3d 352")
    assert greenleaf.court == "3d Cir."  # eyecite gives None for 3d Cir.; parenthetical text used
    assert greenleaf.year == 1999

    durden = _by_core(seed_cites, "2017 WL 2418825")
    assert durden.reporter == "WL" and durden.cite_type == "specialty_west"
    assert durden.defendant == "KLM Royal Dutch Airlines"
    assert durden.year == 2017

    shaboon = _by_core(seed_cites, "2013 IL App (1st) 111279")
    assert shaboon.reporter == "IL App (1st)" and shaboon.cite_type == "neutral"
    assert shaboon.year == 2013  # no parenthetical; eyecite's 2019 (borrowed from Martinez) must not leak in
    assert (shaboon.plaintiff, shaboon.defendant) == ("Shaboon", "Egyptair")

    mata = _by_core(seed_cites, "678 F. Supp. 3d 443")
    assert mata.reporter == "F. Supp. 3d" and mata.year == 2023 and mata.court == "nysd"


def test_seed_spans_point_into_cleaned_text_and_filing_page(seed_text: str, seed_cites: list[CitationInput]) -> None:
    cleaned, _ = extract.clean_filing_text(seed_text)
    for c in seed_cites:
        assert c.span is not None
        s, e = c.span
        assert cleaned[s:e] == c.text
    loper = _by_core(seed_cites, "603 U.S. 369")
    expected_page = seed_text[: seed_text.index("Loper Bright")].count("\f") + 1
    assert loper.filing_page == expected_page
    saks = _by_core(seed_cites, "470 U.S. 392")
    assert saks.filing_page == seed_text[: seed_text.index("Air France v. Saks")].count("\f") + 1
    assert _by_core(seed_cites, "678 F. Supp. 3d 443").filing_page == 1


def test_seed_txt_matches_pdf_extraction() -> None:
    cites = extract_citations(SEED_TXT.read_text())
    have = {_norm(c.cite_text) for c in cites}
    for item in GROUND_TRUTH["items"]:
        assert _norm(item["cite_text"]) in have, item["cite_text"]
    assert all(c.filing_page == 1 for c in cites)


def test_no_duplicates_in_seed(seed_cites: list[CitationInput]) -> None:
    assert all(c.duplicate_of is None for c in seed_cites)


# --------------------------------------------------------------------------- #
# Small texts: kinds, history, duplicates, quotes, the catch regex
# --------------------------------------------------------------------------- #


def test_kinds_id_supra_short() -> None:
    text = (
        "Zicherman v. Korean Air Lines Co., 516 U.S. 217, 225 (1996). Id. at 230. "
        "See Zicherman, 516 U.S. at 230. Smith, supra, at 12."
    )
    cites = extract_citations(text)
    kinds = [c.kind for c in cites]
    assert kinds == ["full", "id", "short", "supra"]
    assert cites[0].pin_cite == "225"
    assert cites[1].pin_cite == "at 230"
    assert cites[2].pin_cite == "230"
    assert cites[2].volume == 516 and cites[2].reporter == "U.S."


def test_statute_kind() -> None:
    cites = extract_citations("The amount in controversy exceeds $75,000 under 28 U.S.C. § 1332.")
    assert [c.kind for c in cites] == ["statute"]
    assert cites[0].reporter == "U.S.C."


def test_subsequent_history_is_marked() -> None:
    text = "Smith v. Jones, 100 F.3d 1, 5 (2d Cir. 1996), cert. denied, 550 U.S. 901 (2007)."
    cites = extract_citations(text)
    assert [c.kind for c in cites] == ["full", "full"]
    first, second = cites
    assert first.history is None and first.pin_cite == "5" and first.year == 1996
    assert second.history is not None and second.history.startswith("cert. denied")
    assert second.volume == 550 and second.page == 901 and second.year == 2007
    assert second.plaintiff is None and second.defendant is None
    aff = extract_citations("Doe v. Roe, 10 F. Supp. 2d 5 (S.D.N.Y. 1998), aff'd, 200 F.3d 100 (2d Cir. 1999).")
    assert aff[1].history == "aff'd"


def test_duplicate_full_cite_points_at_first_occurrence() -> None:
    text = (
        "Air France v. Saks, 470 U.S. 392 (1985). The rule is settled. "
        "Olympic Airways v. Husain, 540 U.S. 644 (2004). "
        "See also Air France v. Saks, 470 U.S. 392, 405 (1985)."
    )
    cites = extract_citations(text)
    assert [c.kind for c in cites] == ["full"] * 3
    assert cites[0].duplicate_of is None
    assert cites[1].duplicate_of is None
    assert cites[2].duplicate_of == 0
    assert cites[2].pin_cite == "405"


def test_quote_before_citation_straight_and_curly() -> None:
    q = "Any injury is the product of a chain of causes, and we require only that some link was unusual."
    for open_, close in (('"', '"'), ("“", "”")):
        text = f"The Court said: {open_}{q}{close} Air France v. Saks, 470 U.S. 392 (1985)."
        cites = extract_citations(text)
        assert cites[0].quotes == [q]


def test_quote_shorter_than_25_chars_is_not_attached() -> None:
    text = 'The cart was an "accident" under the Convention. Air France v. Saks, 470 U.S. 392 (1985).'
    assert extract_citations(text)[0].quotes == []


def test_quote_farther_than_400_chars_is_not_attached() -> None:
    q = "This is a quoted passage that is certainly longer than twenty-five characters."
    filler = "word " * 90  # 450 chars
    text = f'"{q}" {filler}Air France v. Saks, 470 U.S. 392 (1985).'
    assert extract_citations(text)[0].quotes == []


def test_quote_belongs_to_the_nearest_following_citation_only() -> None:
    q1 = "Here, in contrast, we do not require heightened fact pleading of specifics."
    q2 = "A claim has facial plausibility when the plaintiff alleges factual content."
    text = (
        f'The Court said: "{q1}" Bell Atlantic Corp. v. Twombly, 550 U.S. 544 (2007). '
        f'Two years later: "{q2}" Ashcroft v. Iqbal, 556 U.S. 662 (2009).'
    )
    cites = extract_citations(text)
    assert cites[0].quotes == [q1]
    assert cites[1].quotes == [q2]


def test_quote_after_quoting_parenthetical() -> None:
    q = "the subsequent mootness of individual claims does not terminate litigation"
    text = f'J.D. v. Azar, 925 F.3d 1291, 1300 (D.C. Cir. 2019) (quoting "{q}"). Next sentence.'
    cites = extract_citations(text)
    assert cites[0].quotes == [q]


def test_quote_keeps_alterations_and_ellipses() -> None:
    q = "[A]ny injury is the product of a chain of causes . . . external to the passenger."
    text = f'"{q}" Air France v. Saks, 470 U.S. 392 (1985).'
    assert extract_citations(text)[0].quotes == [q]


def test_quote_attached_to_id_does_not_leak_forward() -> None:
    q = "the applicable domestic law, and not the treaty itself, defines the compensable harm"
    text = (
        f'Zicherman v. Korean Air Lines Co., 516 U.S. 217 (1996). "{q}" Id. at 230. '
        "See also Air France v. Saks, 470 U.S. 392 (1985)."
    )
    cites = extract_citations(text)
    assert cites[1].kind == "id" and cites[1].quotes == [q]
    assert cites[2].quotes == []


def test_catch_regex_produces_no_rows_on_prose() -> None:
    text = (
        "filed on 3 May 2019 and served 12 June 2020. See Exhibit 3 Page 4 and Docket No. 22 Civ. 1461. "
        "Boeing 737 MAX 8. Under Article 17 Montreal Convention 1999 and 28 U.S.C. 1332. Rule 56 Statement 3."
    )
    cites = extract_citations(text)
    assert [c.kind for c in cites if c.kind == "unrecognized"] == []


def test_catch_regex_finds_invented_reporter_with_year_after() -> None:
    cites = extract_citations("See Alvarez v. Skyline Cargo, 88 Fed. Air Rptr. 3d 412 (2018).")
    assert len(cites) == 1
    c = cites[0]
    assert c.kind == "unrecognized" and c.reporter == "Fed. Air Rptr. 3d"
    assert (c.volume, c.page, c.year) == (88, 412, 2018)
    assert c.span is not None and c.text == "88 Fed. Air Rptr. 3d 412"


def test_catch_regex_finds_invented_reporter_with_v_before() -> None:
    cites = extract_citations("In Doe v. Roe, 12 Fake. Rptr. 34, the court so held.")
    assert [c.kind for c in cites] == ["unrecognized"]
    assert cites[0].reporter == "Fake. Rptr." and cites[0].year is None


def test_nominative_reporter_is_corrected_to_us() -> None:
    cites = extract_citations("Marbury v. Madison, 5 U.S. (1 Cranch) 137 (1803).")
    c = cites[0]
    assert (c.kind, c.volume, c.reporter, c.page, c.year) == ("full", 5, "U.S.", 137, 1803)


def test_in_re_caption_has_no_plaintiff() -> None:
    cites = extract_citations("In re Papst Licensing GmbH & Co. KG Litigation, 905 F. Supp. 2d 43 (D.D.C. 2012).")
    c = cites[0]
    assert c.plaintiff is None and c.defendant == "Papst Licensing GmbH & Co. KG Litigation"
    assert _norm(c.cite_text) == "In re Papst Licensing GmbH & Co. KG Litigation, 905 F. Supp. 2d 43 (D.D.C. 2012)"


def test_parallel_citations_share_the_year() -> None:
    text = "Zicherman v. Korean Air Lines Co., 516 U.S. 217, 116 S. Ct. 629, 133 L. Ed. 2d 596 (1996)."
    cites = extract_citations(text)
    assert [(c.volume, c.reporter, c.page) for c in cites] == [(516, "U.S.", 217), (116, "S. Ct.", 629), (133, "L. Ed. 2d", 596)]
    assert [c.year for c in cites] == [1996, 1996, 1996]
    assert all(c.plaintiff == "Zicherman" for c in cites)


def test_year_is_not_borrowed_from_the_next_citation() -> None:
    text = "Smith v. Jones, 100 F.3d 1; Doe v. Roe, 200 F.3d 2 (2d Cir. 1990)."
    cites = extract_citations(text)
    assert cites[0].year is None
    assert cites[1].year == 1990


def test_extract_is_pure_and_deterministic() -> None:
    text = SEED_TXT.read_text()
    a = [c.model_dump() for c in extract_citations(text)]
    b = [c.model_dump() for c in extract_citations(text)]
    assert a == b


def test_clean_filing_text_offset_map_round_trips() -> None:
    raw = "Air  France\n v. Saks,\f470 U.S.\t392 (1985)."
    cleaned, to_raw = extract.clean_filing_text(raw)
    assert "  " not in cleaned and "\n" not in cleaned and "\f" not in cleaned
    assert len(to_raw) == len(cleaned) + 1
    i = cleaned.index("470")
    assert raw[to_raw[i]] == "4"
    assert raw[: to_raw[i]].count("\f") == 1


def test_results_are_citation_inputs_serialisable_through_models(seed_cites: list[CitationInput]) -> None:
    from citememo.models import CitationResult

    c = _by_core(seed_cites, "470 U.S. 392")
    assert isinstance(c, CitationInput)
    r = CitationResult(row=1, cite_text=c.cite_text, class_="verified", citation=c)
    dumped = r.model_dump(by_alias=True)
    assert dumped["citation"]["text"] == "470 U.S. 392"
    assert io.StringIO(r.model_dump_json(by_alias=True)).read()
