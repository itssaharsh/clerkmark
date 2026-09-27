"""Filing text → citations (T03, DECISION-RULE §1.1, §1.2, §1.6 item 1–2 and §2 step 1).

Public surface (pure functions, no network, no I/O beyond the bytes handed in):

``pdf_to_text(data: bytes) -> str``
    pdfplumber page text joined by form feeds (``\\f``); line-break hyphenation
    repaired conservatively (only ``lower-\\nlower``). Raises :class:`NoTextLayer`
    when fewer than 40 characters come out (scanned PDF), :class:`UnreadablePdf`
    when the bytes are not a PDF pdfplumber can open.

``clean_filing_text(text: str) -> tuple[str, list[int]]``
    ``eyecite.clean_text(text, ["all_whitespace"])`` plus an offset map
    ``to_raw`` (``len(cleaned) + 1`` entries) from cleaned offsets back to the
    text given. Spans on the returned citations index the *cleaned* text.

``extract_citations(text: str) -> list[CitationInput]``
    Every citation eyecite finds, in filing order, as :class:`ExtractedCitation`
    (a :class:`CitationInput` with a few extra fields, see below), plus the
    unrecognized-reporter catch on the spans eyecite left uncovered.

    * ``kind``: ``full`` (FullCaseCitation), ``id``, ``supra``, ``short``,
      ``statute`` (FullLawCitation / FullJournalCitation) or ``unrecognized``.
    * ``text``/``span``: the core cite (``925 F.3d 1339``) and its
      ``[start, end)`` in the cleaned text; ``filing_page`` is 1-based, from the
      form feeds of the text given.
    * ``volume``/``reporter``/``page``: reporter is eyecite's
      ``edition_guess.short_name`` (``F. Supp. 2d``, ``U.S.`` for ``5 U.S. (1
      Cranch) 137``), or the raw string for ``unrecognized``.
    * ``year``/``court``: year from the parenthetical regex on the text after the
      cite (bounded by the next citation's case name), falling back to eyecite's
      ``metadata.year`` only when that year is printed in the same window, then to
      the volume for year-numbered reporters (``2013 IL App (1st)``, ``2019 WL``).
      ``court`` is eyecite's court id when it has one, else the parenthetical's
      court text (``3d Cir.``).
    * ``quotes``: quoted passages (straight or curly double quotes, ≥ 25 chars,
      alterations and ellipses kept verbatim) that end within 400 chars before the
      core cite and after the previous citation, or that follow ``quoting`` in the
      parenthetical after the cite. A passage is attached to one citation only.
    * ``cite_text``: the citation as the memo prints it, taken from the filing
      (``Estate of Durden v. KLM Royal Dutch Airlines, 2017 WL 2418825 (Ga. Ct.
      App. 2017)``).
    * ``cite_type``: reporters_db ``cite_type`` (``specialty_west``, ``neutral``,
      ``federal`` …) so rules can route WL/LEXIS/neutral cites (§2 step 2).
    * ``history``: the subsequent-history phrase found within 40 chars before a
      full cite (``cert. denied``, ``aff'd`` …); the classifier maps it to class
      ``skipped`` (§1.6 item 2). ``CitationKind`` has no ``skipped`` value, so the
      kind stays ``full``.
    * ``slip_op``: ``slip op.`` within 40 chars after the cite (§1.6 item 1).
    * ``duplicate_of``: index in the returned list of the first full cite with the
      same volume/reporter/page, or ``None``.

Nothing here classifies; see ``rules.py`` (T04).
"""

from __future__ import annotations

import io
import re
from typing import Optional

from eyecite import clean_text, get_citations
from eyecite.models import (
    CitationBase,
    FullCaseCitation,
    FullCitation,
    IdCitation,
    ShortCaseCitation,
    SupraCitation,
)

from citememo.models import CitationInput, CitationKind

__all__ = [
    "ExtractedCitation",
    "NoTextLayer",
    "UnreadablePdf",
    "clean_filing_text",
    "extract_citations",
    "pdf_to_text",
]


class NoTextLayer(ValueError):
    """The PDF has no usable text layer (fewer than 40 characters extracted)."""


class UnreadablePdf(ValueError):
    """The bytes are not a PDF pdfplumber can open."""


class ExtractedCitation(CitationInput):
    """A :class:`CitationInput` plus what the memo and the classifier need from the text."""

    cite_text: str = ""
    cite_type: Optional[str] = None
    history: Optional[str] = None
    slip_op: bool = False
    duplicate_of: Optional[int] = None


# --------------------------------------------------------------------------- #
# PDF → text
# --------------------------------------------------------------------------- #

MIN_TEXT_CHARS = 40
_HYPHEN_BREAK = re.compile(r"(?<=[a-z])-\n(?=[a-z])")


def pdf_to_text(data: bytes) -> str:
    """Text of every page, pages joined by ``\\f``; ``lower-\\nlower`` line-break hyphenation joined."""
    import pdfplumber

    try:
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            pages = [(page.extract_text() or "") for page in pdf.pages]
    except NoTextLayer:  # pragma: no cover - never raised inside
        raise
    except Exception as exc:  # pdfminer raises a zoo of exception types
        raise UnreadablePdf(f"could not open the file as a PDF: {exc.__class__.__name__}") from exc
    text = "\f".join(pages)
    if len(re.sub(r"\s+", "", text)) < MIN_TEXT_CHARS:
        raise NoTextLayer("the PDF has no text layer (fewer than 40 characters extracted)")
    return _HYPHEN_BREAK.sub("", text)


# --------------------------------------------------------------------------- #
# Whitespace cleaning with an offset map
# --------------------------------------------------------------------------- #

_WS = re.compile(r"[​\s]+")  # what eyecite's all_whitespace collapses


def clean_filing_text(text: str) -> tuple[str, list[int]]:
    """``eyecite.clean_text(text, ["all_whitespace"])`` and the cleaned→raw offset map.

    ``to_raw[i]`` is the raw offset of cleaned character ``i``; ``to_raw[len(cleaned)]``
    is ``len(text)`` so half-open spans map too.
    """
    cleaned_parts: list[str] = []
    to_raw: list[int] = []
    pos = 0
    for m in _WS.finditer(text):
        cleaned_parts.append(text[pos : m.start()])
        to_raw.extend(range(pos, m.start()))
        cleaned_parts.append(" ")
        to_raw.append(m.start())
        pos = m.end()
    cleaned_parts.append(text[pos:])
    to_raw.extend(range(pos, len(text)))
    to_raw.append(len(text))
    cleaned = "".join(cleaned_parts)
    expected = clean_text(text, ["all_whitespace"])
    if cleaned != expected:  # eyecite changed its cleaner: fall back to its text, approximate map
        cleaned = expected
        to_raw = _approx_map(text, cleaned)
    return cleaned, to_raw


def _approx_map(raw: str, cleaned: str) -> list[int]:
    import difflib

    sm = difflib.SequenceMatcher(None, raw, cleaned, autojunk=False)
    to_raw = [0] * (len(cleaned) + 1)
    last = 0
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        for k in range(j1, j2):
            to_raw[k] = i1 + min(k - j1, max(i2 - i1 - 1, 0))
            last = to_raw[k]
    to_raw[len(cleaned)] = len(raw)
    if not cleaned:
        to_raw[0] = last
    return to_raw


# --------------------------------------------------------------------------- #
# Patterns
# --------------------------------------------------------------------------- #

_YEAR_PAREN = re.compile(r"\(([^()]*?)\b((?:1[7-9]|20)\d{2})\)")
_HISTORY = re.compile(r"cert\.\s*(?:denied|granted|dismissed)|aff'd|rev'd|vacated|reh'g|denying cert", re.IGNORECASE)
_SLIP_OP = re.compile(r"slip\s+op\.", re.IGNORECASE)
_PARALLEL_GAP = re.compile(r"[\s,]*(?:(?:at\s+)?\d[\d\-\u2013]*(?:\s*n\.\s*\d+)?)?[\s,]*")
_QUOTE_MARK = re.compile(r'["\u201c\u201d]')
_QUOTING = re.compile(r"\bquoting\b", re.IGNORECASE)
MIN_QUOTE_CHARS = 25
_SIGNALS = re.compile(
    r"^(?:(?:see|see also|see, e\.g\.,|e\.g\.,|cf\.|but see|but cf\.|accord|compare|contra|citing|quoting|"
    r"see generally|and|with|in|at)\s+)+",
    re.IGNORECASE,
)
_PROCEDURAL = re.compile(r"(?:In re|In the Matter of|Matter of|Ex parte|Estate of)\s+$", re.IGNORECASE)

# DECISION-RULE §2 step 1: the unrecognized-reporter catch on uncovered spans.
_CATCH = re.compile(r"\b(\d{1,4})\s+((?:[A-Z][A-Za-z.']*\.?\s){1,5}(?:\d(?:st|d|nd|rd|th)\s)?)(\d{1,5})\b")
_ORDINAL = re.compile(r"^\d(?:st|d|nd|rd|th)$")
_MONTHS = {
    "january", "february", "march", "april", "may", "june", "july", "august", "september",
    "october", "november", "december", "jan.", "feb.", "mar.", "apr.", "jun.", "jul.", "aug.",
    "sept.", "sep.", "oct.", "nov.", "dec.",
}
_BAD_REPORTER_TOKENS = {
    "page", "gate", "entry", "chapter", "section", "article", "exhibit", "docket", "no.", "line",
    "paragraph", "seat", "flight", "statement", "deposition", "through", "requires", "lines",
    "u.s.c.", "c.f.r.", "civ.", "cr.", "tr.", "stat.",
}
_BAD_BEFORE_TOKENS = {"no.", "docket", "ecf", "rule", "exhibit", "page", "flight", "boeing", "article", "section", "chapter"}
_NAME_ALLOW_LOWER = {"of", "the", "and", "&", "de", "la", "du", "van", "von", "for", "ex", "rel.", "et", "al.", "in", "re", "on", "behalf"}
_NAME_ABBREVS = {"inc.", "co.", "corp.", "ltd.", "bros.", "u.s.", "no.", "mfg.", "ass'n", "dep't", "sec'y", "nat'l", "int'l", "assocs.", "indus.", "ins.", "r.r.", "ry.", "l.l.c.", "s.a.", "n.v.", "st.", "mt.", "ft."}


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _quoted_passages(cleaned: str) -> list[tuple[int, int, int, int]]:
    """``(open_start, content_start, content_end, close_end)`` for every double-quoted passage ≥ 25 chars.

    Curly marks open/close by themselves; straight marks alternate, so a short
    quoted word (``"accident"``) never flips the pairing of the passages after it.
    """
    out: list[tuple[int, int, int, int]] = []
    open_start: Optional[int] = None
    for m in _QUOTE_MARK.finditer(cleaned):
        ch = m.group()
        if ch == "\u201c":
            open_start = m.start()
        elif ch == "\u201d":
            if open_start is not None:
                if m.start() - (open_start + 1) >= MIN_QUOTE_CHARS:
                    out.append((open_start, open_start + 1, m.start(), m.end()))
                open_start = None
        elif open_start is None:
            open_start = m.start()
        else:
            if m.start() - (open_start + 1) >= MIN_QUOTE_CHARS:
                out.append((open_start, open_start + 1, m.start(), m.end()))
            open_start = None
    return out


def _int(value) -> Optional[int]:
    if value is None:
        return None
    m = re.match(r"\d+", str(value))
    return int(m.group()) if m else None


def _ws(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    v = re.sub(r"\s+", " ", str(value)).strip()
    return v or None


def _kind_of(c: CitationBase) -> Optional[CitationKind]:
    if isinstance(c, FullCaseCitation):
        return "full"
    if isinstance(c, IdCitation):
        return "id"
    if isinstance(c, SupraCitation):
        return "supra"
    if isinstance(c, ShortCaseCitation):
        return "short"
    if isinstance(c, FullCitation):  # FullLawCitation, FullJournalCitation
        return "statute"
    return None  # UnknownCitation and friends: covered span, no row


def _token_pattern(name: str) -> str:
    """Regex for a party name as eyecite gives it, tolerant of the little words eyecite drops."""
    toks = name.split()
    sep = r"\s+(?:[a-z][a-z']*\s+){0,2}"
    return sep.join(re.escape(t) for t in toks)


def _case_name_start(cleaned: str, span_start: int, plaintiff: Optional[str], defendant: Optional[str]) -> Optional[int]:
    """Offset where the case name begins in ``cleaned``, anchored on eyecite's parties."""
    w0 = max(0, span_start - 200)
    w = cleaned[w0:span_start]
    if defendant:
        best = None
        for m in re.finditer(_token_pattern(defendant), w):
            tail = w[m.end() :].strip()
            if tail in ("", ","):
                best = m
        if best is None:
            return None
        df_start = best.start()
        head = w[:df_start]
        if plaintiff:
            mv = re.search(r"\s+v\.?\s+$", head)
            if not mv:
                return None
            head = head[: mv.start()]
            first = plaintiff.split()[0]
            starts = [m.start() for m in re.finditer(r"(?<!\w)" + re.escape(first) + r"(?!\w)", head)]
            if not starts:
                return None
            start = starts[-1]
            if len(head) - start > 120:
                return None
        else:
            start = df_start
        proc = _PROCEDURAL.search(w[:start])
        if proc:
            start = proc.start()
        return w0 + start
    if plaintiff:
        first = plaintiff.split()[0]
        starts = [m.start() for m in re.finditer(r"(?<!\w)" + re.escape(first) + r"(?!\w)", w)]
        if starts and len(w) - starts[-1] <= 120:
            return w0 + starts[-1]
    return None


def _heuristic_name(before: str) -> Optional[tuple[int, str, Optional[str], Optional[str]]]:
    """Case name right before a regex catch: ``(start offset in before, name, plaintiff, defendant)``."""
    stripped = before.rstrip()
    stripped = re.sub(r",\s*$", "", stripped)
    if not stripped:
        return None
    mv = None
    for m in re.finditer(r"\s+v\.?\s+", stripped):
        mv = m
    if mv is None:
        mr = re.search(r"(?:In re|In the Matter of|Matter of|Ex parte)\s+([A-Z][^;:\"“”]{1,80})$", stripped)
        if not mr:
            return None
        return mr.start(), mr.group(0).strip(), None, mr.group(1).strip()
    defendant = stripped[mv.end() :].strip()
    if not defendant or len(defendant) > 100 or re.search(r"[;:\"“”]", defendant):
        return None
    head = stripped[: mv.start()]
    toks = head.split()
    taken: list[str] = []
    for tok in reversed(toks):
        low = tok.lower()
        if re.search(r"[;:\"“”()]", tok):
            break
        if tok[0].isupper() or low in _NAME_ALLOW_LOWER:
            if tok.endswith(".") and low not in _NAME_ABBREVS and len(tok) > 4 and taken:
                break
            taken.append(tok)
            continue
        break
    if not taken:
        return None
    name_head = " ".join(reversed(taken))
    name_head = _SIGNALS.sub("", name_head) if not re.match(r"In re\b", name_head) else name_head
    if not name_head:
        return None
    start = head.rfind(name_head)
    if start < 0:
        return None
    return start, f"{name_head} v. {defendant}", name_head, defendant


def _reanchor_parties(cleaned: str, span_start: int, row: "ExtractedCitation", earlier: list[tuple[int, int]]) -> Optional[int]:
    """eyecite's parties could not be anchored right before the cite: read them from the text there.

    eyecite 2.7.8 hands a citation that follows ``"..., 540 U.S. 644 (2004). "`` the
    previous citation's defendant and no plaintiff ("Husain, 174 F.3d 352" for
    "Greenleaf v. Garlock, Inc., 174 F.3d 352"), which made real cases read "Likely not a
    real case" (T09). The caption is re-read from the text between the previous citation
    and this one; when none is there, parties that only occur before the previous
    citation are dropped (they belong to it). Returns the case-name start offset or None.
    """
    prev_end = max((e for _s, e in earlier), default=0)
    if prev_end and _PARALLEL_GAP.fullmatch(cleaned[prev_end:span_start]):
        return None  # a parallel member ("516 U.S. 217, 116 S. Ct. 629"): it shares the first cite's caption
    w0 = max(prev_end, span_start - 200)
    window = cleaned[w0:span_start]
    name = _heuristic_name(window)
    if name:
        rel_start, _full, pl, df = name
        row.plaintiff = _ws(pl)
        row.defendant = _ws(df)
        return w0 + rel_start
    if prev_end and not any(p and p in window for p in (row.plaintiff, row.defendant)):
        row.plaintiff = None
        row.defendant = None
    return None


def _year_and_court(cleaned: str, after_start: int, limit: int, metadata_year, volume: Optional[int], cite_type: Optional[str]) -> tuple[Optional[int], Optional[str]]:
    window = cleaned[after_start : min(limit, after_start + 60)]
    m = _YEAR_PAREN.search(window)
    if m:
        return int(m.group(2)), (_ws(m.group(1)) or None)
    y = _int(metadata_year)
    if y is not None and str(y) in cleaned[after_start : min(limit, after_start + 80)]:
        return y, None
    if volume is not None and 1750 <= volume <= 2099 and cite_type in ("neutral", "specialty_west", "specialty_lexis"):
        return volume, None
    return None, None


def _paren_end(cleaned: str, after_start: int, limit: int) -> Optional[int]:
    window = cleaned[after_start : min(limit, after_start + 60)]
    m = _YEAR_PAREN.search(window)
    if not m:
        return None
    between = window[: m.start()]
    if between.strip(" ,") and not re.fullmatch(r"[\s,]*(?:at\s+)?[\d\-–, n.]*", between):
        return None
    return after_start + m.end()


def _resolve_known_reporter(raw: str) -> Optional[tuple[str, Optional[str]]]:
    """(canonical short name, cite_type) when the regex catch actually names a reporters_db edition."""
    try:
        from reporters_db import EDITIONS, REPORTERS
    except Exception:  # pragma: no cover
        return None
    key = raw.replace(" ", "").replace("'", "").lower()
    for edition in EDITIONS:
        if edition.replace(" ", "").replace("'", "").lower() == key:
            base = EDITIONS[edition]
            cite_type = None
            for rep in REPORTERS.get(base, []):
                if edition in rep.get("editions", {}):
                    cite_type = rep.get("cite_type")
                    break
            return edition, cite_type
    return None


# --------------------------------------------------------------------------- #
# Extraction
# --------------------------------------------------------------------------- #


def extract_citations(text: str) -> list[CitationInput]:
    """All citations in ``text`` in filing order; see the module docstring for every field."""
    cleaned, to_raw = clean_filing_text(text)
    has_pages = "\f" in text

    def page_of(cleaned_offset: int) -> Optional[int]:
        if not has_pages:
            return 1
        return text[: to_raw[min(cleaned_offset, len(cleaned))]].count("\f") + 1

    found = get_citations(cleaned)
    covered: list[tuple[int, int]] = [c.span() for c in found]

    rows: list[ExtractedCitation] = []
    spans: list[tuple[int, int]] = []  # core spans in output order (for boundaries)
    name_starts: list[Optional[int]] = []

    for c in found:
        kind = _kind_of(c)
        if kind is None:
            continue
        s, e = c.span()
        md = c.metadata
        groups = getattr(c, "groups", {}) or {}
        eg = getattr(c, "edition_guess", None)
        reporter = _ws(eg.short_name) if eg is not None else _ws(groups.get("reporter"))
        cite_type = None
        if eg is not None:
            try:
                cite_type = eg.reporter.cite_type
            except AttributeError:
                cite_type = None
        row = ExtractedCitation(
            text=cleaned[s:e],
            span=(s, e),
            filing_page=page_of(s),
            volume=_int(groups.get("volume")) if kind != "statute" else None,
            reporter=reporter,
            page=_int(groups.get("page")) if kind != "statute" else None,
            pin_cite=_ws(getattr(md, "pin_cite", None)),
            plaintiff=_ws(getattr(md, "plaintiff", None)) if kind == "full" else None,
            defendant=_ws(getattr(md, "defendant", None)) if kind == "full" else None,
            court=getattr(md, "court", None) or None,
            kind=kind,
            cite_type=cite_type,
        )
        name_start = _case_name_start(cleaned, s, row.plaintiff, row.defendant) if kind == "full" else None
        if kind == "full" and name_start is None and (row.plaintiff or row.defendant):
            name_start = _reanchor_parties(cleaned, s, row, [sp for sp in covered if sp[1] <= s])
        rows.append(row)
        spans.append((s, e))
        name_starts.append(name_start)

    # Unrecognized-reporter catch on uncovered spans (§2 step 1).
    for m in _CATCH.finditer(cleaned):
        ms, me = m.start(), m.end()
        if any(a < me and ms < b for a, b in covered):
            continue
        rep_raw = m.group(2).strip()
        toks = rep_raw.split()
        if not (any("." in t for t in toks) or any(_ORDINAL.match(t) for t in toks)):
            continue
        lows = [t.lower() for t in toks]
        if any(t in _MONTHS or t in _BAD_REPORTER_TOKENS for t in lows) or "fed. reg." in rep_raw.lower():
            continue
        before_toks = cleaned[max(0, ms - 200) : ms].split()[-6:]
        if any(t.lower().strip(",;:") in _BAD_BEFORE_TOKENS for t in before_toks):
            continue
        before120 = cleaned[max(0, ms - 120) : ms]
        after40 = cleaned[me : me + 40]
        year_after = _YEAR_PAREN.search(after40)
        if not (re.search(r"\sv\.\s|\bIn re\b", before120) or year_after):
            continue
        known = _resolve_known_reporter(rep_raw)
        volume, page = int(m.group(1)), int(m.group(3))
        row = ExtractedCitation(
            text=cleaned[ms:me],
            span=(ms, me),
            filing_page=page_of(ms),
            volume=volume,
            reporter=known[0] if known else rep_raw,
            page=page,
            kind="full" if known else "unrecognized",
            cite_type=known[1] if known else None,
        )
        name = _heuristic_name(cleaned[max(0, ms - 200) : ms])
        name_start = None
        if name:
            rel_start, _full, pl, df = name
            name_start = max(0, ms - 200) + rel_start
            row.plaintiff = _ws(pl)
            row.defendant = _ws(df)
        rows.append(row)
        spans.append((ms, me))
        name_starts.append(name_start)
        covered.append((ms, me))

    # Filing order.
    order = sorted(range(len(rows)), key=lambda i: spans[i][0])
    rows = [rows[i] for i in order]
    spans = [spans[i] for i in order]
    name_starts = [name_starts[i] for i in order]
    n = len(rows)

    # Year, court, cite_text, history, slip op., duplicates.
    seen: dict[tuple[Optional[int], Optional[str], Optional[int]], int] = {}
    for i, row in enumerate(rows):
        s, e = spans[i]
        # where the text belonging to this citation ends: the next citation's case name (or core
        # cite), skipping parallel members ("516 U.S. 217, 116 S. Ct. 629, ... (1996)")
        j, end_j = i + 1, e
        while j < n and name_starts[j] is None and _PARALLEL_GAP.fullmatch(cleaned[end_j : spans[j][0]]):
            end_j = spans[j][1]
            j += 1
        if j < n:
            nxt = name_starts[j] if name_starts[j] is not None else spans[j][0]
            limit = max(e, nxt)
        else:
            limit = len(cleaned)
        if row.kind in ("full", "unrecognized"):
            md_year = None
            if row.kind == "full":
                for c in found:
                    if c.span() == (s, e):
                        md_year = getattr(c.metadata, "year", None)
                        break
            pin_end = e
            if row.pin_cite and row.kind == "full":
                mp = re.match(r"[,\s]*(?:at\s+)?" + re.escape(row.pin_cite) + r"(?!\d)", cleaned[e:limit])
                if mp:
                    pin_end = e + mp.end()
            year, court_text = _year_and_court(cleaned, pin_end, limit, md_year, row.volume, row.cite_type)
            row.year = year
            if row.court is None and court_text:
                row.court = court_text
            paren_end = _paren_end(cleaned, pin_end, limit)
            start = name_starts[i]
            if start is not None:
                end = paren_end if paren_end is not None else pin_end
                row.cite_text = _ws(cleaned[start:end]) or row.text
            else:
                core = _ws(cleaned[s:pin_end]) or row.text
                if row.plaintiff or row.defendant:
                    name = " v. ".join(p for p in (row.plaintiff, row.defendant) if p)
                    core = f"{name}, {core}"
                if paren_end is not None:
                    core = f"{core} {cleaned[pin_end:paren_end].strip()}"
                row.cite_text = _ws(core) or row.text
            if row.kind == "full":
                before40 = cleaned[max(0, s - 40) : s]
                mh = _HISTORY.search(before40)
                if mh and (name_starts[i] is None or max(0, s - 40) + mh.start() < name_starts[i]):
                    row.history = _ws(mh.group(0))
                row.slip_op = bool(_SLIP_OP.search(cleaned[e : e + 40]))
                key = (row.volume, row.reporter, row.page)
                if key in seen:
                    row.duplicate_of = seen[key]
                else:
                    seen[key] = i
        else:
            row.cite_text = row.text

    # Quotes: after "quoting" first (consumed), then the window before each citation.
    passages = _quoted_passages(cleaned)
    consumed: set[int] = set()
    for i, row in enumerate(rows):
        s, e = spans[i]
        stop = spans[i + 1][0] if i + 1 < n else len(cleaned)
        window_end = min(stop, e + 400)
        for mq in _QUOTING.finditer(cleaned, e, window_end):
            for k, (qs, cs, ce, qe) in enumerate(passages):
                if k in consumed or qs < mq.end() or qs - mq.end() > 80 or qe > stop:
                    continue
                row.quotes.append(cleaned[cs:ce])
                consumed.add(k)
                break
    for i, row in enumerate(rows):
        s, e = spans[i]
        prev_end = spans[i - 1][1] if i else 0
        for k, (qs, cs, ce, qe) in enumerate(passages):
            if k in consumed or qs < prev_end or qe > s or s - qe > 400:
                continue
            row.quotes.append(cleaned[cs:ce])
            consumed.add(k)

    return list(rows)
