"""The orchestrator: one filing in, one :class:`~citememo.models.Memo` out (T05, BUILD-NOTES §2).

Pipeline (DECISION-RULE §1.6 → §2 → §4 → §6; every stage is timed):

1. **extract** — ``pdf_to_text`` (or the pasted text) → ``extract_citations`` (eyecite +
   the unrecognized-reporter catch). ``NoTextLayer`` / ``UnreadablePdf`` propagate to
   the API layer, which maps them to the error envelope. Limits (ADR-0005,
   ``citememo/limits.py``): text beyond 200,000 characters is not read and citations
   beyond the 250th full one are dropped; each cut adds a "Truncated:" line to
   ``memo.warnings`` (``Memo`` has no ``truncated`` field). ``filing.pages``/``words``
   describe the whole input.
2. **group** — consecutive full cites ≤ 3 chars apart with the same parties and year
   form one row (parallel cites, §1.6 item 3); the run limit (``MAX_VOLUMES`` distinct
   ``(slug, volume)`` pairs) marks later volumes ``not_checked``.
3. **lookup** — ``CapClient.fetch_volumes_batch`` fetches every volume's
   ``CasesMetadata`` with at most 6 requests in flight. A volume that *fails*
   (timeout, 5xx, offline miss) degrades only its own rows (``not_checked``, label
   "Could not reach the free library."); an *absent* volume is coverage.
4. **classify** — ``rules.classify`` on a :class:`~citememo.rules.RuleContext` per
   volume (memoised so two cites in one volume share the index). Classification
   stays in ``rules.py``; this module only builds contexts.
5. **quotes** — for ``verified`` rows with a quoted passage, the case JSON is
   fetched (≤ 6 concurrent) and ``quotes.check_quote`` runs; ``rules.apply_quote_check``
   folds it in. Evidence (``running_head``, ``page_marker``, ``excerpt``, ``links``)
   is filled for every row that names a case.
6. **CourtListener** (optional, token) — beyond-coverage rows are re-checked; a 200
   upgrades the row to ``verified`` with source ``CourtListener`` (rules step 4).
7. **advisory** (optional, key) — ``advisory.run_advisory``; never changes a class.

Public surface
--------------
``run_memo(*, text=None, pdf_bytes=None, filename, label=None, sample_id=None,
          cap=None, courtlistener=None, advisory_client=None, run_id=None) -> Memo``
``run_sample(sample_id, *, cap=None, courtlistener=None, advisory_client=None) -> Memo``
``load_samples() -> list[SampleInfo]`` and ``sample_path(sample_id) -> Path``
``KNOWN_SAMPLE_IDS``

One JSON log line per run goes to stdout (run_id, sha256 of the input and of the file
name, n citations, class counts, stage timings, sources, offline). No filing text and no
file name is ever logged: a name like "Doe v. Roe - medical records.pdf" is PII.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from . import advisory as advisory_mod
from . import limits, names, quotes, rules
from .cap import CapClient, CorpusUnavailable
from .courtlistener import CourtListenerClient
from .extract import clean_filing_text, extract_citations, pdf_to_text
from .models import (
    CitationInput,
    CitationResult,
    Filing,
    Memo,
    QuoteCheck,
    RealCase,
    SampleInfo,
    SourcesUsed,
    StageTimings,
    now_iso,
)
from .rules import RuleContext

ROOT = Path(__file__).resolve().parents[1]
SAMPLES_PATH = ROOT / "seed" / "samples.json"

MAX_VOLUMES = 60  # DECISION-RULE §1.6 item 5
CONCURRENCY = 6
PARALLEL_GAP = 3  # characters between two members of a parallel-cite group
EXCERPT_CHARS = 240

RUN_LIMIT_REASON = f"run limit: more than {MAX_VOLUMES} volumes in one filing; run the rest separately"


# --------------------------------------------------------------------------- #
# Samples
# --------------------------------------------------------------------------- #


def _raw_samples() -> list[dict]:
    if not SAMPLES_PATH.exists():
        return []
    return json.loads(SAMPLES_PATH.read_text(encoding="utf-8"))


def load_samples() -> list[SampleInfo]:
    out = []
    for s in _raw_samples():
        out.append(SampleInfo(**{k: v for k, v in s.items() if k in SampleInfo.model_fields}))
    return out


def sample_record(sample_id: str) -> Optional[dict]:
    for s in _raw_samples():
        if s.get("id") == sample_id:
            return s
    return None


def sample_path(sample_id: str) -> Path:
    rec = sample_record(sample_id)
    if rec is None:
        raise KeyError(sample_id)
    return ROOT / rec["file"]


KNOWN_SAMPLE_IDS = [s.get("id") for s in _raw_samples()]


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _ms(t0: float) -> float:
    return round((time.perf_counter() - t0) * 1000, 1)


def _failure_text(exc: CorpusUnavailable) -> str:
    """DECISION-RULE §6.1 wording for a Failed fetch."""
    r = (exc.reason or "").lower()
    if r.startswith("timeout"):
        return "timeout"
    if r == "offline":
        return "offline: not in the cache"
    if r == "non-json":
        return "unreadable reply"
    if r == "connection":
        return "connection error"
    return "server error"


def _long_date(iso: Optional[str]) -> str:
    if not iso:
        return ""
    try:
        d = datetime.strptime(iso[:10], "%Y-%m-%d")
        return f"{d:%B} {d.day}, {d.year}"
    except ValueError:
        return iso


def _caption_upper(name: str) -> str:
    return re.sub(r"\s+V\.\s+", " v. ", name.upper())


def running_head_for(rc: RealCase, page: Optional[int]) -> str:
    parts = [rc.cite, _caption_upper(rc.name)]
    court = rc.court_abbreviation or rc.court
    if court:
        parts.append(court)
    date = _long_date(rc.decision_date)
    if date:
        parts.append(date)
    head = " · ".join(p for p in parts if p)
    if page is not None and page != rc.first_page:
        head += f" · begins at {rc.first_page}"
    return head


def _excerpt_from_start(opinion: str) -> Optional[str]:
    text = opinion.lstrip()
    if not text:
        return None
    return text[:EXCERPT_CHARS]


def _same_group(a: Any, b: Any) -> bool:
    """§1.6 item 3: adjacent, same normalized parties, same year."""
    if a.kind != "full" or b.kind != "full" or not a.span or not b.span:
        return False
    if getattr(a, "history", None) or getattr(b, "history", None):
        return False
    if b.span[0] - a.span[1] > PARALLEL_GAP or b.span[0] < a.span[1]:
        return False
    if (a.year or b.year) and a.year != b.year and a.year is not None and b.year is not None:
        return False
    if not (a.plaintiff or a.defendant) or not (b.plaintiff or b.defendant):
        return False
    return names.normalize_party(a.plaintiff or "") == names.normalize_party(b.plaintiff or "") and names.normalize_party(
        a.defendant or ""
    ) == names.normalize_party(b.defendant or "")


def _cite_type_rank(cite_type: Optional[str]) -> int:
    return {"federal": 0, "state": 1}.get(cite_type or "", 2)


# --------------------------------------------------------------------------- #
# The run
# --------------------------------------------------------------------------- #


@dataclass
class _VolumeData:
    slug: str
    volume: int
    cases: Optional[list[dict]] = None
    failed: Optional[str] = None  # cases fetch failed
    fetched: bool = False


@dataclass
class _Run:
    cap: CapClient
    text: str
    warnings: list[str] = field(default_factory=list)
    volumes_by_slug: dict[str, Optional[dict[str, list[dict]]]] = field(default_factory=dict)
    volumes_failed: dict[str, str] = field(default_factory=dict)
    volume_data: dict[tuple[str, int], _VolumeData] = field(default_factory=dict)
    ctx_cache: dict[tuple, RuleContext] = field(default_factory=dict)
    today_year: int = field(default_factory=lambda: datetime.now().year)

    # -- reporter / slug ------------------------------------------------- #
    def slug_for(self, cite: Any) -> Optional[str]:
        if cite.kind != "full" or not cite.reporter:
            return None
        return self.cap.reporter_slug(cite.reporter)

    def needs_fetch(self, cite: Any) -> Optional[tuple[str, int]]:
        if getattr(cite, "history", None) or getattr(cite, "slip_op", False):
            return None
        slug = self.slug_for(cite)
        if slug is None or cite.volume is None:
            return None
        meta = rules.reporter_meta(cite.reporter, self.cap.reporter_info(slug))
        if meta is not None and meta.cite_type in ("specialty_west", "specialty_lexis", "neutral"):
            return None
        return (slug, int(cite.volume))

    # -- fetch -------------------------------------------------------------- #
    def fetch(self, pairs: list[tuple[str, int]]) -> None:
        if not pairs:
            return
        results = self.cap.fetch_volumes_batch(pairs)
        for key in pairs:
            slug, vol = key
            res = results.get(key)
            vd = _VolumeData(slug=slug, volume=vol, fetched=True)
            if isinstance(res, CorpusUnavailable):
                if "VolumesMetadata" in (res.url or ""):
                    self.volumes_failed[slug] = _failure_text(res)
                    self.warnings.append(
                        f"The free library did not answer for the {self.cap.reporter_short_name(slug) or slug} volume index ({_failure_text(res)})."
                    )
                else:
                    vd.failed = _failure_text(res)
                    self.warnings.append(
                        f"The free library did not answer for {vol} {self.cap.reporter_short_name(slug) or slug} ({vd.failed})."
                    )
            else:
                vd.cases = res  # list or None (absent)
            self.volume_data[key] = vd
        for slug in dict.fromkeys(s for s, _ in pairs):
            if slug in self.volumes_failed:
                self.volumes_by_slug[slug] = None
                continue
            try:
                vols = self.cap.volumes(slug)
            except CorpusUnavailable as exc:
                self.volumes_failed[slug] = _failure_text(exc)
                self.volumes_by_slug[slug] = None
                continue
            self.volumes_by_slug[slug] = None if vols is None else {str(k): v for k, v in vols.items()}

    # -- contexts ------------------------------------------------------------ #
    def context(self, cite: Any, *, run_limited: bool = False, courtlistener_status: Optional[int] = None) -> RuleContext:
        slug = self.slug_for(cite)
        reporter = cite.reporter if cite.kind == "full" and cite.reporter else None
        meta = rules.reporter_meta(reporter, self.cap.reporter_info(slug) if slug else None) if reporter else None
        volume = int(cite.volume) if cite.volume is not None else None
        key = (slug, volume, run_limited, courtlistener_status, reporter)
        if key in self.ctx_cache:
            return self.ctx_cache[key]
        kwargs: dict[str, Any] = {"slug": slug, "reporter": meta, "today_year": self.today_year, "courtlistener_status": courtlistener_status}
        if run_limited:
            kwargs["not_checked_reason"] = RUN_LIMIT_REASON
        elif slug is not None and volume is not None:
            links = [self.cap.volumes_url(slug)]
            if slug in self.volumes_failed:
                kwargs["volumes_failed"] = self.volumes_failed[slug]
            elif slug in self.volumes_by_slug:
                vols = self.volumes_by_slug[slug]
                kwargs["volumes"] = vols
                vd = self.volume_data.get((slug, volume))
                if vd is not None and vols is not None and str(volume) in vols:
                    links.append(self.cap.cases_url(slug, volume))
                    if vd.failed:
                        kwargs["cases_failed"] = vd.failed
                    else:
                        kwargs["cases"] = vd.cases
            kwargs["links"] = links
        ctx = RuleContext(**kwargs)
        self.ctx_cache[key] = ctx
        return ctx


def _classify_group(run: _Run, members: list[Any], row: int, *, run_limited: bool, cl_status: dict[str, int]) -> CitationResult:
    """§1.6 item 3 / step 10: classify the members, keep the best, note the others."""
    if len(members) == 1:
        m = members[0]
        return rules.classify(m, run.context(m, run_limited=run_limited, courtlistener_status=cl_status.get(m.text)), row=row, cite_text=m.cite_text or None)
    # primary first: a member whose reporter has a CAP slug and a present volume, then federal before state
    def rank(m: Any):
        slug = run.slug_for(m)
        vols = run.volumes_by_slug.get(slug) if slug else None
        present = bool(slug and vols and str(m.volume) in vols)
        return (0 if present else 1, 0 if slug else 1, _cite_type_rank(getattr(m, "cite_type", None)))

    ordered = sorted(members, key=rank)
    results = [
        rules.classify(m, run.context(m, run_limited=run_limited, courtlistener_status=cl_status.get(m.text)), row=row, cite_text=m.cite_text or None)
        for m in ordered
    ]
    best = rules.best_class([r.class_ for r in results])
    idx = next(i for i, r in enumerate(results) if r.class_ == best)
    chosen = results[idx]
    others = [m.text for i, m in enumerate(ordered) if i != idx]
    if chosen.class_ == "verified":
        return rules.apply_parallel_cites(chosen, others)
    data = chosen.model_dump(by_alias=False, exclude={"label", "mark", "register_", "drawer"})
    data["parallel_cites"] = list(chosen.parallel_cites) + [f"{o} — not checked (the primary citation did not verify)" for o in others]
    return CitationResult.model_validate(data)


def _pick_quote_result(checks: list[quotes.QuoteMatch]) -> quotes.QuoteMatch:
    for c in checks:
        if c.status in ("differs", "not_found"):
            return c
    for c in checks:
        if c.status == "verbatim":
            return c
    return checks[0]


def run_memo(
    *,
    text: Optional[str] = None,
    pdf_bytes: Optional[bytes] = None,
    filename: str = "pasted-text",
    label: Optional[str] = None,
    sample_id: Optional[str] = None,
    cap: Optional[CapClient] = None,
    courtlistener: Optional[CourtListenerClient] = None,
    advisory_client: Any = None,
    run_id: Optional[str] = None,
) -> Memo:
    """Run the whole pipeline on a PDF (``pdf_bytes``) or on ``text``; see the module docstring."""
    if pdf_bytes is None and text is None:
        raise ValueError("run_memo needs text or pdf_bytes")
    cap = cap or CapClient()
    run_id = run_id or str(uuid.uuid4())
    t_start = time.perf_counter()
    created_at = now_iso()

    # 1. extract ------------------------------------------------------------ #
    t0 = time.perf_counter()
    if pdf_bytes is not None:
        raw = pdf_to_text(pdf_bytes)
        n_bytes = len(pdf_bytes)
        digest = hashlib.sha256(pdf_bytes).hexdigest()
    else:
        raw = text or ""
        n_bytes = len(raw.encode("utf-8"))
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    pages = raw.count("\f") + 1 if raw else 0
    words = len(raw.split())
    raw, cut_text_note = limits.truncate_text(raw)  # ADR-0005: read at most 200,000 characters
    cleaned, _to_raw = clean_filing_text(raw)
    cites, cut_cites_note = limits.cap_citations(extract_citations(raw))  # at most 250 full citations
    stage_extract = _ms(t0)

    run = _Run(cap=cap, text=cleaned)
    run.warnings.extend(n for n in (cut_text_note, cut_cites_note) if n)

    # 2. group + run limit --------------------------------------------------- #
    groups: list[list[Any]] = []
    for c in cites:
        if groups and _same_group(groups[-1][-1], c):
            groups[-1].append(c)
        else:
            groups.append([c])
    pairs: list[tuple[str, int]] = []
    limited: set[tuple[str, int]] = set()
    for g in groups:
        for m in g:
            key = run.needs_fetch(m)
            if key is None or key in pairs or key in limited:
                continue
            if len(pairs) < MAX_VOLUMES:
                pairs.append(key)
            else:
                limited.add(key)
    if limited:
        run.warnings.append(f"Run limit: {len(limited)} volumes beyond the first {MAX_VOLUMES} were not checked; run the rest separately.")

    # 3. lookup -------------------------------------------------------------- #
    t0 = time.perf_counter()
    run.fetch(pairs)
    stage_lookup = _ms(t0)

    # 4. classify ------------------------------------------------------------ #
    t0 = time.perf_counter()
    results: list[CitationResult] = []
    group_meta: list[dict[str, Any]] = []
    for i, g in enumerate(groups, start=1):
        is_limited = any(run.needs_fetch(m) in limited for m in g)
        tr = time.perf_counter()
        r = _classify_group(run, g, i, run_limited=is_limited, cl_status={})
        r.timings_ms["classify"] = _ms(tr)
        results.append(r)
        group_meta.append({"members": g, "limited": is_limited})
    stage_classify = _ms(t0)

    # 6. CourtListener (optional) — before quotes so an upgraded row is treated like any verified row
    sources_cl = False
    if courtlistener is not None and courtlistener.configured:
        t0 = time.perf_counter()
        beyond: dict[int, str] = {}
        for idx, r in enumerate(results):
            vr = r.evidence.volume_range
            c = r.citation
            if r.class_ == "not_in_free_corpus" and vr is not None and c is not None and c.volume is not None and c.volume > vr.vmax and c.text:
                beyond[idx] = c.text
        if beyond:
            lookups = courtlistener.lookup_citations(list(dict.fromkeys(beyond.values())))
            last = getattr(courtlistener, "last_result", None)
            status = getattr(last, "status", None)
            if status == "ok":
                sources_cl = True
            elif status == "throttled":
                run.warnings.append("CourtListener throttled this run; the Caselaw Access Project answered for every row shown.")
            elif status == "unauthorized":
                run.warnings.append("CourtListener refused the token; the Caselaw Access Project answered for every row shown.")
            elif status is not None:
                run.warnings.append("CourtListener did not answer; the Caselaw Access Project answered for every row shown.")
            for idx, cite_text in beyond.items():
                hit = lookups.get(cite_text)
                if hit is not None and getattr(hit, "status", None) == "found":
                    g = group_meta[idx]["members"]
                    upgraded = _classify_group(run, g, idx + 1, run_limited=group_meta[idx]["limited"], cl_status={cite_text: 200})
                    upgraded.timings_ms.update(results[idx].timings_ms)
                    results[idx] = upgraded
        stage_lookup += _ms(t0)

    # 5. quotes + evidence --------------------------------------------------- #
    t0 = time.perf_counter()
    needed: dict[tuple[str, int, str], Optional[dict]] = {}
    plan: list[tuple[int, Optional[tuple[str, int, str]], bool]] = []
    for idx, r in enumerate(results):
        c = r.citation
        rc = r.evidence.real_case_at_page or r.evidence.name_hit
        slug = run.slug_for(c) if c is not None else None
        if rc is None or slug is None or c is None or c.volume is None:
            plan.append((idx, None, False))
            continue
        key = (slug, int(c.volume), rc.file_name or "")
        need_text = r.class_ == "verified" and bool(c.quotes) and bool(rc.file_name)
        if rc.file_name:
            rel = f"{slug}/{int(c.volume)}/cases/{rc.file_name}.json"
            if need_text or cap.cache.has(rel):
                needed.setdefault(key, None)
        plan.append((idx, key if rc.file_name else None, need_text))

    def fetch_case(key: tuple[str, int, str]):
        slug, vol, file_name = key
        try:
            return cap.case_json(slug, vol, file_name)
        except CorpusUnavailable as exc:
            return exc

    if needed:
        with ThreadPoolExecutor(max_workers=CONCURRENCY) as ex:
            for key, res in zip(list(needed), ex.map(fetch_case, list(needed))):
                needed[key] = res

    for idx, key, need_text in plan:
        r = results[idx]
        c = r.citation
        rc = r.evidence.real_case_at_page or r.evidence.name_hit
        if rc is None or c is None:
            if c is not None and c.quotes and r.class_ != "verified" and r.quote_check is None:
                results[idx] = rules.apply_quote_check(r, QuoteCheck(status="not_checked", quote=c.quotes[0]))
            continue
        tq = time.perf_counter()
        evidence = r.evidence.model_copy(deep=True)
        evidence.running_head = running_head_for(rc, c.page)
        evidence.page_marker = str(c.page) if c.page is not None else None
        case_json = needed.get(key) if key is not None else None
        opinion = ""
        if isinstance(case_json, dict):
            opinion = quotes.opinion_text(case_json)
            slug, vol, file_name = key  # type: ignore[misc]
            url = cap.case_url(slug, vol, file_name)
            if url not in evidence.links:
                evidence.links = list(evidence.links) + [url]
        elif isinstance(case_json, CorpusUnavailable):
            run.warnings.append(f"The free library did not answer for the opinion text of {rc.cite} ({_failure_text(case_json)}); the quote was not checked.")
        new = r.model_copy(deep=True, update={"evidence": evidence})
        if need_text and c.quotes:
            if opinion:
                checks = [quotes.check_quote(q, opinion) for q in c.quotes]
                qm = _pick_quote_result(checks)  # type: ignore[arg-type]
                new = rules.apply_quote_check(new, QuoteCheck(**qm.model_dump(include=set(QuoteCheck.model_fields))), qm.closest_passage)
                ev = new.evidence.model_copy(deep=True)
                if qm.excerpt:
                    ev.excerpt = qm.excerpt
                    ev.excerpt_highlight = qm.excerpt_highlight
                else:
                    ev.excerpt = _excerpt_from_start(opinion)
                    ev.excerpt_highlight = None
                new = new.model_copy(deep=True, update={"evidence": ev})
            else:
                new = rules.apply_quote_check(new, QuoteCheck(status="not_checked", quote=c.quotes[0]))
                if not isinstance(case_json, CorpusUnavailable):
                    run.warnings.append(f"The opinion text of {rc.cite} is not in the free library; the quote was not checked.")
        else:
            if c.quotes and new.quote_check is None:
                new = rules.apply_quote_check(new, QuoteCheck(status="not_checked", quote=c.quotes[0]))
            if opinion and new.evidence.excerpt is None:
                ev = new.evidence.model_copy(deep=True)
                ev.excerpt = _excerpt_from_start(opinion)
                ev.excerpt_highlight = None
                new = new.model_copy(deep=True, update={"evidence": ev})
        new.timings_ms.update(r.timings_ms)
        new.timings_ms["quotes"] = _ms(tq)
        results[idx] = new
    stage_quotes = _ms(t0)

    # 7. advisory (optional) ------------------------------------------------- #
    client = advisory_client if advisory_client is not None else advisory_mod.make_client()
    results, stage_advisory = advisory_mod.run_advisory(results, cleaned, client=client)

    # 8. assemble ------------------------------------------------------------ #
    offline = bool(cap.offline)
    memo = Memo(
        run_id=run_id,
        created_at=created_at,
        filing=Filing(filename=filename, pages=pages, words=words, label=label, bytes=n_bytes),
        sources_used=SourcesUsed(cap=True, courtlistener=sources_cl, advisory=stage_advisory is not None),
        results=results,
        elapsed_ms=_ms(t_start),
        stage_timings_ms=StageTimings(extract=stage_extract, lookup=stage_lookup, classify=stage_classify, quotes=stage_quotes, advisory=stage_advisory),
        offline=offline,
        sample_id=sample_id,
        warnings=list(dict.fromkeys(run.warnings)),
    )
    _log(memo, digest)
    return memo


def _log(memo: Memo, digest: str) -> None:
    line = {
        "event": "memo",
        "run_id": memo.run_id,
        "created_at": memo.created_at,
        "sha256": digest,
        "filename_sha256": hashlib.sha256((memo.filing.filename or "").encode("utf-8")).hexdigest(),
        "pages": memo.filing.pages,
        "n_citations": memo.counts.total,
        "counts": memo.counts.model_dump(exclude={"total"}),
        "stage_timings_ms": memo.stage_timings_ms.model_dump(),
        "elapsed_ms": memo.elapsed_ms,
        "sources_used": memo.sources_used.model_dump(),
        "offline": memo.offline,
        "sample_id": memo.sample_id,
        "warnings": len(memo.warnings),
    }
    if os.environ.get("CITEMEMO_QUIET") != "1":
        print(json.dumps(line, ensure_ascii=False), file=sys.stdout, flush=True)


def run_sample(
    sample_id: str,
    *,
    cap: Optional[CapClient] = None,
    courtlistener: Optional[CourtListenerClient] = None,
    advisory_client: Any = None,
    run_id: Optional[str] = None,
) -> Memo:
    """Run a seeded sample (``seed/samples.json``) through :func:`run_memo`. ``KeyError`` for an unknown id."""
    rec = sample_record(sample_id)
    if rec is None:
        raise KeyError(sample_id)
    path = ROOT / rec["file"]
    return run_memo(
        pdf_bytes=path.read_bytes(),
        filename=rec.get("filename") or path.name,
        label=rec.get("label"),
        sample_id=sample_id,
        cap=cap,
        courtlistener=courtlistener,
        advisory_client=advisory_client,
        run_id=run_id,
    )


__all__ = [
    "CONCURRENCY",
    "KNOWN_SAMPLE_IDS",
    "MAX_VOLUMES",
    "RUN_LIMIT_REASON",
    "load_samples",
    "run_memo",
    "run_sample",
    "running_head_for",
    "sample_path",
    "sample_record",
]
