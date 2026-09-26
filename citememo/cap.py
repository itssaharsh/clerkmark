"""Caselaw Access Project (CAP) static-file client with a two-level cache.

ADR-0001: static.case.law is the primary, account-free corpus. Every lookup
goes reporter → slug → volumes → cases → opinion text:

    https://static.case.law/ReportersMetadata.json           (committed: data/cap/)
    https://static.case.law/{slug}/VolumesMetadata.json
    https://static.case.law/{slug}/{volume_folder}/CasesMetadata.json
    https://static.case.law/{slug}/{volume_folder}/cases/{file_name}.json

Fetch contract (DECISION-RULE §1.4), as seen by callers of :class:`CapClient`:

* **Present** → the parsed JSON (``volumes`` returns a dict, ``cases_in_volume``
  a list, ``case_json`` a dict, ``page_index`` a :class:`PageIndex`).
* **Absent** (HTTP 404, cached like a positive result) → ``None``.
* **Failed** (timeout after one retry, connection error, HTTP 5xx/429/403, a
  200 with a non-JSON body, or ``CITEMEMO_OFFLINE=1`` with nothing cached) →
  :class:`CorpusUnavailable` is raised, carrying ``url`` and ``reason``.
  Failures are never cached and an empty list is never returned silently.

Constants: User-Agent ``cite-intake-memo/0.1``, 20 s timeout, one retry,
bounded concurrency 6 for batch fetches. The seed's volumes ship warmed under
``seed/cache/cap`` so the demo runs offline (AC-7).
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple, TypeVar, Union

import httpx

from .cache import ABSENT, MISSING, REPO_ROOT, DiskCache, LRU, is_offline
from .models import RealCase

log = logging.getLogger(__name__)

CAP_BASE = "https://static.case.law"
USER_AGENT = "cite-intake-memo/0.1"
TIMEOUT_S = 20.0
CONCURRENCY = 6
RETRIES = 1
REPORTERS_PATH = REPO_ROOT / "data" / "cap" / "ReportersMetadata.json"
"""Committed copy of https://static.case.law/ReportersMetadata.json (401 reporters)."""

#: DECISION-RULE §1.3: the only two short_name keys that collide. ``mass.app.div.``
#: resolves to ``mass-app-div``; ``ct.cl.`` stays unmapped (None).
KEY_COLLISIONS: Dict[str, Optional[str]] = {"mass.app.div.": "mass-app-div", "ct.cl.": None}

T = TypeVar("T")
VolumeKey = Tuple[str, int]


class CorpusUnavailable(Exception):
    """The free corpus did not answer for ``url``.

    ``reason`` is one of ``"offline"`` (CITEMEMO_OFFLINE=1 and not cached),
    ``"timeout"`` (20 s, after one retry), ``"connection"``, ``"http <code>"``
    (5xx/429/403/other), ``"non-json"`` (HTTP 200 with a non-JSON body).
    ``str(exc)`` always contains the URL.
    """

    def __init__(self, url: str, reason: str, detail: Optional[str] = None) -> None:
        self.url = url
        self.reason = reason
        self.detail = detail
        msg = f"free corpus unavailable ({reason}): {url}"
        if detail:
            msg += f" — {detail}"
        super().__init__(msg)


# --------------------------------------------------------------------------- #
# Reporter keys and page parsing
# --------------------------------------------------------------------------- #


def reporter_key(short_name: Optional[str]) -> str:
    """DECISION-RULE §1.3 key: ``s.replace(" ", "").replace("'", "").lower()``."""
    return (short_name or "").replace(" ", "").replace("'", "").lower()


def digits(s: Optional[str]) -> List[int]:
    """All integers in ``s`` (``'377-391'`` → ``[377, 391]``; ``None`` → ``[]``)."""
    return [int(x) for x in re.findall(r"\d+", s or "")]


def parse_pages(first_raw: Optional[str], last_raw: Optional[str]) -> Tuple[Optional[int], Optional[int]]:
    """DECISION-RULE §1.5 page arithmetic on CAP's string pages.

    ``first = min(digits(first_page))`` or None (no digits → the case is
    excluded from page lookups); ``last = max(digits(last_page))`` or ``first``;
    ``last < first`` → ``last = first`` (us/525 has ``'1'``/``'0'``).
    """
    f = digits(first_raw)
    if not f:
        return None, None
    first = min(f)
    l = digits(last_raw)
    last = max(l) if l else first
    if last < first:
        last = first
    return first, last


# --------------------------------------------------------------------------- #
# Case entries and the per-volume page index
# --------------------------------------------------------------------------- #


@dataclass
class CaseEntry:
    """One row of a volume's ``CasesMetadata.json`` with the §1.5 fields parsed.

    ``first``/``last`` are ints when parseable (``None`` when the row has no page
    digits); ``first_page_raw``/``last_page_raw`` keep CAP's strings. ``raw`` is
    the untouched CAP row.
    """

    raw: Dict[str, Any]
    id: Optional[int]
    name: str
    full_name: str
    first_page_raw: Optional[str]
    last_page_raw: Optional[str]
    first: Optional[int]
    last: Optional[int]
    file_name: Optional[str]
    official_cite: Optional[str]
    all_cites: List[str]
    parallel_cites: List[str]
    decision_date: Optional[str]
    decision_year: Optional[int]
    court_name: Optional[str]
    court_abbreviation: Optional[str]

    @classmethod
    def from_raw(cls, raw: Mapping[str, Any]) -> "CaseEntry":
        first_raw = raw.get("first_page")
        last_raw = raw.get("last_page")
        first, last = parse_pages(first_raw, last_raw)
        cites = [c for c in (raw.get("citations") or []) if isinstance(c, Mapping) and c.get("cite")]
        official = [c["cite"] for c in cites if c.get("type") == "official"]
        court = raw.get("court") or {}
        date = raw.get("decision_date")
        year = None
        if isinstance(date, str) and len(date) >= 4 and date[:4].isdigit():
            year = int(date[:4])
        rid = raw.get("id")
        return cls(
            raw=dict(raw),
            id=int(rid) if isinstance(rid, int) or (isinstance(rid, str) and rid.isdigit()) else None,
            name=raw.get("name_abbreviation") or raw.get("name") or "",
            full_name=raw.get("name") or raw.get("name_abbreviation") or "",
            first_page_raw=first_raw,
            last_page_raw=last_raw,
            first=first,
            last=last,
            file_name=raw.get("file_name"),
            official_cite=official[0] if official else (cites[0]["cite"] if cites else None),
            all_cites=[c["cite"] for c in cites],
            parallel_cites=[c["cite"] for c in cites if c.get("type") == "parallel"],
            decision_date=date if isinstance(date, str) else None,
            decision_year=year,
            court_name=court.get("name") if isinstance(court, Mapping) else None,
            court_abbreviation=court.get("name_abbreviation") if isinstance(court, Mapping) else None,
        )

    @property
    def has_pages(self) -> bool:
        """True when the row takes part in page lookups (``first`` is an int)."""
        return self.first is not None

    def span(self) -> int:
        """``last - first`` (0 for one-page entries and rows without pages)."""
        if self.first is None or self.last is None:
            return 0
        return self.last - self.first


@dataclass
class PageLookup:
    """Result of :meth:`PageIndex.lookup` for one page ``P``.

    ``exact_hits``: cases whose ``first == P`` (§1.5 ``by_first``);
    ``official_hits``: cases whose official cite ends at page ``P`` (``by_official_cite``);
    ``spanning``: cases with ``first < P <= last``;
    ``gap``: ``None`` when ``P`` is covered by some case, ``"beyond_end"`` when
    ``P > max_last``, ``"hole"`` when uncovered inside the held range.
    """

    page: int
    exact_hits: List[CaseEntry] = field(default_factory=list)
    spanning: List[CaseEntry] = field(default_factory=list)
    gap: Optional[str] = None
    official_hits: List[CaseEntry] = field(default_factory=list)

    @property
    def candidates(self) -> List[CaseEntry]:
        """§2 step 6a candidates: ``official_hits ∪ exact_hits`` deduped, in that order."""
        out: List[CaseEntry] = []
        seen: set = set()
        for c in self.official_hits + self.exact_hits:
            k = id(c)
            if k not in seen:
                seen.add(k)
                out.append(c)
        return out


_WS = re.compile(r"\s+")


def _norm_cite(cite: str) -> str:
    return _WS.sub(" ", (cite or "").strip())


class PageIndex:
    """The §1.5 index of one volume: ``PageIndex.from_cases(slug, volume, raw_rows)``.

    Attributes: ``cases`` (all rows deduped by id, in file order, including
    rows without page digits, for name search), ``page_cases`` (rows with a
    ``first`` page), ``by_first`` (``int → list[CaseEntry]``), ``by_official_cite``
    (``"516 U.S. 545" → list[CaseEntry]``), ``covered`` (set of held pages),
    ``max_last`` (last held page or None), ``first_pages`` (``(min first, max last)``),
    ``volume_years`` (``(min, max)`` decision year over the cases).
    """

    def __init__(self, slug: str, volume: int, cases: Sequence[CaseEntry]) -> None:
        self.slug = slug
        self.volume = volume
        self.cases: List[CaseEntry] = list(cases)
        self.page_cases: List[CaseEntry] = [c for c in self.cases if c.has_pages]
        self.by_first: Dict[int, List[CaseEntry]] = {}
        self.by_official_cite: Dict[str, List[CaseEntry]] = {}
        self._by_official_page: Dict[int, List[CaseEntry]] = {}
        self.covered: set = set()
        for c in self.page_cases:
            self.by_first.setdefault(c.first, []).append(c)  # type: ignore[arg-type]
            self.covered.update(range(c.first, c.last + 1))  # type: ignore[arg-type]
        for c in self.cases:
            if c.official_cite:
                self.by_official_cite.setdefault(_norm_cite(c.official_cite), []).append(c)
                d = digits(c.official_cite)
                if d:
                    self._by_official_page.setdefault(d[-1], []).append(c)
        self.max_last: Optional[int] = max((c.last for c in self.page_cases), default=None)  # type: ignore[type-var]
        self.first_pages: Tuple[Optional[int], Optional[int]] = (
            min((c.first for c in self.page_cases), default=None),  # type: ignore[type-var]
            self.max_last,
        )
        years = [c.decision_year for c in self.cases if c.decision_year is not None]
        self.volume_years: Tuple[Optional[int], Optional[int]] = (min(years), max(years)) if years else (None, None)

    @classmethod
    def from_cases(cls, slug: str, volume: int, raw_cases: Iterable[Mapping[str, Any]]) -> "PageIndex":
        """Build from CAP ``CasesMetadata`` rows, deduping by case ``id``."""
        entries: List[CaseEntry] = []
        seen: set = set()
        for i, raw in enumerate(raw_cases):
            if not isinstance(raw, Mapping):
                continue
            e = CaseEntry.from_raw(raw)
            key = e.id if e.id is not None else ("row", i)
            if key in seen:
                continue
            seen.add(key)
            entries.append(e)
        return cls(slug, volume, entries)

    def lookup(self, page: int) -> PageLookup:
        """Locate ``page`` in the volume (see :class:`PageLookup`)."""
        page = int(page)
        exact = list(self.by_first.get(page, []))
        spanning = [c for c in self.page_cases if c.first < page <= c.last]  # type: ignore[operator]
        if page in self.covered:
            gap = None
        elif self.max_last is not None and page > self.max_last:
            gap = "beyond_end"
        else:
            gap = "hole"
        return PageLookup(
            page=page,
            exact_hits=exact,
            spanning=spanning,
            gap=gap,
            official_hits=list(self._by_official_page.get(page, [])),
        )

    def official(self, cite: str) -> List[CaseEntry]:
        """Cases whose official cite equals ``cite`` (whitespace-normalised), e.g. ``"516 U.S. 545"``."""
        return list(self.by_official_cite.get(_norm_cite(cite), []))

    def by_id(self, case_id: int) -> Optional[CaseEntry]:
        """The entry with CAP ``id`` ``case_id``, or None."""
        for c in self.cases:
            if c.id == case_id:
                return c
        return None

    def __len__(self) -> int:
        return len(self.cases)

    def __repr__(self) -> str:
        return f"PageIndex({self.slug}/{self.volume}: {len(self.cases)} cases, pages {self.first_pages[0]}–{self.max_last})"


# --------------------------------------------------------------------------- #
# Module-level helpers (also exposed on CapClient)
# --------------------------------------------------------------------------- #


def opinion_text(case_json: Optional[Mapping[str, Any]]) -> str:
    """Join ``casebody.opinions[].text`` with two newlines (``""`` when absent)."""
    if not case_json:
        return ""
    casebody = case_json.get("casebody") or {}
    opinions = casebody.get("opinions") or []
    parts = [o.get("text") for o in opinions if isinstance(o, Mapping) and o.get("text")]
    return "\n\n".join(parts)


_V_SPLIT = re.compile(r"\s+v\.?\s+", re.IGNORECASE)


def _upper_caption(name: str) -> str:
    return " v. ".join(part.upper() for part in _V_SPLIT.split(name.strip())) if name else ""


def running_head(case: Union[CaseEntry, Mapping[str, Any]]) -> str:
    """``"925 F.3d 1291 · J.D. v. AZAR"``: official cite (else the first cite) then the caption upper-cased.

    Accepts a :class:`CaseEntry` or a CAP case/metadata dict. The `` v. ``
    connector stays lower-case; without any cite the caption alone is returned.
    """
    if isinstance(case, CaseEntry):
        cite = case.official_cite or (case.all_cites[0] if case.all_cites else None)
        name = case.name
    else:
        cites = [c for c in (case.get("citations") or []) if isinstance(c, Mapping) and c.get("cite")]
        official = [c["cite"] for c in cites if c.get("type") == "official"]
        cite = official[0] if official else (cites[0]["cite"] if cites else None)
        name = case.get("name_abbreviation") or case.get("name") or ""
    caption = _upper_caption(name)
    return f"{cite} · {caption}" if cite else caption


def to_real_case(entry: Union[CaseEntry, Mapping[str, Any]]) -> RealCase:
    """Build ``models.RealCase`` (evidence.real_case_at_page) from a case entry.

    Raises ``ValueError`` when the entry has no page digits (such rows are
    excluded from page lookups and never become ``real_case_at_page``).
    """
    e = entry if isinstance(entry, CaseEntry) else CaseEntry.from_raw(entry)
    if e.first is None or e.last is None:
        raise ValueError(f"case {e.name!r} has no page digits")
    return RealCase(
        name=e.name,
        first_page=e.first,
        last_page=e.last,
        decision_date=e.decision_date or "",
        court=e.court_name or "",
        court_abbreviation=e.court_abbreviation,
        cite=e.official_cite or "",
        file_name=e.file_name,
        id=e.id,
        parallel_cites=list(e.parallel_cites),
    )


def _run_sync(coro: Awaitable[T]) -> T:
    """Run a coroutine from sync code, even when an event loop is already running."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)  # type: ignore[arg-type]
    with ThreadPoolExecutor(max_workers=1) as ex:
        return ex.submit(asyncio.run, coro).result()  # type: ignore[arg-type]


# --------------------------------------------------------------------------- #
# The client
# --------------------------------------------------------------------------- #


class CapClient:
    """Resolve reporters, volumes, cases and opinion text from static.case.law.

    ``CapClient(cache=None, reporters_path=None, transport=None, offline=None,
    timeout=20.0, concurrency=6, base_url=CAP_BASE, retries=1)``

    * ``cache``: a :class:`citememo.cache.DiskCache` (default: resolved from
      ``CITEMEMO_CACHE_DIR`` → ``seed/cache/cap`` → ``/tmp/citememo-cache``, with
      the committed seed cache always readable).
    * ``transport``: an ``httpx`` transport (tests pass ``httpx.MockTransport``).
    * ``offline``: ``None`` reads ``CITEMEMO_OFFLINE`` on every call; a bool forces it.

    Every method that touches the network may raise :class:`CorpusUnavailable`
    (see the module docstring); ``None`` means CAP answered 404.
    """

    _reporters_cache: Dict[str, List[Dict[str, Any]]] = {}
    _reporters_lock = threading.Lock()

    def __init__(
        self,
        cache: Optional[DiskCache] = None,
        reporters_path: Optional[Path] = None,
        transport: Optional[httpx.BaseTransport] = None,
        offline: Optional[bool] = None,
        timeout: float = TIMEOUT_S,
        concurrency: int = CONCURRENCY,
        base_url: str = CAP_BASE,
        retries: int = RETRIES,
    ) -> None:
        self.cache = cache if cache is not None else DiskCache()
        self.reporters_path = Path(reporters_path) if reporters_path else REPORTERS_PATH
        self.transport = transport
        self._offline = offline
        self.timeout = float(timeout)
        self.concurrency = max(1, int(concurrency))
        self.base_url = base_url.rstrip("/")
        self.retries = max(0, int(retries))
        self._client: Optional[httpx.Client] = None
        self._volumes_index: Dict[str, Optional[Dict[int, List[Dict[str, Any]]]]] = {}
        self._page_indexes = LRU(32)
        self._slug_by_key: Optional[Dict[str, Optional[str]]] = None
        self._by_slug: Optional[Dict[str, Dict[str, Any]]] = None

    # -- config ------------------------------------------------------------ #

    @property
    def offline(self) -> bool:
        """True when no network call may be made (``CITEMEMO_OFFLINE=1`` or ``offline=True``)."""
        return is_offline() if self._offline is None else bool(self._offline)

    @property
    def cache_dir(self) -> Path:
        """The writable cache directory (for ``/api/health``'s ``cache_dir``)."""
        return self.cache.write_dir

    def _headers(self) -> Dict[str, str]:
        return {"User-Agent": USER_AGENT, "Accept": "application/json"}

    def _sync_client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(
                timeout=self.timeout, headers=self._headers(), transport=self.transport, follow_redirects=True
            )
        return self._client

    def _async_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            timeout=self.timeout, headers=self._headers(), transport=self.transport, follow_redirects=True
        )

    def close(self) -> None:
        """Close the underlying sync HTTP client."""
        if self._client is not None:
            self._client.close()
            self._client = None

    def __enter__(self) -> "CapClient":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    def __repr__(self) -> str:
        return f"CapClient(base_url={self.base_url!r}, offline={self.offline}, cache_dir={str(self.cache_dir)!r})"

    # -- URLs -------------------------------------------------------------- #

    def url(self, rel: str) -> str:
        """Absolute CAP URL for a cache-relative path."""
        return f"{self.base_url}/{rel}"

    def volumes_url(self, slug: str) -> str:
        """``https://static.case.law/{slug}/VolumesMetadata.json``"""
        return self.url(f"{slug}/VolumesMetadata.json")

    def cases_url(self, slug: str, folder: Union[int, str]) -> str:
        """``https://static.case.law/{slug}/{folder}/CasesMetadata.json`` (folder = volume or e.g. ``'138-2'``)."""
        return self.url(f"{slug}/{folder}/CasesMetadata.json")

    def case_url(self, slug: str, folder: Union[int, str], file_name: str) -> str:
        """``https://static.case.law/{slug}/{folder}/cases/{file_name}.json``"""
        return self.url(f"{slug}/{folder}/cases/{file_name}.json")

    def links_for(self, slug: str, volume: Union[int, str], file_name: Optional[str] = None) -> List[str]:
        """The CAP URLs a row used, in fetch order (``evidence.links``)."""
        out = [self.volumes_url(slug), self.cases_url(slug, volume)]
        if file_name:
            out.append(self.case_url(slug, volume, file_name))
        return out

    # -- reporters --------------------------------------------------------- #

    def reporters(self) -> List[Dict[str, Any]]:
        """The 401 CAP reporters from ``data/cap/ReportersMetadata.json`` (loaded once per path)."""
        key = str(self.reporters_path)
        with self._reporters_lock:
            data = self._reporters_cache.get(key)
            if data is None:
                with self.reporters_path.open("r", encoding="utf-8") as fh:
                    data = json.load(fh)
                if not isinstance(data, list):
                    raise ValueError(f"{self.reporters_path}: expected a list of reporters")
                self._reporters_cache[key] = data
        return data

    def _reporter_tables(self) -> Tuple[Dict[str, Optional[str]], Dict[str, Dict[str, Any]]]:
        if self._slug_by_key is None or self._by_slug is None:
            by_key: Dict[str, List[str]] = {}
            by_slug: Dict[str, Dict[str, Any]] = {}
            for r in self.reporters():
                slug = r.get("slug")
                if not slug:
                    continue
                by_slug[slug] = r
                by_key.setdefault(reporter_key(r.get("short_name")), []).append(slug)
            table: Dict[str, Optional[str]] = {}
            for k, slugs in by_key.items():
                if k in KEY_COLLISIONS:
                    table[k] = KEY_COLLISIONS[k]
                elif len(slugs) == 1:
                    table[k] = slugs[0]
                else:
                    log.warning("unlisted reporter key collision %r -> %r; left unmapped", k, slugs)
                    table[k] = None
            self._slug_by_key, self._by_slug = table, by_slug
        return self._slug_by_key, self._by_slug

    def reporter_slug(self, short_name: Optional[str]) -> Optional[str]:
        """Map an eyecite reporter string to its CAP slug, or None when CAP does not hold it.

        ``"F.3d"`` → ``"f3d"``, ``"F. Supp. 2d"`` → ``"f-supp-2d"``, ``"U.S."`` → ``"us"``,
        ``"So. 3d"`` → ``"so3d"``, ``"F. App'x"`` → ``"f-appx"``, ``"F.4th"`` → None.
        Never slugifies an unknown reporter (DECISION-RULE §1.3).
        """
        k = reporter_key(short_name)
        if not k:
            return None
        return self._reporter_tables()[0].get(k)

    def reporter_info(self, slug: str) -> Optional[Dict[str, Any]]:
        """The ReportersMetadata row for ``slug``, or None."""
        return self._reporter_tables()[1].get(slug)

    def reporter_years(self, slug: str) -> Tuple[Optional[int], Optional[int]]:
        """``(start_year, end_year)`` from ReportersMetadata (``(None, None)`` for an unknown slug)."""
        r = self.reporter_info(slug)
        if not r:
            return None, None
        return r.get("start_year"), r.get("end_year")

    def reporter_short_name(self, slug: str) -> Optional[str]:
        """``"f-supp-2d"`` → ``"F. Supp. 2d"``."""
        r = self.reporter_info(slug)
        return r.get("short_name") if r else None

    # -- fetch core (sync) ------------------------------------------------- #

    def _decode(self, rel: str, url: str, resp: httpx.Response) -> Any:
        """Turn a 200/404 response into Present (data) / Absent (None); cache both."""
        if resp.status_code == 404:
            self.cache.put_absent(rel)
            return None
        body = resp.text
        if not body.lstrip().startswith(("[", "{")):
            raise CorpusUnavailable(url, "non-json", "HTTP 200 with a non-JSON body")
        try:
            data = json.loads(body)
        except ValueError as exc:
            raise CorpusUnavailable(url, "non-json", str(exc)) from exc
        self.cache.put(rel, data)
        return data

    @staticmethod
    def _classify_response(resp: httpx.Response) -> Optional[str]:
        """None when the response is a final answer (200/404); else the failure reason."""
        if resp.status_code in (200, 404):
            return None
        return f"http {resp.status_code}"

    def _request_sync(self, url: str) -> httpx.Response:
        reason = "unknown"
        detail: Optional[str] = None
        for attempt in range(self.retries + 1):
            try:
                resp = self._sync_client().get(url)
            except httpx.TimeoutException as exc:
                reason, detail = "timeout", f"{self.timeout:g} s"
                log.warning("CAP timeout (%d/%d) %s: %s", attempt + 1, self.retries + 1, url, exc)
                continue
            except httpx.TransportError as exc:
                reason, detail = "connection", str(exc) or exc.__class__.__name__
                log.warning("CAP connection error (%d/%d) %s: %s", attempt + 1, self.retries + 1, url, exc)
                continue
            failure = self._classify_response(resp)
            if failure is None:
                return resp
            reason, detail = failure, None
            log.warning("CAP %s (%d/%d) %s", failure, attempt + 1, self.retries + 1, url)
        raise CorpusUnavailable(url, reason, detail)

    def _get_json(self, rel: str) -> Any:
        """Present → data; Absent → None; Failed/offline → CorpusUnavailable."""
        v = self.cache.get(rel)
        if v is ABSENT:
            return None
        if v is not MISSING:
            return v
        url = self.url(rel)
        if self.offline:
            raise CorpusUnavailable(url, "offline", "CITEMEMO_OFFLINE=1 and the file is not cached")
        return self._decode(rel, url, self._request_sync(url))

    # -- fetch core (async) ------------------------------------------------ #

    async def _request_async(self, ac: httpx.AsyncClient, url: str) -> httpx.Response:
        reason = "unknown"
        detail: Optional[str] = None
        for attempt in range(self.retries + 1):
            try:
                resp = await ac.get(url)
            except httpx.TimeoutException:
                reason, detail = "timeout", f"{self.timeout:g} s"
                continue
            except httpx.TransportError as exc:
                reason, detail = "connection", str(exc) or exc.__class__.__name__
                continue
            failure = self._classify_response(resp)
            if failure is None:
                return resp
            reason, detail = failure, None
        raise CorpusUnavailable(url, reason, detail)

    async def _get_json_async(self, ac: httpx.AsyncClient, rel: str) -> Any:
        v = self.cache.get(rel)
        if v is ABSENT:
            return None
        if v is not MISSING:
            return v
        url = self.url(rel)
        if self.offline:
            raise CorpusUnavailable(url, "offline", "CITEMEMO_OFFLINE=1 and the file is not cached")
        return self._decode(rel, url, await self._request_async(ac, url))

    # -- volumes ----------------------------------------------------------- #

    @staticmethod
    def _index_volumes(data: Any) -> Dict[int, List[Dict[str, Any]]]:
        out: Dict[int, List[Dict[str, Any]]] = {}
        for entry in data if isinstance(data, list) else []:
            if not isinstance(entry, Mapping):
                continue
            vn = str(entry.get("volume_number") or "").strip()
            if not vn.isdigit():
                continue
            out.setdefault(int(vn), []).append(dict(entry))
        return out

    def _volumes_from_data(self, slug: str, data: Any) -> Optional[Dict[int, List[Dict[str, Any]]]]:
        vols = None if data is None else self._index_volumes(data)
        self._volumes_index[slug] = vols
        return vols

    def volumes(self, slug: str) -> Optional[Dict[int, List[Dict[str, Any]]]]:
        """``VolumesMetadata`` for ``slug`` as ``{volume_number: [entry, ...]}``.

        Int keys; non-numeric volume numbers are skipped; duplicate volume rows
        (a3d lists 41) are grouped under one key, each with its own
        ``volume_folder``. None when CAP answers 404 (e.g. ``f4th``).
        """
        if slug in self._volumes_index:
            return self._volumes_index[slug]
        return self._volumes_from_data(slug, self._get_json(f"{slug}/VolumesMetadata.json"))

    async def volumes_async(self, ac: httpx.AsyncClient, slug: str) -> Optional[Dict[int, List[Dict[str, Any]]]]:
        """Async twin of :meth:`volumes` using an open ``httpx.AsyncClient``."""
        if slug in self._volumes_index:
            return self._volumes_index[slug]
        return self._volumes_from_data(slug, await self._get_json_async(ac, f"{slug}/VolumesMetadata.json"))

    def vmax(self, slug: str) -> Optional[int]:
        """Highest volume number CAP lists for ``slug`` (``us`` → 572); None when absent/empty."""
        vols = self.volumes(slug)
        if not vols:
            return None
        return max(vols)

    def vmin(self, slug: str) -> Optional[int]:
        """Lowest volume number CAP lists for ``slug``."""
        vols = self.volumes(slug)
        if not vols:
            return None
        return min(vols)

    def cap_end_year(self, slug: str) -> Optional[int]:
        """DECISION-RULE §3 ``cap_end``: max non-zero ``end_year`` in VolumesMetadata, else the reporter's ``end_year``."""
        vols = self.volumes(slug)
        if vols is None:
            return None
        years = [
            int(e["end_year"])
            for entries in vols.values()
            for e in entries
            if isinstance(e.get("end_year"), int) and e["end_year"] > 0
        ]
        if years:
            return max(years)
        return self.reporter_years(slug)[1]

    def _folders(self, vols: Optional[Dict[int, List[Dict[str, Any]]]], volume: int) -> List[str]:
        if not vols:
            return []
        out: List[str] = []
        for e in vols.get(int(volume), []):
            folder = str(e.get("volume_folder") or e.get("volume_number") or volume)
            if folder not in out:
                out.append(folder)
        return out

    def volume_folders(self, slug: str, volume: int) -> List[str]:
        """CAP folder names holding ``volume`` (``["925"]``; a3d 138 → ``["138", "138-2"]``); ``[]`` when not listed."""
        return self._folders(self.volumes(slug), volume)

    # -- cases ------------------------------------------------------------- #

    @staticmethod
    def _merge_cases(parts: List[Optional[Any]]) -> Optional[List[Dict[str, Any]]]:
        present = [p for p in parts if p is not None]
        if not present:
            return None
        out: List[Dict[str, Any]] = []
        seen: set = set()
        for data in present:
            for row in data if isinstance(data, list) else []:
                if not isinstance(row, Mapping):
                    continue
                cid = row.get("id")
                if cid is not None:
                    if cid in seen:
                        continue
                    seen.add(cid)
                out.append(dict(row))
        return out

    def cases_in_volume(self, slug: str, volume: int) -> Optional[List[Dict[str, Any]]]:
        """``CasesMetadata`` rows for ``slug``/``volume``: the union over the volume's folders, deduped by ``id``.

        None when the volume is not listed in ``VolumesMetadata`` (no fetch is
        made) or every folder answers 404.
        """
        folders = self.volume_folders(slug, volume)
        if not folders:
            return None
        return self._merge_cases([self._get_json(f"{slug}/{f}/CasesMetadata.json") for f in folders])

    async def cases_in_volume_async(self, ac: httpx.AsyncClient, slug: str, volume: int) -> Optional[List[Dict[str, Any]]]:
        """Async twin of :meth:`cases_in_volume`."""
        folders = self._folders(await self.volumes_async(ac, slug), volume)
        if not folders:
            return None
        parts = [await self._get_json_async(ac, f"{slug}/{f}/CasesMetadata.json") for f in folders]
        return self._merge_cases(parts)

    def page_index(self, slug: str, volume: int) -> Optional[PageIndex]:
        """The §1.5 :class:`PageIndex` for ``slug``/``volume`` (memoised); None when the volume is absent.

        ``page_index("f3d", 925).lookup(1339)`` → ``exact_hits=[]``, ``spanning=[J.D. v. Azar]``;
        ``.lookup(1291)`` → ``exact_hits=[J.D. v. Azar]``; ``.lookup(1400)`` → ``gap="beyond_end"``.
        """
        key = f"{slug}/{int(volume)}"
        cached = self._page_indexes.get(key)
        if cached is not MISSING:
            return cached
        cases = self.cases_in_volume(slug, volume)
        idx = None if cases is None else PageIndex.from_cases(slug, int(volume), cases)
        self._page_indexes.put(key, idx)
        return idx

    def case_json(self, slug: str, volume: int, file_name: str) -> Optional[Dict[str, Any]]:
        """The full case file ``{slug}/{folder}/cases/{file_name}.json`` (``casebody.opinions[].text`` etc.).

        Tries the volume's folders in order (``str(volume)`` first); None when
        CAP answers 404 for all of them.
        """
        folders = [str(volume)]
        try:
            for f in self.volume_folders(slug, volume):
                if f not in folders:
                    folders.append(f)
        except CorpusUnavailable:
            pass  # offline without the volume index: still try the plain folder
        for f in folders:
            data = self._get_json(f"{slug}/{f}/cases/{file_name}.json")
            if data is not None:
                return data
        return None

    # -- text helpers ------------------------------------------------------ #

    @staticmethod
    def opinion_text(case_json: Optional[Mapping[str, Any]]) -> str:
        """Join ``casebody.opinions[].text`` with two newlines."""
        return opinion_text(case_json)

    @staticmethod
    def running_head(case: Union[CaseEntry, Mapping[str, Any]]) -> str:
        """``"925 F.3d 1291 · J.D. v. AZAR"`` (official cite · caption upper-cased)."""
        return running_head(case)

    @staticmethod
    def to_real_case(entry: Union[CaseEntry, Mapping[str, Any]]) -> RealCase:
        """Build ``models.RealCase`` from a case entry."""
        return to_real_case(entry)

    # -- batch ------------------------------------------------------------- #

    async def fetch_volumes_batch_async(
        self, pairs: Iterable[VolumeKey]
    ) -> Dict[VolumeKey, Union[List[Dict[str, Any]], None, CorpusUnavailable]]:
        """Fetch ``CasesMetadata`` for many ``(slug, volume)`` pairs with at most 6 requests in flight.

        Returns ``{(slug, volume): rows | None | CorpusUnavailable}``: a list when
        present, None when absent, the exception instance when that volume
        failed (per-volume degrade; nothing is raised). Each slug's volume
        index is fetched once first. Everything lands in the two-level cache.
        """
        wanted: List[VolumeKey] = []
        for slug, vol in pairs:
            key = (slug, int(vol))
            if key not in wanted:
                wanted.append(key)
        out: Dict[VolumeKey, Union[List[Dict[str, Any]], None, CorpusUnavailable]] = {}
        if not wanted:
            return out
        sem = asyncio.Semaphore(self.concurrency)
        async with self._async_client() as ac:

            async def vols_for(slug: str) -> Union[Optional[Dict[int, List[Dict[str, Any]]]], CorpusUnavailable]:
                async with sem:
                    try:
                        return await self.volumes_async(ac, slug)
                    except CorpusUnavailable as exc:
                        return exc

            slugs = list(dict.fromkeys(s for s, _ in wanted))
            vol_results = dict(zip(slugs, await asyncio.gather(*(vols_for(s) for s in slugs))))

            async def one(key: VolumeKey) -> None:
                slug, vol = key
                v = vol_results[slug]
                if isinstance(v, CorpusUnavailable):
                    out[key] = v
                    return
                folders = self._folders(v, vol)
                if not folders:
                    out[key] = None
                    return
                async with sem:
                    try:
                        parts = [await self._get_json_async(ac, f"{slug}/{f}/CasesMetadata.json") for f in folders]
                    except CorpusUnavailable as exc:
                        out[key] = exc
                        return
                out[key] = self._merge_cases(parts)

            await asyncio.gather(*(one(k) for k in wanted))
        return {k: out[k] for k in wanted}

    def fetch_volumes_batch(
        self, pairs: Iterable[VolumeKey]
    ) -> Dict[VolumeKey, Union[List[Dict[str, Any]], None, CorpusUnavailable]]:
        """Sync facade of :meth:`fetch_volumes_batch_async` (safe to call with or without a running loop)."""
        return _run_sync(self.fetch_volumes_batch_async(list(pairs)))


__all__ = [
    "CAP_BASE",
    "CONCURRENCY",
    "KEY_COLLISIONS",
    "REPORTERS_PATH",
    "RETRIES",
    "TIMEOUT_S",
    "USER_AGENT",
    "CapClient",
    "CaseEntry",
    "CorpusUnavailable",
    "PageIndex",
    "PageLookup",
    "digits",
    "opinion_text",
    "parse_pages",
    "reporter_key",
    "running_head",
    "to_real_case",
]
