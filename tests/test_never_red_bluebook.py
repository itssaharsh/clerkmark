"""T09 adversarial pass on the never-red promise: real cases cited the way briefs cite them.

Filings abbreviate case names by Bluebook rule 10.2.2 / table T6 ("Dep't", "Ass'n",
"Metro.", "Prods. Liab. Litig.") and use agency initials (NLRB, SEC, EEOC, EPA) and
place initials ("D.C.", "N.Y.C."). The existing sweep (test_rules) cites every cached case
by CAP's own ``name_abbreviation``; this one cites it in brief form, at its own first page,
and asserts that no real case is ever classed ``likely_fabricated`` ("Likely not a real
case."). A fabricated citation must still read red (the seed's three).
"""

from __future__ import annotations

import pytest

from citememo import memo as memo_mod
from citememo import rules
from citememo.models import CitationInput
from test_rules import CACHE, ctx_for, parties

# Bluebook forms: agency and place initials first, then T6 word abbreviations.
PHRASES = [
    ("Securities & Exchange Commission", "SEC"),
    ("Securities and Exchange Commission", "SEC"),
    ("National Labor Relations Board", "NLRB"),
    ("Equal Employment Opportunity Commission", "EEOC"),
    ("Federal Trade Commission", "FTC"),
    ("Federal Communications Commission", "FCC"),
    ("Environmental Protection Agency", "EPA"),
    ("Immigration & Naturalization Service", "INS"),
    ("Immigration and Naturalization Service", "INS"),
    ("District of Columbia", "D.C."),
    ("New York City", "N.Y.C."),
    ("United States Department", "U.S. Department"),
]
T6 = {
    "Department": "Dep't", "Association": "Ass'n", "National": "Nat'l", "International": "Int'l",
    "Services": "Servs.", "Service": "Serv.", "Products": "Prods.", "Liability": "Liab.", "Litigation": "Litig.",
    "Securities": "Sec.", "Security": "Sec.", "Education": "Educ.", "Metropolitan": "Metro.", "Pacific": "Pac.",
    "Maritime": "Mar.", "Company": "Co.", "Corporation": "Corp.", "Incorporated": "Inc.", "Insurance": "Ins.",
    "University": "Univ.", "Hospital": "Hosp.", "American": "Am.", "America": "Am.", "Commission": "Comm'n",
    "Administration": "Admin.", "Government": "Gov't", "Authority": "Auth.", "Center": "Ctr.",
    "Transportation": "Transp.", "Division": "Div.", "Immigration": "Immigr.", "Washington": "Wash.",
    "Manufacturing": "Mfg.", "Enterprises": "Enters.", "Industries": "Indus.", "Technology": "Tech.",
    "Board": "Bd.", "Commissioner": "Comm'r", "Secretary": "Sec'y", "Brothers": "Bros.", "Railroad": "R.R.",
    "Community": "Cmty.", "County": "Cnty.", "Distribution": "Distrib.", "Development": "Dev.",
    "Environmental": "Env't", "Financial": "Fin.", "General": "Gen.", "Housing": "Hous.", "Management": "Mgmt.",
    "Medical": "Med.", "Municipal": "Mun.", "Organization": "Org.", "Public": "Pub.", "Resources": "Res.",
    "System": "Sys.", "Systems": "Sys.", "Communications": "Commc'ns", "Investment": "Inv.",
    "Associates": "Assocs.", "Committee": "Comm.", "Correctional": "Corr.", "Employees": "Emps.",
    "Employment": "Emp.", "Engineering": "Eng'g", "Equipment": "Equip.", "Federal": "Fed.", "Human": "Hum.",
    "Independent": "Indep.", "Information": "Info.", "Laboratories": "Lab'ys", "Mortgage": "Mortg.",
    "Mutual": "Mut.", "Pharmaceuticals": "Pharms.", "Pharmaceutical": "Pharm.", "Property": "Prop.",
    "Properties": "Props.", "Railway": "Ry.", "Savings": "Sav.", "School": "Sch.", "Schools": "Schs.",
    "Society": "Soc'y", "Transport": "Transp.", "Trust": "Tr.", "Justice": "Just.",
}


def bluebook(name: str) -> str:
    for long, short in PHRASES:
        name = name.replace(long, short)
    out = []
    for w in name.split(" "):
        bare = w.rstrip(",")
        out.append(T6.get(bare, bare) + w[len(bare):])
    return " ".join(out)


def test_never_red_every_cached_case_cited_in_bluebook_form_at_its_first_page():
    red, n = [], 0
    for slug, reporter in (("us", "U.S."), ("f3d", "F.3d"), ("f-supp-2d", "F. Supp. 2d")):
        for vol_dir in sorted((CACHE / slug).iterdir()):
            if not vol_dir.is_dir():
                continue
            volume = int(vol_dir.name)
            ctx = ctx_for(reporter, volume)
            for case in rules.index_volume(ctx.cases).cases:
                cited = bluebook(case.name)
                if cited == case.name:
                    continue
                n += 1
                pl, df = parties(cited)
                c = CitationInput(text=f"{volume} {reporter} {case.first_page}", volume=volume, reporter=reporter,
                                  page=case.first_page, plaintiff=pl, defendant=df, year=int(case.decision_date[:4]))
                r = rules.classify(c, ctx)
                if r.class_ == "likely_fabricated":
                    red.append((f"{cited}, {volume} {reporter} {case.first_page}", case.name))
    assert n > 100  # the sweep really abbreviates something
    assert red == []


# Through the whole pipeline (eyecite decides the parties), as a clerk would paste them.
BRIEF_CITES = [
    "EEOC v. Arabian Am. Oil Co., 499 U.S. 244 (1991)",
    "Am. Hosp. Ass'n v. NLRB, 499 U.S. 606 (1991)",
    "Alaska Dep't of Env't Conservation v. EPA, 540 U.S. 461 (2004)",
    "Dave v. D.C. Metro. Police Dep't, 905 F. Supp. 2d 1, 5 (D.D.C. 2012)",
    "Pac. Mar. Ass'n v. NLRB, 905 F. Supp. 2d 55 (D.D.C. 2012)",
    "D.N. v. N.Y.C. Dep't of Educ., 905 F. Supp. 2d 582 (S.D.N.Y. 2012)",
    "In re Diet Drugs Prods. Liab. Litig., 905 F. Supp. 2d 644 (E.D. Pa. 2012)",
    "Citizens for Responsibility & Ethics in Wash. v. U.S. Dep't of Educ., 905 F. Supp. 2d 161 (D.D.C. 2012)",
    "United States v. Grand Lab'ys, Inc., 174 F.3d 960 (8th Cir. 1999)",
    # a real case with the wrong court and year in the parenthetical
    "Greenleaf v. Garlock, Inc., 174 F.3d 352 (9th Cir. 2001)",
]


@pytest.mark.parametrize("cite", BRIEF_CITES)
def test_never_red_real_case_in_brief_form_through_the_pipeline(cite, monkeypatch):
    monkeypatch.setenv("CITEMEMO_OFFLINE", "1")
    monkeypatch.setenv("CITEMEMO_QUIET", "1")
    memo = memo_mod.run_memo(text=f"The movant relies on {cite}. Nothing else is cited.", filename="pasted-text")
    full = [r for r in memo.results if r.citation is not None and r.citation.kind == "full"]
    assert len(full) == 1, [r.cite_text for r in memo.results]
    assert full[0].class_ != "likely_fabricated", (cite, full[0].reasons)


def test_fabricated_citations_still_read_red(monkeypatch):
    monkeypatch.setenv("CITEMEMO_OFFLINE", "1")
    monkeypatch.setenv("CITEMEMO_QUIET", "1")
    text = (
        "Miller v. United Airlines, Inc., 174 F.3d 366 (2d Cir. 1999). "
        "Varghese v. China S. Airlines Co., 925 F.3d 1339 (11th Cir. 2019). "
        "Varghese v. China Southern Airlines Co., 925 F.3d 1339 (11th Cir. 2019)."
    )
    memo = memo_mod.run_memo(text=text, filename="pasted-text")
    assert [r.class_ for r in memo.results] == ["likely_fabricated"] * 3, [r.reasons for r in memo.results]


# eyecite 2.7.8: a citation whose parenthetical holds only a year, followed by ". " and the
# next case name, hands the NEXT citation the previous defendant and no plaintiff
# ("Olympic Airways v. Husain, 540 U.S. 644 (2004). Greenleaf v. Garlock, Inc., 174 F.3d 352"
# came back as "Husain, 174 F.3d 352" and read "Likely not a real case.").
STRING_CITE = (
    "Olympic Airways v. Husain, 540 U.S. 644 (2004). Greenleaf v. Garlock, Inc., 174 F.3d 352 (3d Cir. 1999). "
    "Eastern Airlines, Inc. v. Floyd, 499 U.S. 530 (1991). J.D. v. Azar, 925 F.3d 1291 (D.C. Cir. 2019). "
    "EEOC v. Arabian Am. Oil Co., 499 U.S. 244 (1991). Dave v. D.C. Metro. Police Dep't, 905 F. Supp. 2d 1, 5 (D.D.C. 2012). "
    "Air France v. Saks, 470 U.S. 392 (1985). Miller v. United Airlines, Inc., 174 F.3d 366 (2d Cir. 1999)."
)


def test_never_red_string_cite_after_a_year_only_parenthetical_keeps_its_own_parties():
    from citememo.extract import extract_citations

    got = [(c.plaintiff, c.defendant) for c in extract_citations(STRING_CITE) if c.kind == "full"]
    assert got == [
        ("Olympic Airways", "Husain"),
        ("Greenleaf", "Garlock, Inc."),
        ("Eastern Airlines, Inc.", "Floyd"),
        ("J.D.", "Azar"),
        ("EEOC", "Arabian Am. Oil Co."),
        ("Dave", "D.C. Metro. Police Dep't"),
        ("Air France", "Saks"),
        ("Miller", "United Airlines, Inc."),
    ], got


def test_never_red_string_cite_through_the_pipeline(monkeypatch):
    monkeypatch.setenv("CITEMEMO_OFFLINE", "1")
    monkeypatch.setenv("CITEMEMO_QUIET", "1")
    memo = memo_mod.run_memo(text=STRING_CITE, filename="pasted-text")
    rows = {r.cite_text: r.class_ for r in memo.results}
    assert rows == {
        "Olympic Airways v. Husain, 540 U.S. 644 (2004)": "verified",
        "Greenleaf v. Garlock, Inc., 174 F.3d 352 (3d Cir. 1999)": "verified",
        "Eastern Airlines, Inc. v. Floyd, 499 U.S. 530 (1991)": "verified",
        "J.D. v. Azar, 925 F.3d 1291 (D.C. Cir. 2019)": "verified",
        "EEOC v. Arabian Am. Oil Co., 499 U.S. 244 (1991)": "verified",
        "Dave v. D.C. Metro. Police Dep't, 905 F. Supp. 2d 1, 5 (D.D.C. 2012)": "verified",
        "Air France v. Saks, 470 U.S. 392 (1985)": "verified",
        "Miller v. United Airlines, Inc., 174 F.3d 366 (2d Cir. 1999)": "likely_fabricated",
    }, rows
