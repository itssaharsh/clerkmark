"""The deterministic classifier (DECISION-RULE.md §2, §3, §5–§7; ADR-0002).

Pure functions over already-fetched data. No I/O, no network, no model. The
memo orchestrator (T05) builds a :class:`RuleContext` per citation from the
CapClient's output and calls :func:`classify`; quote results from ``quotes.py``
are folded in afterwards with :func:`apply_quote_check`, parallel members of a
citation group with :func:`apply_parallel_cites`.

Expected shapes (all plain JSON as CAP serves it; see DECISION-RULE §1.4–§1.5)
-----------------------------------------------------------------------------
``RuleContext``
    ``slug``            CAP reporter slug for the citation's reporter, ``None`` when
                        ReportersMetadata has none (``F.4th``, ``N.Y.S.3d``, ``WL``).
    ``reporter``        :class:`ReporterMeta` (reporters_db edition + CAP years) or
                        ``None`` when reporters_db does not know the reporter either.
                        :func:`reporter_meta` builds it.
    ``volumes``         ``{volume_number(str): [VolumesMetadata row, ...]}`` for the
                        slug. ``None`` = the index is *Absent* (404). Duplicate rows
                        for one volume are fine.
    ``vmax``            ``max(int(v) for v in volumes)``; derived when omitted.
    ``cases``           the ``CasesMetadata.json`` rows of the cited volume (union
                        of every duplicate volume row, any order). ``None`` = Absent.
    ``volumes_failed`` / ``cases_failed``
                        a §6.1 failure text (``"timeout"``, ``"server error"``,
                        ``"unreadable reply"``) when that fetch *Failed*; the row is
                        ``not_checked``.
    ``not_checked_reason``
                        pre-decided ``not_checked`` (run limit, per-row exception).
    ``courtlistener_status``
                        HTTP status of the CourtListener citation lookup for this
                        citation, or ``None``; ``200`` upgrades a beyond-coverage
                        row to ``verified`` (source ``CourtListener``).
    ``links``           CAP URLs used for this row, in fetch order (copied to
                        ``evidence.links``).
    ``today_year``      for the §3.2 plausibility note (default 2026).

``CitationInput`` (from ``extract.py``): ``volume``, ``reporter`` (eyecite
``edition_guess.short_name``), ``page``, ``year``, ``court`` (eyecite court id
such as ``ca2`` or the parenthetical text ``2d Cir.``), ``plaintiff``,
``defendant``, ``pin_cite``, ``kind``. ``kind`` other than ``full`` short-circuits:
``id`` / ``supra`` / ``short`` / ``statute`` -> ``skipped``; ``unrecognized`` ->
``unrecognized_reporter``.

Wording: ``reasons[0]`` is the UI-SPEC §9 rule sentence for the class; later
reasons are the DECISION-RULE §6.3 observations and notes. Reasons are
observations, never verdicts; the word "fabricated" never appears in one.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Optional

from . import names
from .models import (
    CitationInput,
    CitationResult,
    ClosestPassage,
    EditionRange,
    Evidence,
    NameHit,
    QuoteCheck,
    RealCase,
    VolumeRange,
    YearMismatch,
    label_for,
)

# §3.1: only a *closed* West edition held to volume 999 makes V >= 1000 red.
# Flip to False once BUILD-NOTES §1 cites a source for F.3d's last volume.
SERIES_CEILING_REQUIRES_CLOSED = True
SERIES_CEILING = 999
US_ORDERS_PAGE = 801
DEFAULT_TODAY_YEAR = 2026

REPORTER_DISPLAY = {"U.S.": "U.S. Reports"}

CLASS_ORDER = (
    "verified",
    "quote_not_found",
    "wrong_cite_exists",
    "not_in_free_corpus",
    "not_checked",
    "unrecognized_reporter",
    "likely_fabricated",
)

_DIGITS = re.compile(r"\d+")


# --------------------------------------------------------------------------- #
# Context dataclasses
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class ReporterMeta:
    """What the two sources say about a reporter (reporters_db edition + CAP ReportersMetadata).

    ``edition_start`` / ``edition_end`` are reporters_db years (``end None`` = open);
    ``cap_start_year`` / ``cap_end_year`` come from ReportersMetadata (the orchestrator may
    replace ``cap_end_year`` by the max non-zero ``end_year`` in VolumesMetadata, §3);
    ``successor`` is the sibling edition that starts after this one (``F.3d`` -> ``F.4th``).
    """

    reporter: str
    cite_type: Optional[str] = None
    edition_start: Optional[int] = None
    edition_end: Optional[int] = None
    edition_end_date: Optional[str] = None
    cap_start_year: Optional[int] = None
    cap_end_year: Optional[int] = None
    slug: Optional[str] = None
    successor: Optional[str] = None
    successor_start: Optional[str] = None


@dataclass
class RuleContext:
    """Already-fetched data for one citation (see the module docstring for shapes)."""

    slug: Optional[str] = None
    reporter: Optional[ReporterMeta] = None
    volumes: Optional[dict[str, list[dict]]] = None
    vmax: Optional[int] = None
    cases: Optional[list[dict]] = None
    volumes_failed: Optional[str] = None
    cases_failed: Optional[str] = None
    not_checked_reason: Optional[str] = None
    courtlistener_status: Optional[int] = None
    links: list[str] = field(default_factory=list)
    today_year: int = DEFAULT_TODAY_YEAR
    _index: Optional["VolumeIndex"] = field(default=None, init=False, repr=False, compare=False)
    _memo: dict = field(default_factory=dict, init=False, repr=False, compare=False)

    def index(self) -> "VolumeIndex":
        """The §1.5 index of ``cases``, built once per context (memoized; ``cases`` is read-only)."""
        if self._index is None:
            self._index = index_volume(self.cases)
        return self._index

    def volume_max(self) -> Optional[int]:
        if self.vmax is not None:
            return self.vmax
        if self.volumes:
            nums = [int(v) for v in self.volumes if str(v).isdigit()]
            return max(nums) if nums else None
        return None

    def volume_min(self) -> Optional[int]:
        if "vmin" not in self._memo:
            nums = [int(v) for v in (self.volumes or {}) if str(v).isdigit()]
            self._memo["vmin"] = min(nums) if nums else None
        return self._memo["vmin"]


def reporter_meta(reporter: str, cap_entry: Optional[dict] = None) -> Optional[ReporterMeta]:
    """Build a :class:`ReporterMeta` from reporters_db plus a CAP ReportersMetadata entry.

    ``reporter`` is eyecite's ``edition_guess.short_name`` (``"F. Supp. 2d"``); ``cap_entry`` is
    the matching ``data/cap/ReportersMetadata.json`` row (``slug``, ``start_year``, ``end_year``)
    or ``None``. Returns ``None`` when reporters_db has no such edition.
    """
    try:
        from reporters_db import EDITIONS, REPORTERS
    except Exception:  # pragma: no cover - reporters_db is a pinned dependency
        return None
    base = EDITIONS.get(reporter)
    if base is None:
        return None
    entry = None
    for candidate in REPORTERS.get(base, []):
        if reporter in candidate.get("editions", {}):
            entry = candidate
            break
    if entry is None:
        return None
    editions = entry["editions"]
    ed = editions[reporter]
    start = ed.get("start")
    end = ed.get("end")
    successor = successor_start = None
    later = [
        (v.get("start"), k)
        for k, v in editions.items()
        if k != reporter and v.get("start") is not None and start is not None and v.get("start") > start
    ]
    if later:
        s, k = min(later)
        successor, successor_start = k, s.date().isoformat()
    cap_entry = cap_entry or {}
    return ReporterMeta(
        reporter=reporter,
        cite_type=entry.get("cite_type"),
        edition_start=start.year if start else None,
        edition_end=end.year if end else None,
        edition_end_date=end.date().isoformat() if end else None,
        cap_start_year=cap_entry.get("start_year") or None,
        cap_end_year=cap_entry.get("end_year") or None,
        slug=cap_entry.get("slug"),
        successor=successor,
        successor_start=successor_start,
    )


# --------------------------------------------------------------------------- #
# §1.5 volume index
# --------------------------------------------------------------------------- #


@dataclass
class IndexedCase:
    """One CasesMetadata row with parsed pages (``first_page`` None = no page digits)."""

    raw: dict
    id: Any
    name: str
    first_page: Optional[int]
    last_page: Optional[int]
    decision_date: str
    court: str
    court_abbreviation: Optional[str]
    cites: list[str]
    file_name: Optional[str]

    @property
    def span(self) -> int:
        if self.first_page is None or self.last_page is None:
            return -1
        return self.last_page - self.first_page

    def official_cite(self, volume: int, reporter: str) -> str:
        for c in self.raw.get("citations") or []:
            if c.get("type") == "official" and c.get("cite"):
                return c["cite"]
        return f"{volume} {reporter} {self.first_page}" if self.first_page is not None else self.cites[0] if self.cites else ""

    def to_real_case(self, volume: int, reporter: str) -> RealCase:
        first = self.first_page if self.first_page is not None else 0
        last = self.last_page if self.last_page is not None else first
        official = self.official_cite(volume, reporter)
        return RealCase(
            name=self.name,
            first_page=first,
            last_page=last,
            decision_date=self.decision_date,
            court=self.court,
            court_abbreviation=self.court_abbreviation,
            cite=official,
            file_name=self.file_name,
            id=self.id if isinstance(self.id, int) else None,
            parallel_cites=[c for c in self.cites if c != official],
        )


@dataclass
class VolumeIndex:
    cases: list[IndexedCase]           # cases with page digits (page lookups)
    all_cases: list[IndexedCase]       # every case (name search)
    by_first: dict[int, list[IndexedCase]]
    by_cite: dict[str, list[IndexedCase]]
    covered: set[int]
    max_last: Optional[int]
    by_name: dict[str, list[IndexedCase]] = field(default_factory=dict)

    def same_name(self, case: "IndexedCase") -> list["IndexedCase"]:
        """Other entries carrying this caption (orders pages, duplicates)."""
        return [c for c in self.by_name.get(case.name, []) if c is not case]

    def spans(self, page: int) -> list[IndexedCase]:
        return [c for c in self.cases if c.first_page < page <= c.last_page]

    def min_first(self) -> Optional[int]:
        return min(self.covered) if self.covered else None


def _digits(s: Any) -> list[int]:
    return [int(x) for x in _DIGITS.findall(str(s or ""))]


def _cite_key(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip().lower()


def index_volume(cases: Optional[list[dict]]) -> VolumeIndex:
    """§1.5: parse pages, dedupe by case id, build the page and official-cite indexes."""
    seen: set[Any] = set()
    all_cases: list[IndexedCase] = []
    for row in cases or []:
        cid = row.get("id")
        key = cid if cid is not None else (row.get("name_abbreviation"), row.get("first_page"), row.get("last_page"))
        if key in seen:
            continue
        seen.add(key)
        fd = _digits(row.get("first_page"))
        ld = _digits(row.get("last_page"))
        first = min(fd) if fd else None
        last = (max(ld) if ld else first) if first is not None else None
        if first is not None and last is not None and last < first:
            last = first
        court = row.get("court") or {}
        all_cases.append(
            IndexedCase(
                raw=row,
                id=cid,
                name=row.get("name_abbreviation") or row.get("name") or "",
                first_page=first,
                last_page=last,
                decision_date=str(row.get("decision_date") or ""),
                court=court.get("name") or "",
                court_abbreviation=court.get("name_abbreviation"),
                cites=[c.get("cite") for c in (row.get("citations") or []) if c.get("cite")],
                file_name=row.get("file_name"),
            )
        )
    paged = [c for c in all_cases if c.first_page is not None]
    by_name: dict[str, list[IndexedCase]] = {}
    for c in all_cases:
        by_name.setdefault(c.name, []).append(c)
    by_first: dict[int, list[IndexedCase]] = {}
    by_cite: dict[str, list[IndexedCase]] = {}
    covered: set[int] = set()
    for c in paged:
        by_first.setdefault(c.first_page, []).append(c)
        covered.update(range(c.first_page, c.last_page + 1))
        for cite in c.cites:
            by_cite.setdefault(_cite_key(cite), []).append(c)
    return VolumeIndex(
        cases=paged,
        all_cases=all_cases,
        by_first=by_first,
        by_cite=by_cite,
        covered=covered,
        max_last=max(covered) if covered else None,
        by_name=by_name,
    )


def decision_year(case: IndexedCase) -> Optional[int]:
    m = re.match(r"(\d{4})", case.decision_date or "")
    return int(m.group(1)) if m else None


# --------------------------------------------------------------------------- #
# Small helpers
# --------------------------------------------------------------------------- #


def label_for_result(result: CitationResult) -> str:
    """The UI-SPEC §9 label the row must carry (used by tests as the oracle)."""
    kind = result.citation.kind if result.citation else "full"
    has_quote = bool(result.citation and result.citation.quotes) or bool(
        result.quote_check and result.quote_check.status == "verbatim"
    )
    return label_for(result.class_, has_quote=has_quote, pincite_unverified=result.pincite_unverified, kind=kind)


def best_class(classes: list[str]) -> str:
    """Step 10: the best class of a citation group, in the order of DECISION-RULE §2."""
    ranked = [c for c in CLASS_ORDER if c in classes]
    return ranked[0] if ranked else classes[0]


def _display(reporter: str) -> str:
    return REPORTER_DISPLAY.get(reporter, reporter)


def _vrp(volume: Any, reporter: str, page: Any) -> str:
    return f"{volume} {reporter} {page}"


def _range(case: IndexedCase) -> str:
    return f"{case.first_page}–{case.last_page}"


def _filed_caption(cite: CitationInput) -> str:
    pl, df = cite.plaintiff, cite.defendant
    if pl and df:
        return f"{pl} v. {df}"
    return pl or df or ""


def _default_cite_text(cite: CitationInput) -> str:
    caption = _filed_caption(cite)
    text = cite.text or _vrp(cite.volume, cite.reporter or "", cite.page)
    paren = " ".join(str(x) for x in (cite.court, cite.year) if x)
    out = f"{caption}, {text}" if caption else text
    if paren:
        out += f" ({paren})"
    return out


def _result(
    cite: CitationInput,
    ctx: RuleContext,
    class_: str,
    reasons: list[str],
    *,
    row: int,
    cite_text: Optional[str],
    evidence: Optional[Evidence] = None,
    source: str = "none",
    pincite_unverified: bool = False,
) -> CitationResult:
    ev = evidence or Evidence()
    if ctx.links and not ev.links:
        ev.links = list(ctx.links)
    return CitationResult(
        row=row,
        cite_text=cite_text if cite_text is not None else _default_cite_text(cite),
        class_=class_,
        reasons=reasons,
        evidence=ev,
        source=source,
        pincite_unverified=pincite_unverified,
        citation=cite,
    )


def _volume_range(ctx: RuleContext, reporter: str, volume: int, *, held: bool, max_last: Optional[int] = None) -> VolumeRange:
    vmin = ctx.volume_min()
    vmax = ctx.volume_max()
    cap_end = cap_end_year(ctx)
    return VolumeRange(
        reporter=reporter,
        vmin=vmin if vmin is not None else 1,
        vmax=vmax if vmax is not None else 0,
        held=held,
        cited=volume,
        cap_end_year=cap_end,
        max_last_page=max_last,
        note=f"{_display(reporter)} · volumes {vmin if vmin is not None else '?'}–{vmax if vmax is not None else '?'} in the free library · cited: {volume}",
    )


def cap_end_year(ctx: RuleContext) -> Optional[int]:
    """§3: max non-zero ``end_year`` in VolumesMetadata, else ReportersMetadata ``end_year``."""
    if "cap_end" not in ctx._memo:
        ctx._memo["cap_end"] = _cap_end_year(ctx)
    return ctx._memo["cap_end"]


def _cap_end_year(ctx: RuleContext) -> Optional[int]:
    ends = []
    for rows in (ctx.volumes or {}).values():
        for row in rows:
            for key in ("end_year", "start_year"):
                y = row.get(key)
                if isinstance(y, int) and y > 0:
                    ends.append(y)
    if ends:
        return max(ends)
    return ctx.reporter.cap_end_year if ctx.reporter else None


# --------------------------------------------------------------------------- #
# classify
# --------------------------------------------------------------------------- #


def classify(cite: CitationInput, ctx: RuleContext, *, row: int = 1, cite_text: Optional[str] = None) -> CitationResult:
    """DECISION-RULE §2 steps 1–8 for one citation. Pure; never raises for odd input.

    ``row`` and ``cite_text`` are the memo row number and the printed citation; the
    orchestrator sets them (defaults: 1 and ``"<A> v. <B>, <text> (<court> <year>)"``).
    """
    try:
        return _classify(cite, ctx, row=row, cite_text=cite_text)
    except Exception as exc:  # §6.1: one bad row never sinks the memo
        return _result(
            cite,
            ctx,
            "not_checked",
            [
                f"Could not be checked: the rule engine failed on this citation ({type(exc).__name__}). Run again or check by hand."
            ],
            row=row,
            cite_text=cite_text,
        )


def _classify(cite: CitationInput, ctx: RuleContext, *, row: int, cite_text: Optional[str]) -> CitationResult:
    reporter = cite.reporter or ""
    meta = ctx.reporter

    # §1.6 pre-classification kinds
    if cite.kind in ("id", "supra", "short"):
        return _result(cite, ctx, "skipped", ["Short-form citation (Id., supra or short form); the full citation it points to is checked instead."], row=row, cite_text=cite_text)
    if cite.kind == "statute":
        return _result(cite, ctx, "skipped", ["Statute, regulation or journal citation; out of scope."], row=row, cite_text=cite_text)
    # §1.6 items 1–2: extract.py marks these on ExtractedCitation (history / slip_op); CitationInput has neither.
    history = getattr(cite, "history", None)
    if history:
        return _result(cite, ctx, "skipped", [f"Subsequent-history citation ({history}); not checked."], row=row, cite_text=cite_text)
    if getattr(cite, "slip_op", False):
        return _result(
            cite, ctx, "not_in_free_corpus",
            ["State slip citation; not in the free library. Slip opinion; not held by the free corpus."],
            row=row, cite_text=cite_text,
        )
    if ctx.not_checked_reason:
        return _result(cite, ctx, "not_checked", [f"Could not be checked: {ctx.not_checked_reason}. Run again or check by hand."], row=row, cite_text=cite_text)

    # Step 1 — unrecognized reporter
    if cite.kind == "unrecognized" or (meta is None and ctx.slug is None):
        shown = reporter or cite.text or "?"
        return _result(
            cite,
            ctx,
            "unrecognized_reporter",
            [
                f"No reporter called '{shown}' in reporters_db or the Caselaw Access Project.",
                f"Citation-like string with a reporter this tool does not know: '{shown}'. Check the reporter abbreviation by hand.",
            ],
            row=row,
            cite_text=cite_text,
            evidence=Evidence(matched_text=cite.text or None),
        )

    # Step 2 — no free corpus holds these
    cite_type = meta.cite_type if meta else None
    if cite_type in ("specialty_west", "specialty_lexis"):
        which = "Westlaw" if cite_type == "specialty_west" else "Lexis"
        return _result(
            cite,
            ctx,
            "not_in_free_corpus",
            [f"{which}-only citation; no free text exists. Proprietary citation (Westlaw/Lexis); not checkable in a free corpus."],
            row=row,
            cite_text=cite_text,
            evidence=Evidence(cite_type=cite_type),
        )
    if cite_type == "neutral":
        return _result(
            cite,
            ctx,
            "not_in_free_corpus",
            ["Public-domain neutral citation; the free corpus does not index this format. Check the court's own site."],
            row=row,
            cite_text=cite_text,
            evidence=Evidence(cite_type=cite_type),
        )

    notes: list[str] = []
    evidence = Evidence()

    # Step 3 — edition-year note (never a class)
    year = cite.year
    if year is not None and meta is not None:
        starts = [y for y in (meta.edition_start, meta.cap_start_year) if y]
        ends = [y for y in (meta.edition_end or 9999, meta.cap_end_year) if y]
        if starts:
            lo = min(starts) - 1
            hi = max(ends) + 1 if ends else 10000
            if year < lo or year > hi:
                shown_hi = "open" if hi >= 10000 else str(hi)
                notes.append(f"The filing's year {year} is outside the years both sources give for {reporter} ({lo}–{shown_hi}).")
                evidence.edition_range = EditionRange(reporter=reporter, start=lo, end=None if hi >= 10000 else hi, note=f"{lo}–{shown_hi}")

    # Step 3b — CAP slug
    if ctx.slug is None:
        ed = f"{meta.edition_start or '?'}–{meta.edition_end or 'open'}" if meta else "unknown"
        ev = Evidence(edition_range=EditionRange(reporter=reporter, start=meta.edition_start if meta else None, end=meta.edition_end if meta else None, note=ed))
        return _result(
            cite,
            ctx,
            "not_in_free_corpus",
            [f"{reporter} is not held by the Caselaw Access Project (reporters_db edition {ed}). Check CourtListener or Westlaw."] + notes,
            row=row,
            cite_text=cite_text,
            evidence=ev,
        )

    volume = cite.volume
    page = cite.page
    if volume is None:
        return _result(cite, ctx, "not_checked", ["Could not be checked: the citation has no volume number. Check by hand."] + notes, row=row, cite_text=cite_text)

    # Step 4 — volume range
    if ctx.volumes_failed:
        return _result(
            cite, ctx, "not_checked",
            [f"Could not be checked: the free corpus did not answer for {volume} {reporter} ({ctx.volumes_failed}). Run again or check by hand."] + notes,
            row=row, cite_text=cite_text,
        )
    if ctx.volumes is None:
        return _result(
            cite, ctx, "not_in_free_corpus",
            [f"{reporter} is listed by the free corpus but its volume index is not published. Check CourtListener or Westlaw."] + notes,
            row=row, cite_text=cite_text,
        )
    vmax = ctx.volume_max()
    if vmax is not None and volume > vmax:
        return _beyond_coverage(cite, ctx, reporter, volume, vmax, notes, row=row, cite_text=cite_text)
    if str(volume) not in ctx.volumes:
        evidence.volume_range = _volume_range(ctx, reporter, volume, held=False)
        return _result(
            cite, ctx, "not_in_free_corpus",
            [f"Volume {volume} of {reporter} is not in the free corpus. Check CourtListener or Westlaw."] + notes,
            row=row, cite_text=cite_text, evidence=evidence, source="CAP",
        )

    # Step 5 — cases in the volume
    if ctx.cases_failed:
        return _result(
            cite, ctx, "not_checked",
            [f"Could not be checked: the free corpus did not answer for {volume} {reporter} ({ctx.cases_failed}). Run again or check by hand."] + notes,
            row=row, cite_text=cite_text,
        )
    if ctx.cases is None:
        evidence.volume_range = _volume_range(ctx, reporter, volume, held=True)
        return _result(
            cite, ctx, "not_in_free_corpus",
            [f"Volume {volume} of {reporter} is listed but its cases are not in the free corpus. Check CourtListener or Westlaw."] + notes,
            row=row, cite_text=cite_text, evidence=evidence, source="CAP",
        )
    if page is None:
        return _result(cite, ctx, "not_checked", ["Could not be checked: the citation has no page number. Check by hand."] + notes, row=row, cite_text=cite_text)

    idx = ctx.index()
    evidence.volume_range = _volume_range(ctx, reporter, volume, held=True, max_last=idx.max_last)

    # §5.2 safer reading: a filing with only generic party names ("United States v. Doe")
    # has nothing to search for; treat it like a filing with no names (see the T04 report).
    no_names = not cite.plaintiff and not cite.defendant
    all_generic = not no_names and not names.has_distinctive_party(cite)
    nameless = no_names or all_generic
    names_note = None
    if all_generic:
        names_note = f"The filing gives only generic party names ({_filed_caption(cite)}); they cannot pick a case out of the volume."

    def match_of(case: IndexedCase) -> str:
        if nameless:
            return "no_names"
        return names.match(cite, case.raw)

    # Step 6a — cases that begin at the page or carry its official cite
    candidates = list(idx.by_cite.get(_cite_key(_vrp(volume, reporter, page)), []))
    for c in idx.by_first.get(page, []):
        if c not in candidates:
            candidates.append(c)
    context = None
    if candidates:
        matches = [(match_of(c), c) for c in candidates]
        fulls = [c for m, c in matches if m == "full"]
        if fulls:
            best = max(fulls, key=lambda c: (c.span, -c.first_page))
            return _verified(cite, ctx, idx, best, reporter, volume, page, notes, evidence, row=row, cite_text=cite_text)
        partials = [c for m, c in matches if m == "partial"]
        if partials:
            best = max(partials, key=lambda c: (c.span, -c.first_page))
            evidence.real_case_at_page = best.to_real_case(volume, reporter)
            reasons = [
                f"The case that begins at {_vrp(volume, reporter, page)} is {best.name} ({best.court}, {best.decision_date}); the filing calls it {_filed_caption(cite)} (one party name matches)."
            ]
            _year_note(cite, best, reasons, evidence)
            return _result(cite, ctx, "wrong_cite_exists", reasons + notes, row=row, cite_text=cite_text, evidence=evidence, source="CAP")
        if nameless:
            best = max(candidates, key=lambda c: (c.span, -c.first_page))
            listed = "; ".join(c.name for c in candidates)
            evidence.real_case_at_page = best.to_real_case(volume, reporter)
            evidence.other_entries = [c.to_real_case(volume, reporter) for c in candidates if c is not best]
            if names_note:
                reasons = [f"{names_note} The case that begins at {_vrp(volume, reporter, page)} is {listed}."]
            else:
                reasons = [f"The filing gives no party names; the case that begins at {_vrp(volume, reporter, page)} is {listed}."]
            _year_note(cite, best, reasons, evidence)
            return _result(cite, ctx, "verified", reasons + notes, row=row, cite_text=cite_text, evidence=evidence, source="CAP")
        context = "page_hit"
        at_page = max(candidates, key=lambda c: (c.span, -c.first_page))
    else:
        spanning = idx.spans(page)
        if spanning:
            matches = [(match_of(c), c) for c in spanning]
            fulls = [c for m, c in matches if m == "full"]
            partials = [c for m, c in matches if m == "partial"]
            if fulls or partials or nameless:
                best = max(fulls or partials or spanning, key=lambda c: (c.span, -c.first_page))
                evidence.real_case_at_page = best.to_real_case(volume, reporter)
                if fulls:
                    reasons = [f"{best.name} begins at {_vrp(volume, reporter, best.first_page)}; page {page} is inside it ({_range(best)})."]
                elif partials:
                    reasons = [
                        f"Page {page} is inside {best.name} ({_range(best)}), which begins at {best.first_page}; one party name differs from the filing's {_filed_caption(cite)}."
                    ]
                else:
                    reasons = [f"Page {page} is inside {best.name} ({_range(best)}), which begins at {best.first_page}."]
                    if names_note:
                        reasons.append(names_note)
                _year_note(cite, best, reasons, evidence)
                return _result(cite, ctx, "wrong_cite_exists", reasons + notes, row=row, cite_text=cite_text, evidence=evidence, source="CAP")
            context = "inside_span"
            at_page = max(spanning, key=lambda c: (c.span, -c.first_page))
            candidates = spanning
        else:
            context = "gap"
            at_page = None
            gap_kind = "beyond_end" if idx.max_last is not None and page > idx.max_last else "hole"

    # Step 7 — name search across the volume
    searched = names.distinctive_parties(cite)
    evidence.searched_names = searched
    hit, nearest = _name_search(cite, idx, volume, reporter)
    if nearest is not None:
        evidence.nearest_caption = nearest
    if hit is not None:
        hit_case, kind = hit
        evidence.name_hit = _name_hit(hit_case, kind, cite, volume, reporter)
        if at_page is not None:
            evidence.real_case_at_page = at_page.to_real_case(volume, reporter)
        others = idx.same_name(hit_case)
        evidence.other_entries = [c.to_real_case(volume, reporter) for c in others]
        if kind == "full":
            reasons = [f"{hit_case.name} is in this volume at {_vrp(volume, reporter, hit_case.first_page)}, not page {page}."]
            if at_page is not None:
                reasons[0] += f" Page {page} belongs to {at_page.name} ({_range(at_page)})."
        else:
            reasons = [f"Only one party name matches a case in this volume: {hit_case.name} at {_vrp(volume, reporter, hit_case.first_page)}."]
            if at_page is not None:
                reasons[0] += f" Page {page} belongs to {at_page.name} ({_range(at_page)})."
        _year_note(cite, hit_case, reasons, evidence)
        return _result(cite, ctx, "wrong_cite_exists", reasons + notes, row=row, cite_text=cite_text, evidence=evidence, source="CAP")

    # no hit
    held_lo = idx.min_first()
    held_hi = idx.max_last
    if context == "gap":
        if nameless:
            reasons = [
                f"Page {page} of {volume} {reporter} is not in the free corpus (it holds pages {held_lo}–{held_hi} of this volume with gaps); "
                "the filing gives no party names and no case text sits at this page."
            ]
            if names_note:
                reasons.append(names_note)
        elif gap_kind == "hole":
            reasons = [
                f"Page {page} of {volume} {reporter} is not in the free corpus (it holds pages {held_lo}–{held_hi} of this volume with gaps); "
                f"no case named {_or_names(searched)} in the pages it holds."
            ]
        else:
            reasons = [
                f"The last case the free corpus holds in {volume} {reporter} ends at page {held_hi}; page {page} is beyond it; "
                f"no case named {_or_names(searched)} in the volume."
            ]
        return _result(cite, ctx, "not_in_free_corpus", reasons + notes, row=row, cite_text=cite_text, evidence=evidence, source="CAP")

    # page_hit / inside_span with no matching name anywhere in the volume
    assert at_page is not None
    evidence.real_case_at_page = at_page.to_real_case(volume, reporter)
    evidence.other_entries = [c.to_real_case(volume, reporter) for c in candidates if c is not at_page]
    if reporter == "U.S." and (page >= US_ORDERS_PAGE or all(c.span == 0 for c in candidates)):
        listed = "; ".join(c.name for c in candidates)
        reasons = [f"Orders pages of U.S. Reports are not fully held by the free corpus; the entries it holds at page {page} are {listed}."]
        return _result(cite, ctx, "not_in_free_corpus", reasons + notes, row=row, cite_text=cite_text, evidence=evidence, source="CAP")

    party = searched[0] if searched else _filed_caption(cite)
    if context == "page_hit":
        reasons = [f"{at_page.name} begins at page {page}; no case named {party} in volume {volume}."]
    else:
        reasons = [f"Page {page} belongs to {at_page.name}, {volume} {reporter} {_range(at_page)}. No case named {party} in volume {volume}."]
    if len(searched) > 1:
        reasons.append(f"No case in volume {volume} {reporter} is named {_or_names(searched)}; the nearest caption is shown.")
    _year_note(cite, at_page, reasons, evidence)
    return _result(cite, ctx, "likely_fabricated", reasons + notes, row=row, cite_text=cite_text, evidence=evidence, source="CAP")


def _or_names(searched: list[str]) -> str:
    if not searched:
        return "either party"
    return " or ".join(searched)


def _verified(
    cite: CitationInput,
    ctx: RuleContext,
    idx: VolumeIndex,
    case: IndexedCase,
    reporter: str,
    volume: int,
    page: int,
    notes: list[str],
    evidence: Evidence,
    *,
    row: int,
    cite_text: Optional[str],
) -> CitationResult:
    evidence.real_case_at_page = case.to_real_case(volume, reporter)
    others = idx.same_name(case)
    evidence.other_entries = [c.to_real_case(volume, reporter) for c in others]
    evidence.running_head = f"{_vrp(volume, reporter, case.first_page)} · {case.name.upper()} · {case.court_abbreviation or case.court} · {case.decision_date}"
    evidence.page_marker = str(page)
    official = case.official_cite(volume, reporter)
    reasons = [f"Found in the free corpus: {case.name}, {official} ({case.court}, {case.decision_date})."]
    if _cite_key(official) != _cite_key(_vrp(volume, reporter, case.first_page)):
        reasons.append(f"The entry is printed at page {case.first_page} of volume {volume}.")
    _year_note(cite, case, reasons, evidence)
    pin = False
    if cite.pin_cite:
        pin = True
        reasons.append(f"Pin page {cite.pin_cite.replace('at ', '').strip()} not verifiable: the free corpus text has no page numbers.")
    return _result(cite, ctx, "verified", reasons + notes, row=row, cite_text=cite_text, evidence=evidence, source="CAP", pincite_unverified=pin)


def _year_note(cite: CitationInput, case: IndexedCase, reasons: list[str], evidence: Evidence) -> None:
    """Step 8: a year that disagrees with the decision date is a note, never a class.

    DECISION-RULE step 8 says ``> 1``; §7 rows 28 and 29 expect the note for a one-year
    slip (Saks 1986, Iqbal 2010). The rows are the more specific statement and a note
    never changes a class, so any disagreement is noted.
    """
    if cite.year is None:
        return
    dy = decision_year(case)
    if dy is None:
        return
    if cite.year != dy:
        reasons.append(f"The filing gives year {cite.year}; the opinion is dated {case.decision_date}.")
        evidence.year_mismatch = YearMismatch(cited=cite.year, decided=case.decision_date)


def _name_hit(case: IndexedCase, kind: str, cite: CitationInput, volume: int, reporter: str) -> NameHit:
    rc = case.to_real_case(volume, reporter)
    return NameHit(
        **rc.model_dump(),
        score=names.best_score(cite, case.raw),
        match=kind,  # type: ignore[arg-type]
        court_consistent=names.court_consistent(cite.court, case.court) if (cite.court and case.court) else None,
    )


def _name_search(
    cite: CitationInput, idx: VolumeIndex, volume: int, reporter: str
) -> tuple[Optional[tuple[IndexedCase, str]], Optional[NameHit]]:
    """Step 7: rank hits by span desc then first page asc; partial hits need a consistent court."""
    if not names.has_distinctive_party(cite):
        return None, None
    fulls: list[IndexedCase] = []
    partials: list[IndexedCase] = []
    nearest: Optional[IndexedCase] = None
    nearest_score = -1.0
    for case in idx.all_cases:
        m, pl_score, df_score = names.evaluate(cite, case.raw)
        if m == "full":
            fulls.append(case)
        elif m == "partial":
            if names.court_consistent(cite.court, case.court):
                partials.append(case)
        if m != "full":
            s = max([x for x in (pl_score, df_score) if x is not None] or [0.0])
            if s > nearest_score:
                nearest, nearest_score = case, s

    def rank(c: IndexedCase):
        return (-(c.span), c.first_page if c.first_page is not None else 10**9)

    hit = None
    if fulls:
        hit = (sorted(fulls, key=rank)[0], "full")
    elif partials:
        hit = (sorted(partials, key=rank)[0], "partial")
    nearest_hit = _name_hit(nearest, "none", cite, volume, reporter) if nearest is not None and hit is None else None
    return hit, nearest_hit


# --------------------------------------------------------------------------- #
# §3 volume beyond coverage
# --------------------------------------------------------------------------- #


def _beyond_coverage(
    cite: CitationInput, ctx: RuleContext, reporter: str, volume: int, vmax: int, notes: list[str], *, row: int, cite_text: Optional[str]
) -> CitationResult:
    meta = ctx.reporter
    evidence = Evidence(volume_range=_volume_range(ctx, reporter, volume, held=False))
    closed = meta is not None and meta.edition_end is not None
    ceiling_applies = (closed or not SERIES_CEILING_REQUIRES_CLOSED) and vmax == SERIES_CEILING and volume >= 1000
    if ceiling_applies:
        end = (meta.edition_end_date or str(meta.edition_end)) if meta else "?"
        reasons = [
            f"{reporter} ended at volume {SERIES_CEILING}; volume {volume} cannot exist.",
            f"reporters_db closes the {reporter} edition on {end}; the free corpus holds volumes to {SERIES_CEILING}. West restarted numbering at 1000 in the next series.",
        ]
        return _result(cite, ctx, "likely_fabricated", reasons + notes, row=row, cite_text=cite_text, evidence=evidence, source="CAP")

    cap_end = cap_end_year(ctx)
    reasons = [f"{_display(reporter)} volumes after {vmax} are not in the Caselaw Access Project."]
    if cap_end:
        reasons.append(f"The free corpus ends {cap_end} for {reporter}; check CourtListener or Westlaw.")
    else:
        reasons.append("Check CourtListener or Westlaw.")
    plaus = _plausibility(ctx, reporter, volume, vmax, cap_end)
    if plaus:
        evidence.plausibility = " ".join(plaus)
        reasons.extend(plaus)
    if ctx.courtlistener_status == 200:
        reasons = [f"Confirmed by CourtListener: {_vrp(volume, reporter, cite.page)}; opinion text not fetched."] + reasons[1:]
        return _result(cite, ctx, "verified", reasons + notes, row=row, cite_text=cite_text, evidence=evidence, source="CourtListener")
    return _result(cite, ctx, "not_in_free_corpus", reasons + notes, row=row, cite_text=cite_text, evidence=evidence, source="CAP")


def _plausibility(ctx: RuleContext, reporter: str, volume: int, vmax: int, cap_end: Optional[int]) -> list[str]:
    """§3.2 notes (evidence only). Never raises on 0/None years."""
    out: list[str] = []
    meta = ctx.reporter
    if cap_end:
        rate = 0.0
        for rows in (ctx.volumes or {}).values():
            if any(r.get("start_year") == cap_end or r.get("end_year") == cap_end for r in rows):
                rate += 1
        if rate == 0 and meta and meta.edition_start and cap_end > meta.edition_start:
            rate = vmax / (cap_end - meta.edition_start)
        if rate > 0:
            bound = vmax + (ctx.today_year - cap_end + 2) * rate * 3
            if volume > bound:
                out.append(
                    f"Volume {volume} is improbable: {reporter} reached {vmax} by {cap_end}; about {rate:g} volumes were labelled {cap_end}; "
                    f"even at three times that pace the series would be near {int(bound)} today."
                )
    if volume >= 1000 and meta and meta.successor:
        out.append(
            f"Volume {volume} is above {SERIES_CEILING}, the last volume of the West series held by the free corpus for F.2d, F. Supp. and F. Supp. 2d; "
            f"reporters_db lists {meta.successor} from {meta.successor_start or '?'}."
        )
    return out


# --------------------------------------------------------------------------- #
# Step 9 — quote check (applied by the orchestrator after quotes.py runs)
# --------------------------------------------------------------------------- #


def apply_quote_check(
    result: CitationResult,
    quote_check: Optional[QuoteCheck | dict],
    closest_passage: Optional[ClosestPassage | dict] = None,
) -> CitationResult:
    """Fold a ``quotes.check_quote`` result into a row (DECISION-RULE §4.4). Returns a new row.

    Only a ``verified`` row can change: ``verbatim`` keeps it, ``differs`` / ``not_found``
    make it ``quote_not_found`` with the §4.4 sentence first and the lookup sentence kept
    after it. Other classes get ``quote_check.status = "not_checked"`` (no text was compared).
    """
    if quote_check is None:
        return result.model_copy(deep=True)
    qc = quote_check if isinstance(quote_check, QuoteCheck) else QuoteCheck.model_validate(quote_check)
    cp = None
    if closest_passage is not None:
        cp = closest_passage if isinstance(closest_passage, ClosestPassage) else ClosestPassage.model_validate(closest_passage)
    data = result.model_dump(by_alias=False, exclude={"label", "mark", "register_", "drawer"})
    evidence = result.evidence.model_copy(deep=True)
    if cp is not None:
        evidence.closest_passage = cp
    if result.class_ != "verified" or qc.status == "not_checked":
        data["quote_check"] = qc if result.class_ == "verified" else QuoteCheck(status="not_checked", quote=qc.quote)
        data["evidence"] = evidence
        data["class_"] = result.class_
        return CitationResult.model_validate(data)
    reasons = list(result.reasons)
    if qc.status == "verbatim":
        note = "Quoted passage found in the opinion text"
        if qc.segments > 1:
            note += " with an omission marked by ellipsis"
        reasons.append(note + ".")
        class_ = "verified"
    elif qc.status == "differs":
        n = len(qc.diff) if qc.diff else 1
        pairs = "; ".join(f"'{d.filed}' → '{d.opinion}'" for d in qc.diff)
        lead = f"The quoted passage differs from the opinion text in {n} word(s)"
        lead += f": {pairs}." if pairs else "."
        reasons = [lead + " The opinion's passage is shown."] + reasons
        class_ = "quote_not_found"
    else:
        sim = f"{qc.similarity:.1f}" if qc.similarity is not None else "?"
        reasons = [f"The quoted passage was not found in the opinion text; the closest passage is {sim}% similar and is shown."] + reasons
        class_ = "quote_not_found"
    data["class_"] = class_
    data["reasons"] = reasons
    data["quote_check"] = qc
    data["evidence"] = evidence
    return CitationResult.model_validate(data)


# --------------------------------------------------------------------------- #
# Step 10 — parallel citations of a group whose primary verified
# --------------------------------------------------------------------------- #

_PARALLEL = re.compile(r"^\s*(\d+)\s+(.+?)\s+(\d+)\s*$")


def apply_parallel_cites(result: CitationResult, other_cites: list[str]) -> CitationResult:
    """Step 10 for a ``verified`` primary: compare each other member's ``V R P`` with the CAP record.

    Exact match -> ``"116 S. Ct. 629 — confirmed by the CAP record"``; same reporter at another
    volume/page -> a reason note and ``evidence.parallel_mismatch`` (class unchanged); reporter not
    in the record -> ``"... — not listed in the CAP record; not checked"``. Returns a new row.
    """
    data = result.model_dump(by_alias=False, exclude={"label", "mark", "register_", "drawer"})
    evidence = result.evidence.model_copy(deep=True)
    rc = result.evidence.real_case_at_page
    record = list(rc.parallel_cites) + [rc.cite] if rc is not None else []
    record_keys = {_cite_key(c): c for c in record}
    entries: list[str] = list(result.parallel_cites)
    reasons = list(result.reasons)
    mismatches: list[str] = []
    for other in other_cites:
        key = _cite_key(other)
        if key in record_keys:
            entries.append(f"{other} — confirmed by the CAP record")
            continue
        m = _PARALLEL.match(other)
        same_reporter = None
        if m:
            rep = _cite_key(m.group(2))
            for rk, rv in record_keys.items():
                rm = _PARALLEL.match(rv)
                if rm and _cite_key(rm.group(2)) == rep:
                    same_reporter = rv
                    break
        if same_reporter:
            reasons.append(f"The filing's parallel cite {other} differs from the record's {same_reporter}.")
            mismatches.append(f"{other} ≠ {same_reporter}")
            entries.append(f"{other} — differs from the CAP record's {same_reporter}")
        else:
            entries.append(f"{other} — not listed in the CAP record; not checked")
    if mismatches:
        evidence.parallel_mismatch = "; ".join(mismatches)
    data["parallel_cites"] = entries
    data["reasons"] = reasons
    data["evidence"] = evidence
    return CitationResult.model_validate(data)


__all__ = [
    "CLASS_ORDER",
    "IndexedCase",
    "ReporterMeta",
    "RuleContext",
    "SERIES_CEILING",
    "SERIES_CEILING_REQUIRES_CLOSED",
    "VolumeIndex",
    "apply_parallel_cites",
    "apply_quote_check",
    "best_class",
    "cap_end_year",
    "classify",
    "decision_year",
    "index_volume",
    "label_for_result",
    "reporter_meta",
]
