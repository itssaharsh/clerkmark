"""Party-name normalization and matching (DECISION-RULE.md §5).

Pure functions, no I/O. ``rules.py`` calls :func:`match` for every candidate
case at a page (step 6) and for every case in the volume (step 7); T05 needs
nothing from here directly.

Public surface
--------------
- ``normalize_party(s) -> str``: §5.1 (lowercase, NFKC, ``&`` -> ``and``,
  Bluebook T6 expansion, leading procedural phrases and trailing corporate
  suffixes dropped, punctuation stripped).
- ``is_generic(s) -> bool``: §5.2 stoplist, or fewer than 5 letters after
  normalization. A generic party can confirm a match but never carry one.
- ``score(a, caption_part) -> float``: §5.3 ``max(token_set_ratio, token_sort_ratio)``
  on the normalized strings (0–100).
- ``party_scores(cite, case) -> (pl_score, df_score)``.
- ``match(cite, case) -> "full" | "partial" | "none" | "no_names"``: §5.3, where
  ``cite`` is a ``CitationInput`` (``plaintiff`` / ``defendant``) and ``case`` is a
  CAP ``CasesMetadata`` row (``name_abbreviation``) or a caption string.
- ``court_consistent(filing_court, cap_court_name) -> bool``: §5.4 soft circuit check.
"""

from __future__ import annotations

import re
import unicodedata
from functools import lru_cache
from typing import Any, Optional

from rapidfuzz import fuzz

# --------------------------------------------------------------------------- #
# §5.1 normalization tables
# --------------------------------------------------------------------------- #

T6_ABBREVIATIONS: dict[str, str] = {
    "servs.": "services",
    "serv.": "service",
    "enters.": "enterprises",
    "ass'n": "association",
    "atl.": "atlantic",
    "sec'y": "secretary",
    "dep't": "department",
    "comm'r": "commissioner",
    "corp.": "corporation",
    "ins.": "insurance",
    "int'l": "international",
    "nat'l": "national",
    "mfg.": "manufacturing",
    "bd.": "board",
    "univ.": "university",
    "hosp.": "hospital",
    "r.r.": "railroad",
    "ry.": "railway",
    "co.": "company",
    "inc.": "incorporated",
    "ltd.": "limited",
    "bros.": "brothers",
    "indus.": "industries",
    "tech.": "technology",
    "transp.": "transportation",
    "ctr.": "center",
    "auth.": "authority",
    # T09: T6 contractions whose letters are not a prefix/subsequence of the word
    "lab'ys": "laboratories",
    "lab'y": "laboratory",
}

# Ordered longest first so "in the matter of" wins over "matter of".
LEADING_PHRASES: tuple[str, ...] = (
    "in the matter of",
    "on behalf of",
    "application of",
    "petition of",
    "marriage of",
    "estate of",
    "matter of",
    "ex parte",
    "ex rel.",
    "ex rel",
    "in re",
    # eyecite drops "of": "Estate of Durden" arrives as "Estate  Durden".
    "estate",
)

TRAILING_SUFFIXES: tuple[str, ...] = (
    "incorporated",
    "company",
    "corporation",
    "limited",
    "llc",
    "llp",
    "lp",
    "plc",
    "gmbh",
    "s.a.",
    "n.v.",
    "et al.",
    "et al",
    "sa",
    "nv",
)

GENERIC_PARTIES: frozenset[str] = frozenset(
    {
        "united states",
        "state",
        "people",
        "commonwealth",
        "city",
        "county",
        "town",
        "village",
        "board",
        "department",
        "secretary",
        "attorney general",
        "commissioner",
        "administrator",
        "director",
        "warden",
        "superintendent",
        "government",
        "doe",
        "roe",
        "estate",
        "in re",
        "ex parte",
        "matter",
        "plaintiff",
        "defendant",
        "petitioner",
        "respondent",
        "appellant",
        "appellee",
        "ins",
        "co",
        "corp",
        "inc",
        "ltd",
        "llc",
    }
)

MIN_LETTERS = 5

_WS = re.compile(r"\s+")
_PUNCT = re.compile(r"[^\w\s]", re.UNICODE)


def _expand_t6(text: str) -> str:
    tokens = text.split(" ")
    out = []
    for tok in tokens:
        bare = tok.rstrip(",;:")
        trail = tok[len(bare):]
        out.append(T6_ABBREVIATIONS.get(bare, bare) + trail)
    return " ".join(out)


_LEADING_RE = re.compile(
    r"^(?:" + "|".join(re.escape(p) for p in LEADING_PHRASES) + r")(?=\s|$)[\s,.;]*"
)
_TRAILING_RE = re.compile(
    r"(?:^|[\s,])(?:" + "|".join(re.escape(sfx) for sfx in TRAILING_SUFFIXES) + r")[\s,.;]*$"
)
_TRAIL_PUNCT = re.compile(r"[\s,.;]+$")


def _drop_leading(text: str) -> str:
    while text:
        new = _LEADING_RE.sub("", text, count=1)
        if new == text:
            return text
        text = new
    return text


def _drop_trailing(text: str) -> str:
    while text:
        new = _TRAIL_PUNCT.sub("", text)
        new = _TRAILING_RE.sub("", new, count=1)
        if new == text:
            return text
        text = new
    return text


@lru_cache(maxsize=65536)
def normalize_party(s: Optional[str]) -> str:
    """§5.1: a party or caption reduced to the words that identify it.

    ``"Garlock, Inc."`` -> ``"garlock"``; ``"ISS Marine Servs."`` -> ``"iss marine services"``;
    ``"In re Papst Licensing GmbH & Co. KG Litigation"`` -> ``"papst licensing gmbh and company kg litigation"``.
    """
    if not s:
        return ""
    text = unicodedata.normalize("NFKC", str(s)).lower()
    text = text.replace("&", " and ")
    text = _WS.sub(" ", text).strip()
    text = _expand_t6(text)
    text = _drop_leading(text)
    text = _drop_trailing(text)
    text = _PUNCT.sub(" ", text)
    text = _WS.sub(" ", text).strip()
    text = _drop_leading(text)
    text = _drop_trailing(text)
    return _WS.sub(" ", text).strip()


def letters(s: str) -> int:
    return sum(1 for ch in s if ch.isalpha())


@lru_cache(maxsize=65536)
def is_generic(party: Optional[str]) -> bool:
    """§5.2: stoplist members and parties with fewer than 5 letters after normalization."""
    norm = normalize_party(party)
    if not norm:
        return True
    if norm in GENERIC_PARTIES:
        return True
    return letters(norm) < MIN_LETTERS


# --------------------------------------------------------------------------- #
# §5.3 scoring
# --------------------------------------------------------------------------- #

def caption_of(case: Any) -> str:
    """The CAP ``name_abbreviation`` of a case row, or the string itself."""
    if case is None:
        return ""
    if isinstance(case, str):
        return case
    if isinstance(case, dict):
        return case.get("name_abbreviation") or case.get("name") or ""
    return getattr(case, "name", None) or getattr(case, "name_abbreviation", None) or ""


def caption_parts(caption: str) -> list[str]:
    """Normalized halves of a caption split on the first `` v. `` (one part when there is none)."""
    if " v. " in caption:
        a, b = caption.split(" v. ", 1)
        return [normalize_party(a), normalize_party(b)]
    return [normalize_party(caption)]


def _ratio(a: str, b: str) -> tuple[float, float]:
    if not a or not b:
        return 0.0, 0.0
    return float(fuzz.token_set_ratio(a, b)), float(fuzz.token_sort_ratio(a, b))


def score(a: Optional[str], candidate: Optional[str]) -> float:
    """``max(token_set_ratio, token_sort_ratio)`` of the normalized strings, 0–100."""
    na, nb = normalize_party(a), normalize_party(candidate)
    s, t = _ratio(na, nb)
    return max(s, t)


def sort_score(a: Optional[str], candidate: Optional[str]) -> float:
    """``token_sort_ratio`` alone (the §5.3 partial-match test)."""
    na, nb = normalize_party(a), normalize_party(candidate)
    return _ratio(na, nb)[1]


def _against(norm_party: str, candidates: list[str]) -> tuple[float, float]:
    """(best max(set, sort) ratio, best sort ratio) of a normalized party against caption candidates."""
    best = best_sort = 0.0
    for cand in candidates:
        if not cand:
            continue
        set_r, sort_r = _ratio(norm_party, cand)
        best = max(best, set_r, sort_r)
        best_sort = max(best_sort, sort_r)
    return best, best_sort


# --------------------------------------------------------------------------- #
# §5.1a brief-form abbreviations (T09 adversarial pass)
#
# Briefs cite by Bluebook R10.2 / T6: "Pac. Mar. Ass'n v. NLRB", "Dave v. D.C. Metro.
# Police Dep't", "In re Diet Drugs Prods. Liab. Litig.". The T6 table above cannot list
# every abbreviation, and agency / place initials (NLRB, EEOC, EPA, D.C., N.Y.C.) are
# not words at all, so a real case cited at its own first page used to score "none"
# and read "Likely not a real case." Each abbreviated filed token (it carries a period
# or an apostrophe, or is written in initials) is aligned, in order, with the caption
# being scored: an abbreviation fits a caption word it is a prefix of, or (3+ letters,
# same first letter) a subsequence of ("Prods." -> products, "Comm'n" -> commission);
# initials fit a run of caption words by first letters, skipping "of/and/the/for"
# ("EEOC" -> equal employment opportunity commission, "D.C." -> district of columbia).
# The aligned caption words replace the tokens and the ordinary §5.3 ratio is taken
# again; the better of the two scores counts. Plain words are never expanded, so a
# fabricated caption made of ordinary words scores exactly as before.
# --------------------------------------------------------------------------- #

_INITIALS_SKIP = frozenset({"of", "and", "the", "for", "in", "on", "de"})
_DOTTED_INITIALS = re.compile(r"^(?:[A-Za-z]\.){2,}$")
_CAPS_INITIALS = re.compile(r"^[A-Z]{2,6}$")
_ABBR_MARK = re.compile(r"[.'\u2019]")
_NOT_ALNUM = re.compile(r"[^a-z0-9]")


@lru_cache(maxsize=65536)
def _brief_units(party: str) -> tuple[tuple[str, str, str], ...]:
    """``(kind, letters, raw)`` per filed token, kind ``initials`` / ``abbr`` / ``word``; ``()`` when nothing is abbreviated."""
    text = unicodedata.normalize("NFKC", party).replace("&", " and ")
    units: list[tuple[str, str, str]] = []
    abbreviated = False
    for tok in text.split():
        raw = tok.strip(",;:()[]")
        low = raw.lower()
        letters_only = _NOT_ALNUM.sub("", low)
        if not letters_only:
            continue
        if low in T6_ABBREVIATIONS:
            units.append(("word", T6_ABBREVIATIONS[low], raw))
        elif _DOTTED_INITIALS.match(raw) or _CAPS_INITIALS.match(raw):
            units.append(("initials", letters_only, raw))
            abbreviated = True
        elif _ABBR_MARK.search(raw) and len(letters_only) >= 2:
            units.append(("abbr", letters_only, raw))
            abbreviated = True
        else:
            units.append(("word", letters_only, raw))
    return tuple(units) if abbreviated else ()


def _abbr_fits(abbr: str, word: str) -> bool:
    if len(abbr) < 2 or len(word) < len(abbr):
        return False
    if word.startswith(abbr):
        return True
    if len(abbr) >= 3 and abbr[0] == word[0]:
        rest = iter(word)
        return all(ch in rest for ch in abbr)
    return False


def _initials_end(initials: str, words: list[str], start: int) -> int:
    """End index of a run of ``words`` from ``start`` whose first letters spell ``initials``; 0 when none."""
    if len(initials) < 2 or words[start] in _INITIALS_SKIP:
        return 0
    i, k = 0, start
    while k < len(words) and i < len(initials):
        w = words[k]
        if i > 0 and w in _INITIALS_SKIP:
            k += 1
            continue
        if w[0] != initials[i]:
            return 0
        i += 1
        k += 1
    return k if i == len(initials) else 0


@lru_cache(maxsize=262144)
def _expand_against(party: str, candidate_norm: str) -> Optional[str]:
    """``party`` with its abbreviations replaced by the caption words they stand for, or ``None``."""
    units = _brief_units(party)
    if not units or not candidate_norm:
        return None
    words = candidate_norm.split()
    out: list[str] = []
    pos = 0
    changed = False
    for kind, letters_only, raw in units:
        hit: Optional[tuple[int, int]] = None
        for j in range(pos, len(words)):
            w = words[j]
            if kind in ("word", "initials") and w == letters_only:
                hit = (j, j + 1)
                break
            if kind == "abbr" and _abbr_fits(letters_only, w):
                hit = (j, j + 1)
                break
            if kind == "initials":
                end = _initials_end(letters_only, words, j)
                if end:
                    hit = (j, end)
                    break
        if hit is None:
            out.append(raw)
            continue
        out.append(" ".join(words[hit[0]:hit[1]]))
        pos = hit[1]
        changed = changed or kind != "word"
    return " ".join(out) if changed else None


def _against_party(party: str, candidates: list[str]) -> tuple[float, float]:
    """:func:`_against` for a raw filed party, also scoring its brief-form expansion per candidate."""
    best, best_sort = _against(normalize_party(party), candidates)
    if best_sort >= 100.0 or not _brief_units(party):
        return best, best_sort
    for cand in candidates:
        expanded = _expand_against(party, cand) if cand else None
        if expanded:
            set_r, sort_r = _ratio(normalize_party(expanded), cand)
            best = max(best, set_r, sort_r)
            best_sort = max(best_sort, sort_r)
    return best, best_sort


def evaluate(cite: Any, case: Any) -> tuple[str, Optional[float], Optional[float]]:
    """§5.3 in one pass: ``(match, plaintiff score, defendant score)``.

    ``match`` is ``"full"`` / ``"partial"`` / ``"none"`` / ``"no_names"`` exactly as :func:`match`
    defines it; the scores are what :func:`party_scores` returns. One rapidfuzz pass per pair.
    """
    pl = getattr(cite, "plaintiff", None) or None
    df = getattr(cite, "defendant", None) or None
    if not pl and not df:
        return "no_names", None, None
    caption = caption_of(case)
    parts = caption_parts(caption)
    whole = normalize_party(caption)
    pl_cands = [parts[0], whole]
    df_cands = [parts[1], whole] if len(parts) == 2 else [whole]
    pl_score = df_score = None
    pl_sort = df_sort = 0.0
    if pl:
        pl_score, pl_sort = _against_party(pl, pl_cands)
    if df:
        df_score, df_sort = _against_party(df, df_cands)
    pl_generic = is_generic(pl) if pl else True
    df_generic = is_generic(df) if df else True
    if pl and df:
        if pl_score >= 80 and df_score >= 80:
            return "full", pl_score, df_score
    else:
        only_generic = pl_generic if pl else df_generic
        only_score = pl_score if pl else df_score
        if not only_generic and only_score is not None and only_score >= 85:
            return "full", pl_score, df_score
    # partial: a non-generic party sorts >= 90 against any caption part or the whole caption
    all_cands = parts + [whole]
    for party, generic in ((pl, pl_generic), (df, df_generic)):
        if not party or generic:
            continue
        _, sort_r = _against_party(party, all_cands)
        if sort_r >= 90:
            return "partial", pl_score, df_score
    return "none", pl_score, df_score


def party_scores(cite: Any, case: Any) -> tuple[Optional[float], Optional[float]]:
    """(plaintiff score, defendant score) against a caption, ``None`` for a missing party."""
    _, pl_score, df_score = evaluate(cite, case)
    return pl_score, df_score


def best_score(cite: Any, case: Any) -> float:
    pl_score, df_score = party_scores(cite, case)
    return max([s for s in (pl_score, df_score) if s is not None] or [0.0])


def has_distinctive_party(cite: Any) -> bool:
    """True when at least one filed party is not generic (§5.2). Nothing can be searched otherwise."""
    return any(not is_generic(p) for p in (getattr(cite, "plaintiff", None), getattr(cite, "defendant", None)) if p)


def distinctive_parties(cite: Any) -> list[str]:
    """Filed parties that are not generic, plaintiff first."""
    return [p for p in (getattr(cite, "plaintiff", None), getattr(cite, "defendant", None)) if p and not is_generic(p)]


def match(cite: Any, case: Any) -> str:
    """§5.3 ``match(case)``: ``"full"``, ``"partial"``, ``"none"`` or ``"no_names"``.

    - ``no_names``: neither party given.
    - ``full``: both present and both score >= 80; or exactly one present, not generic, scoring >= 85.
    - ``partial``: not full, and a non-generic party has ``token_sort_ratio >= 90`` against a
      caption part or the whole caption.
    - ``none``: otherwise.
    """
    return evaluate(cite, case)[0]


# --------------------------------------------------------------------------- #
# §5.4 court consistency (soft; step-7 partial hits only)
# --------------------------------------------------------------------------- #

_ORDINALS = {
    1: "first", 2: "second", 3: "third", 4: "fourth", 5: "fifth", 6: "sixth",
    7: "seventh", 8: "eighth", 9: "ninth", 10: "tenth", 11: "eleventh",
}
_ORDINAL_WORDS = {v: v for v in _ORDINALS.values()}
_ORDINAL_WORDS.update({"federal": "federal", "district of columbia": "district of columbia"})

_FILED_CIRCUIT = re.compile(r"(\d+)\s*(?:st|d|nd|rd|th)\s+Cir\.?", re.IGNORECASE)
_EYECITE_CIRCUIT = re.compile(r"^ca(\d{1,2})$", re.IGNORECASE)
_CAP_CIRCUIT = re.compile(
    r"\b(first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth|eleventh|federal)\b(?:\s+circuit)?",
    re.IGNORECASE,
)


def circuit_of_filing(court: Optional[str]) -> Optional[str]:
    """``"3d Cir."`` / ``"ca3"`` -> ``"third"``; ``"D.C. Cir."`` / ``"cadc"`` -> ``"district of columbia"``; ``"Fed. Cir."`` / ``"cafc"`` -> ``"federal"``."""
    if not court:
        return None
    text = court.strip()
    low = text.lower()
    if low in ("cadc",) or re.search(r"\bd\.\s*c\.\s*cir", low):
        return "district of columbia"
    if low in ("cafc",) or re.search(r"\bfed\.\s*cir", low):
        return "federal"
    m = _EYECITE_CIRCUIT.match(low)
    if m:
        return _ORDINALS.get(int(m.group(1)))
    m = _FILED_CIRCUIT.search(text)
    if m:
        return _ORDINALS.get(int(m.group(1)))
    return None


def circuit_of_cap(court_name: Optional[str]) -> Optional[str]:
    """CAP ``court.name`` -> the circuit word, or ``None`` for district and state courts."""
    if not court_name:
        return None
    low = court_name.lower()
    if "court of appeals" not in low:
        return None
    if "district of columbia" in low:
        return "district of columbia"
    m = _CAP_CIRCUIT.search(low)
    if m:
        return m.group(1).lower()
    return None


def court_consistent(filing_court: Optional[str], cap_court_name: Optional[str]) -> bool:
    """§5.4: inconsistent only when both sides yield a circuit and the circuits differ."""
    a = circuit_of_filing(filing_court)
    b = circuit_of_cap(cap_court_name)
    if a is None or b is None:
        return True
    return a == b


__all__ = [
    "GENERIC_PARTIES",
    "T6_ABBREVIATIONS",
    "best_score",
    "caption_of",
    "caption_parts",
    "circuit_of_cap",
    "circuit_of_filing",
    "court_consistent",
    "distinctive_parties",
    "evaluate",
    "has_distinctive_party",
    "is_generic",
    "match",
    "normalize_party",
    "party_scores",
    "score",
    "sort_score",
]
