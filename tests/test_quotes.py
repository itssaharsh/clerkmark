"""T03 — citememo/quotes.py: check_quote against cached CAP opinion text (offline).

Fixtures: seed/cache/cap/**/cases/*.json (committed). Expectations follow
docs/DECISION-RULE.md §4 and seed/ground_truth.json.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from citememo.models import ClosestPassage, DiffToken, QuoteCheck
from citememo.quotes import check_quote, norm_quote, opinion_text

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "seed" / "cache" / "cap"
GT = json.loads((ROOT / "seed" / "ground_truth.json").read_text())
GT_ITEMS = {it["id"]: it for it in GT["items"]}


def _case(slug: str, volume: int, file_name: str) -> dict:
    return json.loads((CACHE / slug / str(volume) / "cases" / f"{file_name}.json").read_text())


@pytest.fixture(scope="module")
def zicherman() -> str:
    return opinion_text(_case("us", 516, "0217-01"))


@pytest.fixture(scope="module")
def saks() -> str:
    return opinion_text(_case("us", 470, "0392-01"))


@pytest.fixture(scope="module")
def husain() -> str:
    return opinion_text(_case("us", 540, "0644-01"))


@pytest.fixture(scope="module")
def chan() -> str:
    return opinion_text(_case("us", 490, "0122-01"))


@pytest.fixture(scope="module")
def iqbal() -> str:
    return opinion_text(_case("us", 556, "0662-01"))


@pytest.fixture(scope="module")
def twombly() -> str:
    return opinion_text(_case("us", 550, "0544-01"))


ZICHERMAN_Q = GT_ITEMS["real-zicherman"]["quote"]
SAKS_Q = GT_ITEMS["real-saks"]["quote"]
HUSAIN_Q = GT_ITEMS["real-husain"]["quote"]
TWOMBLY_Q = GT_ITEMS["real-twombly"]["quote"]


def test_opinion_text_concatenates_opinions_majority_first() -> None:
    case = _case("us", 490, "0122-01")  # majority + concurrence
    t = opinion_text(case)
    assert t.startswith(case["casebody"]["opinions"][0]["text"][:200])
    assert case["casebody"]["opinions"][1]["text"][:200] in t


def test_verbatim_quote(zicherman: str) -> None:
    r = check_quote(ZICHERMAN_Q, zicherman)
    assert isinstance(r, QuoteCheck)
    assert r.status == "verbatim"
    assert r.similarity == 100.0
    assert r.diff == []
    assert r.segments == 1
    assert r.quote == ZICHERMAN_Q
    assert isinstance(r.closest_passage, ClosestPassage)
    assert ZICHERMAN_Q in r.closest_passage.text
    assert r.closest_passage.status == "verbatim"
    assert r.closest_passage.highlight is not None
    s, e = r.closest_passage.highlight
    assert r.closest_passage.text[s:e] == ZICHERMAN_Q
    # excerpt is the passage with about 200 chars of context each side
    assert r.excerpt == r.closest_passage.text
    assert len(r.excerpt) <= len(ZICHERMAN_Q) + 2 * 200 + 2


def test_every_seed_verbatim_quote_is_verbatim() -> None:
    for item in GT["items"]:
        qc = item.get("quote_check") or {}
        if not item["quote"] or not qc.get("found_verbatim"):
            continue
        rc = item["real_case_at_page"]
        slug = {"U.S.": "us", "F.3d": "f3d"}[item["reporter"]]
        text = opinion_text(_case(slug, item["volume"], rc["file_name"]))
        r = check_quote(item["quote"], text)
        assert r.status == "verbatim", (item["id"], r.status, r.diff)


def test_one_word_swapped_is_differs_with_the_token_pair(zicherman: str) -> None:
    q = ZICHERMAN_Q.replace("authorizing", "permitting")
    r = check_quote(q, zicherman)
    assert r.status == "differs"
    assert r.diff == [DiffToken(filed="permitting", opinion="authorizing")]
    assert r.similarity is not None and 90 <= r.similarity < 100
    assert "authorizing us to apply the law" in r.closest_passage.text


def test_inserted_not_is_differs(husain: str) -> None:
    q = HUSAIN_Q.replace("Article 17 creates", "Article 17 not creates")
    r = check_quote(q, husain)
    assert r.status == "differs"
    assert len(r.diff) == 1
    assert r.diff[0].filed == "not" and r.diff[0].opinion == ""


def test_three_words_changed_is_differs_chan(chan: str) -> None:
    item = GT_ITEMS["misq-chan"]
    r = check_quote(item["quote"], chan)
    assert r.status == "differs"
    pairs = {(d.filed, d.opinion) for d in r.diff}
    assert pairs == {("authority", "power"), ("add", "insert"), ("exception", "amendment")}
    assert r.similarity is not None and 70 <= r.similarity < 100
    assert item["real_sentence"] in r.closest_passage.text
    assert r.closest_passage.status == "differs"


def test_four_words_changed_is_not_found_iqbal(iqbal: str) -> None:
    item = GT_ITEMS["misq-iqbal"]
    r = check_quote(item["quote"], iqbal)
    assert r.status == "not_found"
    assert len(r.diff) >= 4
    assert r.similarity is not None and 70 <= r.similarity < 100
    assert item["real_sentence"] in r.closest_passage.text  # the closest passage is still shown


def test_ellipsis_segments_in_order_are_verbatim(saks: str) -> None:
    q = "Any injury is the product of a chain of causes, . . . that some link in the chain was an unusual or unexpected event external to the passenger."
    r = check_quote(q, saks)
    assert r.status == "verbatim"
    assert r.segments == 2
    assert r.diff == []
    r2 = check_quote(q.replace(". . .", "…"), saks)
    assert r2.status == "verbatim" and r2.segments == 2
    r3 = check_quote(q.replace(". . .", "..."), saks)
    assert r3.status == "verbatim" and r3.segments == 2


def test_ellipsis_segments_out_of_order_are_not_found(saks: str) -> None:
    q = "some link in the chain was an unusual or unexpected event external to the passenger . . . Any injury is the product of a chain of causes, and we require only"
    r = check_quote(q, saks)
    assert r.status == "not_found"
    assert r.segments == 2


def test_short_fragment_segments_are_dropped(saks: str) -> None:
    q = "Any injury is the product of a chain of causes, and we require only that the passenger . . . event."
    r = check_quote(q, saks)
    assert r.status == "verbatim"
    assert r.segments == 1  # the 1-token tail is not compared


def test_quote_of_only_short_fragments_is_not_checked(saks: str) -> None:
    r = check_quote("event . . . chain", saks)
    assert r.status == "not_checked"
    assert r.segments == 0
    assert r.closest_passage is None


def test_normalization_bracket_hyphenation_curly_quotes(zicherman: str) -> None:
    q = (
        "“[A]bsent such legislation, however, Articles 17 and 24(2) provide nothing more than a pass-\n"
        "through, authorizing us to apply the law that would govern in absence of the Warsaw Convention.”"
    )
    r = check_quote(q, zicherman)
    assert r.status == "verbatim", r.diff


def test_normalization_soft_hyphen_line_break_inside_a_word(twombly: str) -> None:
    q = TWOMBLY_Q.replace("plausible", "plausi-\nble").replace("heightened", "height­ened")
    r = check_quote(q, twombly)
    assert r.status == "verbatim", r.diff


def test_normalization_dashes_and_apostrophes(zicherman: str) -> None:
    # the opinion has a curly apostrophe (Kole’s) and an em dash; the filer typed straight ones
    q = "Petitioners Marjorie Zicherman and Muriel Mahalek, Kole's sister and mother, respectively, sued respondent Korean Air Lines Co."
    assert check_quote(q, zicherman).status == "verbatim"
    q2 = "it must be acknowledged that the term is to be understood in its distinctively legal sense -- that is, to mean only legally cognizable harm."
    assert check_quote(q2, zicherman).status == "verbatim"


def test_omission_parentheticals_are_ignored(zicherman: str) -> None:
    q = ZICHERMAN_Q.replace("pass-through,", "pass-through (citation omitted),")
    assert check_quote(q, zicherman).status == "verbatim"
    q2 = ZICHERMAN_Q + " (internal quotation marks omitted) (emphasis added)"
    assert check_quote(q2, zicherman).status == "verbatim"


def test_generic_phrase_is_not_found(zicherman: str) -> None:
    r = check_quote("The court below was plainly wrong in every respect and its judgment must fall.", zicherman)
    assert r.status == "not_found"
    assert r.similarity is not None and r.similarity < 100
    assert r.closest_passage is not None  # the nearest window is still shown


def test_norm_quote_tokens() -> None:
    s, _ = norm_quote("“[T]he Court’s pass-through — rule.”")
    assert s.strip() == "the courts pass through rule"


def test_check_quote_is_pure(zicherman: str) -> None:
    q = ZICHERMAN_Q.replace("authorizing", "permitting")
    a = check_quote(q, zicherman).model_dump()
    b = check_quote(q, zicherman).model_dump()
    assert a == b


def test_quote_check_fits_citation_result(zicherman: str) -> None:
    from citememo.models import CitationResult

    r = check_quote(ZICHERMAN_Q, zicherman)
    row = CitationResult(row=1, cite_text="x", class_="verified", quote_check=r)
    d = row.model_dump(by_alias=True)
    assert d["quote_check"]["status"] == "verbatim"
    assert row.label == "Found. Quote matches."
