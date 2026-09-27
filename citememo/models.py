"""Data contracts for the citation memo.

Every module in ``citememo`` and every byte the HTTP API returns is one of the
pydantic v2 models below. Field names are the JSON keys, with one exception:
``CitationResult.class_`` serialises as ``"class"`` (a Python keyword). Call
``model_dump(by_alias=True)`` (or ``model_dump_json(by_alias=True)``) when you
hand a model to the wire; ``populate_by_name`` is on, so both ``class`` and
``class_`` are accepted on input.

Sources for wording: docs/DECISION-RULE.md §6.3 (the ``reasons[]`` sentences,
observations never verdicts) and docs/UI-SPEC.md §9 (the plain-word ``label``
printed on the memo row). The word "fabricated" appears on screen only inside
the label "Likely not a real case" / the class key ``likely_fabricated``.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

# --------------------------------------------------------------------------- #
# Enumerations (Literal types so they serialise as plain strings)
# --------------------------------------------------------------------------- #

CitationClass = Literal[
    "verified",
    "quote_not_found",
    "wrong_cite_exists",
    "not_in_free_corpus",
    "unrecognized_reporter",
    "likely_fabricated",
    "not_checked",
    "skipped",
]
"""The eight classes of DECISION-RULE §0. ``not_checked`` is the failure class
(timeout, server error, run limit); it is never counted in the red or coverage
registers."""

CitationKind = Literal["full", "id", "supra", "short", "statute", "unrecognized"]
"""What eyecite (or the unrecognized-reporter regex) found: a full case
citation, an Id./supra/short form, a statute/regulation/journal cite, or a
citation-like string with a reporter nobody knows."""

Source = Literal["CAP", "CourtListener", "none"]
"""Which corpus answered for this row. ``none`` for rows decided without a
lookup (WL/LEXIS, unrecognized reporter, skipped)."""

Mark = Literal[
    "circle-all",
    "circle-reporter",
    "strike-correct",
    "underline-quote",
    "underline-pencil",
    "check",
    "none",
]
"""The pen mark the memo draws beside the row (UI-SPEC C-02). Derived from the
class; sent so the front end never re-derives the rule."""

Register = Literal["green", "amber", "coverage", "unknown_reporter", "red", "grey"]
"""The memo register of DECISION-RULE §0 (colour family + weight)."""

QuoteStatus = Literal["verbatim", "differs", "not_found", "not_checked"]
"""DECISION-RULE §4.4. ``not_checked``: no quote attached, or the case is not
verified so no text was compared."""

Drawer = Literal["page", "shelf"]
"""Which evidence drawer the row's bracket link opens: the reporter page (a
case sits at or around the page) or the shelf (where the free library's volumes
stop). ``None`` means no link: the reason sentence already says why."""

AdvisoryVerdict = Literal["supports", "does_not_support", "cannot_tell"]

ErrorCode = Literal[
    "no_text_layer",
    "too_large",
    "unsupported_type",
    "upstream_timeout",
    "empty",
    "not_found",
    "rate_limited",
    "internal",
]

CLASSES: tuple[str, ...] = (
    "verified",
    "quote_not_found",
    "wrong_cite_exists",
    "not_in_free_corpus",
    "unrecognized_reporter",
    "likely_fabricated",
    "not_checked",
    "skipped",
)

# UI-SPEC §9 row labels (first line of the margin note). Never edit the words
# without editing UI-SPEC §9; the QA greps the page for them.
LABELS: dict[str, str] = {
    "verified": "Found.",
    "quote_not_found": "Found, but this quote is not in the opinion.",
    "wrong_cite_exists": "Exists, but not at this page.",
    "not_in_free_corpus": "Not in the free library. Check Westlaw or Lexis.",
    "unrecognized_reporter": "No reporter by this name.",
    "likely_fabricated": "Likely not a real case.",
    "not_checked": "Could not reach the free library.",
    "skipped": "Not checked (Id., supra or short form).",
}
LABEL_SKIPPED_STATUTE = "Not checked (statute)."
LABEL_FOUND_QUOTE = "Found. Quote matches."
LABEL_PIN_SUFFIX = " Pin page not checked."

MARKS: dict[str, str] = {
    "verified": "check",
    "quote_not_found": "underline-quote",
    "wrong_cite_exists": "strike-correct",
    "not_in_free_corpus": "underline-pencil",
    "unrecognized_reporter": "circle-reporter",
    "likely_fabricated": "circle-all",
    "not_checked": "none",
    "skipped": "none",
}

REGISTERS: dict[str, str] = {
    "verified": "green",
    "quote_not_found": "amber",
    "wrong_cite_exists": "amber",
    "not_in_free_corpus": "coverage",
    "not_checked": "coverage",
    "unrecognized_reporter": "unknown_reporter",
    "likely_fabricated": "red",
    "skipped": "grey",
}

# Class keys as the Evaluation tab prints them (UI-SPEC §5 S5).
CLASS_KEY_LEGEND: dict[str, str] = {
    "likely_fabricated": "Likely not a real case",
    "not_in_free_corpus": "Not in the free library",
    "wrong_cite_exists": "Exists, but not at this page",
    "quote_not_found": "Found, but this quote is not in the opinion",
    "unrecognized_reporter": "No reporter by this name",
    "verified": "Found",
    "not_checked": "Could not reach the free library",
    "skipped": "Not checked",
}


def label_for(
    class_: str,
    *,
    has_quote: bool = False,
    pincite_unverified: bool = False,
    kind: str = "full",
) -> str:
    """The UI-SPEC §9 label for a class, with the verified/skipped variants."""
    if class_ == "verified":
        text = LABEL_FOUND_QUOTE if has_quote else LABELS["verified"]
        return text + LABEL_PIN_SUFFIX if pincite_unverified else text
    if class_ == "skipped" and kind == "statute":
        return LABEL_SKIPPED_STATUTE
    return LABELS[class_]


def now_iso() -> str:
    """UTC timestamp, second precision, with offset (``2026-09-26T14:03:11+00:00``)."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class _Model(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")


# --------------------------------------------------------------------------- #
# Input side: one citation as extracted from the filing
# --------------------------------------------------------------------------- #


class CitationInput(_Model):
    """One citation as ``extract.py`` found it in the filing text.

    ``text`` and ``span`` cover the core cite eyecite matched (``925 F.3d 1339``)
    in the cleaned text; the party names and year are separate fields. The
    memo row's full ``cite_text`` (parties + cite + parenthetical) lives on
    ``CitationResult``.
    """

    text: str = Field(description="The matched text of the core cite, e.g. '925 F.3d 1339'.")
    span: Optional[tuple[int, int]] = Field(
        default=None, description="[start, end) character offsets in the cleaned filing text."
    )
    filing_page: Optional[int] = Field(default=None, ge=1, description="1-based PDF page the span starts on.")
    volume: Optional[int] = None
    reporter: Optional[str] = Field(
        default=None,
        description="Canonical reporter string (eyecite edition_guess.short_name), e.g. 'F. Supp. 2d'; the raw string for unrecognized reporters.",
    )
    page: Optional[int] = None
    pin_cite: Optional[str] = Field(default=None, description="e.g. 'at 230' or '1340-41'; note only, never verified.")
    year: Optional[int] = Field(default=None, description="Year from the parenthetical regex, falling back to eyecite metadata.year.")
    court: Optional[str] = Field(default=None, description="eyecite court id ('scotus', 'ca2') or the parenthetical's court text.")
    plaintiff: Optional[str] = None
    defendant: Optional[str] = None
    quotes: list[str] = Field(default_factory=list, description="Quoted passages (>= 25 chars) attached to this citation.")
    kind: CitationKind = "full"


# --------------------------------------------------------------------------- #
# Evidence
# --------------------------------------------------------------------------- #


class RealCase(_Model):
    """A case record from CAP ``CasesMetadata.json``, reduced to what a row shows."""

    name: str = Field(description="CAP name_abbreviation, e.g. 'J.D. v. Azar'.")
    first_page: int
    last_page: int
    decision_date: str = Field(description="ISO date as CAP gives it, e.g. '2019-06-14'.")
    court: str = Field(description="CAP court.name, e.g. 'Court of Appeals of the District of Columbia'.")
    court_abbreviation: Optional[str] = Field(default=None, description="CAP court.name_abbreviation, e.g. 'D.C. Cir.'.")
    cite: str = Field(description="Official cite, e.g. '925 F.3d 1291'.")
    file_name: Optional[str] = Field(default=None, description="CAP case file stem, e.g. '1291-01'.")
    id: Optional[int] = Field(default=None, description="CAP case id.")
    parallel_cites: list[str] = Field(default_factory=list, description="Other cites the CAP record lists.")


class NameHit(RealCase):
    """A case found by name search across the volume (DECISION-RULE step 7)."""

    score: float = Field(description="Best fuzzy score (0-100) of the filed party names against this caption.")
    match: Literal["full", "partial", "none"] = "none"
    court_consistent: Optional[bool] = Field(default=None, description="§5.4 circuit check; None when either side has no court.")


class VolumeRange(_Model):
    """What the free library holds for this reporter (the shelf)."""

    reporter: str
    vmin: int = Field(description="Lowest volume number CAP lists.")
    vmax: int = Field(description="Highest volume number CAP lists.")
    held: bool = Field(description="True when the cited volume is present in CAP.")
    cited: Optional[int] = Field(default=None, description="The cited volume.")
    cap_end_year: Optional[int] = Field(default=None, description="Last year CAP covers for this reporter.")
    max_last_page: Optional[int] = Field(default=None, description="Last page of the last case CAP holds in the cited volume.")
    note: Optional[str] = Field(default=None, description="Shelf label, e.g. 'U.S. Reports · volumes 1–572 in the free library · cited: 600'.")


class EditionRange(_Model):
    """reporters_db / CAP edition years (DECISION-RULE step 3; a note, never a class)."""

    reporter: str
    start: Optional[int] = None
    end: Optional[int] = Field(default=None, description="None = the edition is open in reporters_db.")
    note: Optional[str] = None


class DiffToken(_Model):
    """One differing word (or run of words): what the filing says vs what the opinion says."""

    filed: str
    opinion: str


class ClosestPassage(_Model):
    """The best-matching window of the opinion text for a quoted passage (DECISION-RULE §4)."""

    text: str = Field(description="Raw opinion text around the aligned window (about ±200 chars).")
    similarity: float = Field(ge=0, le=100, description="rapidfuzz partial_ratio (min over segments), 0-100.")
    diff_tokens: list[DiffToken] = Field(default_factory=list)
    status: QuoteStatus = "not_checked"
    highlight: Optional[tuple[int, int]] = Field(default=None, description="[start, end) offsets inside `text` of the opinion's passage.")


class YearMismatch(_Model):
    cited: int
    decided: str


class Evidence(_Model):
    """Everything a row can show under itself. All fields optional; the UI reads what is there.

    Per-row evidence (``running_head``, ``excerpt``, ``links``) is EMBEDDED here so the
    front end needs no ``/api/evidence/{row}`` call (see docs/API.md, deviation from
    UI-SPEC §6 C-04). Extra keys are allowed so ``rules.py`` can attach diagnostics
    (``searched_names``, ``plausibility`` …) without a schema change.
    """

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    real_case_at_page: Optional[RealCase] = Field(default=None, description="The case that begins at, or spans, the cited page.")
    name_hit: Optional[NameHit] = Field(default=None, description="Step-7 name search result, when one was found.")
    other_entries: list[RealCase] = Field(default_factory=list, description="Other CAP entries for the same case (orders pages, duplicates).")
    volume_range: Optional[VolumeRange] = None
    edition_range: Optional[EditionRange] = None
    closest_passage: Optional[ClosestPassage] = None
    running_head: Optional[str] = Field(
        default=None,
        description="Reporter running head for the drawer, e.g. '925 F.3d 1291 · J.D. v. AZAR · D.C. Cir. · June 14, 2019'.",
    )
    page_marker: Optional[str] = Field(default=None, description="The cited page as the drawer prints it at the right, e.g. '1339'.")
    excerpt: Optional[str] = Field(
        default=None,
        description="About 200 chars of opinion text around the closest passage (quote rows) or the case's start (other rows). None when the case text is not in the cache and could not be fetched.",
    )
    excerpt_highlight: Optional[tuple[int, int]] = Field(default=None, description="[start, end) inside `excerpt` to underline.")
    links: list[str] = Field(default_factory=list, description="CAP static URLs used for this row, in fetch order.")
    cite_type: Optional[str] = Field(default=None, description="reporters_db cite_type for step-2 rows ('specialty_west', 'neutral').")
    matched_text: Optional[str] = Field(default=None, description="The regex match for unrecognized_reporter rows.")
    searched_names: list[str] = Field(default_factory=list, description="Party names searched across the volume in step 7.")
    nearest_caption: Optional[NameHit] = Field(default=None, description="Best-scoring caption when no hit carried a match.")
    year_mismatch: Optional[YearMismatch] = None
    plausibility: Optional[str] = Field(default=None, description="DECISION-RULE §3.2 note for volumes beyond coverage.")
    parallel_mismatch: Optional[str] = None


# --------------------------------------------------------------------------- #
# Result side
# --------------------------------------------------------------------------- #


class QuoteCheck(_Model):
    """Summary of the quote comparison (DECISION-RULE §4.4); the text lives in ``evidence.closest_passage``."""

    status: QuoteStatus
    quote: Optional[str] = Field(default=None, description="The quoted passage as filed.")
    similarity: Optional[float] = Field(default=None, ge=0, le=100)
    segments: int = Field(default=1, ge=0, description="Ellipsis-separated segments compared.")
    diff: list[DiffToken] = Field(default_factory=list)


class Advisory(_Model):
    """Optional LLM support check. Labelled ADVISORY everywhere; never changes the class."""

    verdict: AdvisoryVerdict
    why: str
    model: str


class CitationResult(_Model):
    """One memo row."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid", serialize_by_alias=True)

    row: int = Field(ge=1, description="1-based line number in filing order; the UI's `#line-{row}`.")
    cite_text: str = Field(description="The citation as printed on the memo, e.g. 'Varghese v. China Southern Airlines Co., 925 F.3d 1339 (11th Cir. 2019)'.")
    class_: CitationClass = Field(alias="class")
    label: str = Field(default="", description="UI-SPEC §9 label; filled from the class when empty.")
    reasons: list[str] = Field(default_factory=list, description="Plain sentences; reasons[0] is printed under the row.")
    evidence: Evidence = Field(default_factory=Evidence)
    source: Source = "none"
    pincite_unverified: bool = False
    quote_check: Optional[QuoteCheck] = None
    parallel_cites: list[str] = Field(default_factory=list, description="e.g. '116 S. Ct. 629 — confirmed by the CAP record'.")
    advisory: Optional[Advisory] = None
    timings_ms: dict[str, float] = Field(default_factory=dict, description="Per-row stage timings, e.g. {'lookup': 12.4, 'quotes': 2.1}.")
    citation: Optional[CitationInput] = Field(default=None, description="The extracted input (span, filing page, parties, quotes).")
    mark: Mark = Field(default="none", description="Derived from the class unless given.")
    register_: Register = Field(default="grey", alias="register", description="Derived from the class unless given (DECISION-RULE §0 register).")
    drawer: Optional[Drawer] = Field(default=None, description="Which evidence drawer the row's link opens; None = no link.")

    @model_validator(mode="after")
    def _derive(self) -> "CitationResult":
        fields_set = self.model_fields_set
        if not self.label:
            kind = self.citation.kind if self.citation else "full"
            has_quote = bool(self.citation and self.citation.quotes) or bool(
                self.quote_check and self.quote_check.status == "verbatim"
            )
            self.label = label_for(self.class_, has_quote=has_quote, pincite_unverified=self.pincite_unverified, kind=kind)
        if "mark" not in fields_set:
            self.mark = MARKS[self.class_]  # type: ignore[assignment]
        if "register_" not in fields_set:
            self.register_ = REGISTERS[self.class_]  # type: ignore[assignment]
        if "drawer" not in fields_set:
            ev = self.evidence
            if self.class_ in ("skipped", "not_checked", "unrecognized_reporter"):
                self.drawer = None
            elif ev.real_case_at_page is not None or ev.name_hit is not None:
                self.drawer = "page"
            elif ev.volume_range is not None:
                self.drawer = "shelf"
            else:
                self.drawer = None
        return self


class Counts(_Model):
    """Rows per class plus the total."""

    verified: int = 0
    quote_not_found: int = 0
    wrong_cite_exists: int = 0
    not_in_free_corpus: int = 0
    unrecognized_reporter: int = 0
    likely_fabricated: int = 0
    not_checked: int = 0
    skipped: int = 0
    total: int = 0

    @classmethod
    def from_results(cls, results: list[CitationResult]) -> "Counts":
        c = cls()
        for r in results:
            setattr(c, r.class_, getattr(c, r.class_) + 1)
        c.total = len(results)
        return c


def _n(n: int, singular: str, plural: str) -> str:
    return f"{n} {singular if n == 1 else plural}"


def read_these_first_sentence(c: Counts) -> str:
    """UI-SPEC §9 foot paragraph. Zero counts are omitted ("{f} found" always stays); the UI links each count."""
    flagged = []
    if c.likely_fabricated:
        flagged.append(_n(c.likely_fabricated, "likely not real case", "likely not real cases"))
    if c.unrecognized_reporter:
        flagged.append(f"{c.unrecognized_reporter} no reporter by this name")
    if c.quote_not_found:
        flagged.append(_n(c.quote_not_found, "quote not in the opinion", "quotes not in the opinion"))
    if c.wrong_cite_exists:
        flagged.append(f"{c.wrong_cite_exists} exists at another page")
    rest = [f"{c.verified} found"]
    if c.not_in_free_corpus:
        rest.append(f"{c.not_in_free_corpus} not in the free library")
    if c.skipped:
        rest.append(f"{c.skipped} not checked")
    tail = "; ".join(rest) + f". Of {_n(c.total, 'citation', 'citations')}."
    if c.not_checked:
        tail += f" {c.not_checked} not answered yet."
    if flagged:
        return "Read these first: " + ", ".join(flagged) + ". Then: " + tail
    return "Nothing to read first: " + tail


class Filing(_Model):
    filename: str
    pages: int = Field(ge=0)
    words: int = Field(ge=0)
    label: Optional[str] = Field(default=None, description="Typed into RE:. For samples, the synthetic label; for uploads, None.")
    bytes: Optional[int] = Field(default=None, ge=0)


class SourcesUsed(_Model):
    cap: bool = True
    courtlistener: bool = False
    advisory: bool = False


class StageTimings(_Model):
    """Milliseconds per pipeline stage. ``advisory`` is None when not run."""

    extract: float = 0.0
    lookup: float = 0.0
    classify: float = 0.0
    quotes: float = 0.0
    advisory: Optional[float] = None


class Memo(_Model):
    """The whole response of POST /api/memo (and of the sample, replay and fixture routes)."""

    run_id: str
    created_at: str = Field(default_factory=now_iso, description="ISO 8601 with offset; the stamp's date and time.")
    app_version: str = Field(default="0.1.0")
    filing: Filing
    sources_used: SourcesUsed = Field(default_factory=SourcesUsed)
    results: list[CitationResult] = Field(default_factory=list)
    counts: Counts = Field(default_factory=Counts, description="Filled from results when omitted.")
    read_these_first: str = Field(default="", description="UI-SPEC §9 tally sentence; filled from counts when empty.")
    elapsed_ms: float = 0.0
    stage_timings_ms: StageTimings = Field(default_factory=StageTimings)
    offline: bool = Field(default=False, description="True when answers came from the on-disk CAP cache only.")
    replay: bool = Field(default=False, description="True for seed/replay.json and for the front-end fixture.")
    fixture: bool = Field(default=False, description="True only for web/static/fixture-memo.json (hand-built from the seed, not a recorded run).")
    sample_id: Optional[str] = None
    warnings: list[str] = Field(default_factory=list, description="Run-level notices, e.g. 'CourtListener throttled this run; the Caselaw Access Project answered for every row shown.'")
    notes: list[str] = Field(default_factory=list, description="Provenance notes (where a fixture's numbers came from).")

    @model_validator(mode="after")
    def _fill(self) -> "Memo":
        if "counts" not in self.model_fields_set or self.counts.total == 0 and self.results:
            self.counts = Counts.from_results(self.results)
        if not self.read_these_first:
            self.read_these_first = read_these_first_sentence(self.counts)
        return self

    @property
    def flagged(self) -> int:
        """Rows needing a first look: the four red-marked classes."""
        c = self.counts
        return c.likely_fabricated + c.unrecognized_reporter + c.quote_not_found + c.wrong_cite_exists


# --------------------------------------------------------------------------- #
# Samples, evaluation, health, errors
# --------------------------------------------------------------------------- #


class SampleInfo(_Model):
    id: str = Field(description="Route key: POST /api/memo/sample/{id}.")
    title: str
    label: str = Field(description="The synthetic label printed on the content and typed into RE:.")
    filename: str
    pages: int
    words: Optional[int] = None
    citations: int = Field(description="Rows the memo will show (scored + label + skipped).")
    scored: int = Field(description="Rows with a ground-truth class (20 for the seed).")
    synthetic: bool = True
    cached: bool = Field(default=True, description="Every CAP file the sample needs is in seed/cache, so it runs offline.")


class EvalRow(_Model):
    id: str = Field(description="ground_truth item id, e.g. 'mata-varghese'.")
    line: Optional[int] = Field(default=None, description="Memo row this item matched (by cite_text), or None if the memo lacked it.")
    cite_text: str
    expected: CitationClass
    accepted: list[CitationClass]
    predicted: Optional[CitationClass] = None
    ok: bool = False
    reason: Optional[str] = Field(default=None, description="The memo's reasons[0] for this row.")
    real_case: bool = Field(default=False, description="True when ground truth has a real case beginning at the cited page.")


class EvalReport(_Model):
    rows: list[EvalRow]
    correct: int
    total: int
    accuracy: float = Field(ge=0, le=1, description="correct / total.")
    real_cases_marked_fabricated: int = Field(description="Real cases (real_case=True) predicted likely_fabricated. Target 0.")
    real_total: int = Field(description="How many rows are real cases.")
    per_class: dict[str, dict[str, int]] = Field(
        default_factory=dict, description="{'expected': {class: n}, 'predicted': {class: n}}."
    )
    elapsed_ms: float
    stage_timings_ms: StageTimings = Field(default_factory=StageTimings)
    generated_at: str = Field(default_factory=now_iso)
    run_id: Optional[str] = None
    run_created_at: Optional[str] = None
    offline: bool = False
    replay: bool = False


class Health(_Model):
    ok: bool = True
    version: str = "0.1.0"
    offline: bool = False
    courtlistener: bool = False
    advisory: bool = False
    replay_available: bool = False
    cache_dir: Optional[str] = None


class ErrorBody(_Model):
    code: ErrorCode
    message: str = Field(description="One plain sentence for the user (UI-SPEC §9 errors).")
    hint: Optional[str] = Field(default=None, description="What to do next, e.g. 'Try a PDF saved from a word processor, or the sample filing.'")


class ErrorEnvelope(_Model):
    """Every non-2xx JSON body: ``{"error": {"code", "message", "hint"}}``."""

    error: ErrorBody


__all__ = [
    "Advisory",
    "AdvisoryVerdict",
    "CLASSES",
    "CLASS_KEY_LEGEND",
    "CitationClass",
    "CitationInput",
    "CitationKind",
    "CitationResult",
    "ClosestPassage",
    "Counts",
    "DiffToken",
    "Drawer",
    "EditionRange",
    "ErrorBody",
    "ErrorCode",
    "ErrorEnvelope",
    "EvalReport",
    "EvalRow",
    "Evidence",
    "Filing",
    "Health",
    "LABELS",
    "MARKS",
    "Mark",
    "Memo",
    "NameHit",
    "QuoteCheck",
    "QuoteStatus",
    "REGISTERS",
    "RealCase",
    "Register",
    "SampleInfo",
    "Source",
    "SourcesUsed",
    "StageTimings",
    "VolumeRange",
    "YearMismatch",
    "label_for",
    "now_iso",
    "read_these_first_sentence",
]
