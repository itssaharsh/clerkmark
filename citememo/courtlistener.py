"""Optional second source: the CourtListener v4 citation-lookup API (AC-15).

ADR-0001: CAP decides; CourtListener only confirms rows the free corpus does
not hold, and only when ``COURTLISTENER_TOKEN`` is set. Without a token no
network call is ever made and ``configured`` is False. The API (verified
2026-09-26): ``POST https://www.courtlistener.com/api/rest/v4/citation-lookup/``
with form field ``text``, header ``Authorization: Token <token>``; 401 without
a token; ≤ 250 citations and ≤ 64,000 characters per request; 60 valid
citations per minute; per-citation ``status`` 200 found / 300 ambiguous /
404 valid-but-not-found / 400 invalid reporter / 429 throttled.

``lookup`` never raises: a :class:`CourtListenerResult` carries ``status``
(``ok`` / ``not_configured`` / ``unauthorized`` / ``throttled`` / ``unavailable``)
so ``memo.py`` can print "CourtListener: not configured" or "unavailable" and
leave the CAP class unchanged. Every successful response is cached (memory +
``<cache dir>/courtlistener/<sha256 of text>.json``); with ``CITEMEMO_OFFLINE=1``
only the cache answers.
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, Optional

import httpx

from .cache import ABSENT, MISSING, DiskCache, is_offline

log = logging.getLogger(__name__)

CL_BASE = "https://www.courtlistener.com"
CL_LOOKUP_URL = CL_BASE + "/api/rest/v4/citation-lookup/"
USER_AGENT = "cite-intake-memo/0.1"
TIMEOUT_S = 20.0
MAX_CITATIONS = 250
MAX_CHARS = 64000
STATUS_MAP: Dict[int, str] = {200: "found", 300: "ambiguous", 404: "not_found", 400: "invalid_reporter", 429: "throttled"}
"""Per-citation HTTP-style status → label. Anything else maps to ``"other"``."""

_WS = re.compile(r"\s+")


def _norm(s: Optional[str]) -> str:
    return _WS.sub(" ", (s or "").strip())


@dataclass
class CitationLookup:
    """One per-citation entry of a citation-lookup response.

    ``status`` is one of ``found``, ``ambiguous``, ``not_found``,
    ``invalid_reporter``, ``throttled``, ``other`` (unknown code), or the
    client-side ``unavailable`` when the request that should have carried it
    failed. ``clusters`` are CourtListener cluster dicts (``id``, ``case_name``,
    ``absolute_url``, ``date_filed``, ``citations``).
    """

    citation: str
    status: str
    http_status: Optional[int] = None
    normalized_citations: List[str] = field(default_factory=list)
    error_message: str = ""
    start_index: Optional[int] = None
    end_index: Optional[int] = None
    clusters: List[Dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_raw(cls, raw: Mapping[str, Any]) -> "CitationLookup":
        code = raw.get("status")
        try:
            code_int: Optional[int] = int(code) if code is not None else None
        except (TypeError, ValueError):
            code_int = None
        return cls(
            citation=str(raw.get("citation") or ""),
            status=STATUS_MAP.get(code_int, "other") if code_int is not None else "other",
            http_status=code_int,
            normalized_citations=[str(c) for c in (raw.get("normalized_citations") or [])],
            error_message=str(raw.get("error_message") or ""),
            start_index=raw.get("start_index"),
            end_index=raw.get("end_index"),
            clusters=[dict(c) for c in (raw.get("clusters") or []) if isinstance(c, Mapping)],
        )

    @property
    def found(self) -> bool:
        """True only for status 200 (one unambiguous cluster set)."""
        return self.status == "found"

    @property
    def cluster_ids(self) -> List[int]:
        return [c["id"] for c in self.clusters if isinstance(c.get("id"), int)]

    @property
    def case_name(self) -> Optional[str]:
        """``case_name`` of the first cluster, if any."""
        return self.clusters[0].get("case_name") if self.clusters else None

    @property
    def date_filed(self) -> Optional[str]:
        return self.clusters[0].get("date_filed") if self.clusters else None

    @property
    def url(self) -> Optional[str]:
        """Absolute CourtListener URL of the first cluster (``absolute_url`` prefixed with the site)."""
        if not self.clusters:
            return None
        rel = self.clusters[0].get("absolute_url")
        if not rel:
            return None
        return rel if str(rel).startswith("http") else CL_BASE + str(rel)

    def matches(self, cite: str) -> bool:
        """True when ``cite`` equals this entry's ``citation`` or one of its ``normalized_citations``."""
        n = _norm(cite)
        return n == _norm(self.citation) or any(n == _norm(x) for x in self.normalized_citations)


@dataclass
class CourtListenerResult:
    """What :meth:`CourtListenerClient.lookup` returns; it never raises.

    ``status``: ``ok`` (entries mapped), ``not_configured`` (no token: no call
    made), ``unauthorized`` (401/403), ``throttled`` (whole-response 429),
    ``unavailable`` (timeout, connection error, 5xx, non-JSON, offline miss).
    ``reason`` is a short human sentence for the memo heading.
    """

    status: str
    reason: str = ""
    entries: List[CitationLookup] = field(default_factory=list)
    http_status: Optional[int] = None
    from_cache: bool = False
    raw: Optional[List[Any]] = field(default=None, repr=False)

    @property
    def ok(self) -> bool:
        return self.status == "ok"

    @property
    def throttled(self) -> bool:
        """True for a whole-response 429 or any per-citation 429 (DECISION-RULE §6.1: stop on the first)."""
        return self.status == "throttled" or any(e.status == "throttled" for e in self.entries)

    def by_citation(self, cite: str) -> Optional[CitationLookup]:
        """The entry for ``cite`` (matched on ``citation`` or ``normalized_citations``), or None."""
        for e in self.entries:
            if e.matches(cite):
                return e
        return None

    def found_citations(self) -> List[str]:
        """The ``citation`` strings CourtListener found (status 200)."""
        return [e.citation for e in self.entries if e.found]


class CourtListenerClient:
    """``CourtListenerClient(token=None, transport=None, cache=None, timeout=20.0, offline=None)``.

    ``token`` defaults to ``COURTLISTENER_TOKEN`` (blank = not configured);
    ``transport`` lets tests inject ``httpx.MockTransport``; ``cache`` is a
    :class:`citememo.cache.DiskCache` (default resolves the usual cache dir).
    The token never appears in ``repr``/``str``.
    """

    def __init__(
        self,
        token: Optional[str] = None,
        transport: Optional[httpx.BaseTransport] = None,
        cache: Optional[DiskCache] = None,
        timeout: float = TIMEOUT_S,
        offline: Optional[bool] = None,
        lookup_url: str = CL_LOOKUP_URL,
    ) -> None:
        raw = os.environ.get("COURTLISTENER_TOKEN", "") if token is None else token
        self._token: Optional[str] = (raw or "").strip() or None
        self.transport = transport
        self.cache = cache if cache is not None else DiskCache()
        self.timeout = float(timeout)
        self._offline = offline
        self.lookup_url = lookup_url
        self._client: Optional[httpx.Client] = None
        self.last_result: Optional[CourtListenerResult] = None

    # -- config ------------------------------------------------------------ #

    @property
    def configured(self) -> bool:
        """True when a non-blank token is available (``/api/health`` ``courtlistener``)."""
        return self._token is not None

    @property
    def offline(self) -> bool:
        return is_offline() if self._offline is None else bool(self._offline)

    def __repr__(self) -> str:
        return f"CourtListenerClient(configured={self.configured}, offline={self.offline})"

    __str__ = __repr__

    def _http(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(
                timeout=self.timeout,
                headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
                transport=self.transport,
            )
        return self._client

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None

    # -- lookup ------------------------------------------------------------ #

    @staticmethod
    def _cache_key(text: str) -> str:
        return "courtlistener/" + hashlib.sha256(text.encode("utf-8")).hexdigest() + ".json"

    @staticmethod
    def _parse(data: Any, from_cache: bool) -> CourtListenerResult:
        entries = [CitationLookup.from_raw(r) for r in data if isinstance(r, Mapping)]
        return CourtListenerResult(status="ok", entries=entries, http_status=200, from_cache=from_cache)

    def lookup(self, text: str) -> CourtListenerResult:
        """POST ``text`` to the citation-lookup endpoint and map every per-citation status.

        Returns ``status="not_configured"`` (no call) without a token, ``ok``
        with cached entries when the same text was asked before, and never
        raises. Callers chunk long inputs (see :meth:`lookup_citations`);
        this method sends ``text`` as is.
        """
        if not self.configured:
            res = CourtListenerResult(status="not_configured", reason="COURTLISTENER_TOKEN is not set")
            self.last_result = res
            return res
        text = text or ""
        if not text.strip():
            res = CourtListenerResult(status="ok")
            self.last_result = res
            return res
        rel = self._cache_key(text)
        cached = self.cache.get(rel)
        if cached is not MISSING and cached is not ABSENT and isinstance(cached, list):
            res = self._parse(cached, from_cache=True)
            self.last_result = res
            return res
        if self.offline:
            res = CourtListenerResult(status="unavailable", reason="offline: CITEMEMO_OFFLINE=1 and no cached answer")
            self.last_result = res
            return res
        res = self._post(text)
        if res.ok and res.raw is not None:
            self.cache.put(rel, res.raw)
        self.last_result = res
        return res

    def _post(self, text: str) -> CourtListenerResult:
        try:
            resp = self._http().post(
                self.lookup_url,
                data={"text": text},
                headers={"Authorization": f"Token {self._token}"},
            )
        except httpx.TimeoutException:
            return CourtListenerResult(status="unavailable", reason=f"timeout after {self.timeout:g} s")
        except httpx.TransportError as exc:
            return CourtListenerResult(status="unavailable", reason=f"connection error: {exc.__class__.__name__}")
        code = resp.status_code
        if code in (401, 403):
            return CourtListenerResult(status="unauthorized", reason=f"HTTP {code}: the token was rejected", http_status=code)
        if code == 429:
            return CourtListenerResult(status="throttled", reason="HTTP 429: CourtListener throttled this run", http_status=code)
        if code != 200:
            return CourtListenerResult(status="unavailable", reason=f"HTTP {code} from CourtListener", http_status=code)
        try:
            data = resp.json()
        except ValueError:
            return CourtListenerResult(status="unavailable", reason="non-JSON reply from CourtListener", http_status=code)
        if not isinstance(data, list):
            return CourtListenerResult(status="unavailable", reason="unexpected JSON shape from CourtListener", http_status=code)
        res = self._parse(data, from_cache=False)
        res.raw = data
        return res

    # -- many citations ---------------------------------------------------- #

    def lookup_citations(self, citations: Iterable[str]) -> Dict[str, CitationLookup]:
        """Look up many citation strings, one per line, chunked at 250 citations / 64,000 chars per request.

        Returns ``{citation: CitationLookup}`` for every distinct input. Stops
        on the first throttle (whole-response or per-citation 429) and marks
        the rest ``throttled``; a failed request marks its chunk and the rest
        ``unavailable``. ``{}`` when not configured. ``self.last_result`` holds
        the last response.
        """
        cites = list(dict.fromkeys(_norm(c) for c in citations if _norm(c)))
        out: Dict[str, CitationLookup] = {}
        if not self.configured or not cites:
            return out
        chunks: List[List[str]] = []
        cur: List[str] = []
        cur_len = 0
        for c in cites:
            add = len(c) + (1 if cur else 0)
            if cur and (len(cur) >= MAX_CITATIONS or cur_len + add > MAX_CHARS):
                chunks.append(cur)
                cur, cur_len = [], 0
                add = len(c)
            cur.append(c)
            cur_len += add
        if cur:
            chunks.append(cur)

        def mark(rest: Iterable[str], status: str, http_status: Optional[int], msg: str) -> None:
            for c in rest:
                out.setdefault(c, CitationLookup(citation=c, status=status, http_status=http_status, error_message=msg))

        for i, chunk in enumerate(chunks):
            res = self.lookup("\n".join(chunk))
            if not res.ok:
                remaining = [c for ch in chunks[i:] for c in ch]
                if res.status == "throttled":
                    mark(remaining, "throttled", 429, res.reason)
                else:
                    mark(remaining, "unavailable", res.http_status, res.reason)
                break
            for c in chunk:
                e = res.by_citation(c)
                out[c] = e if e is not None else CitationLookup(citation=c, status="other", error_message="no entry returned")
            if res.throttled:
                mark([c for ch in chunks[i + 1 :] for c in ch], "throttled", 429, "CourtListener throttled; CAP result shown")
                break
        return out


__all__ = [
    "CL_BASE",
    "CL_LOOKUP_URL",
    "MAX_CHARS",
    "MAX_CITATIONS",
    "STATUS_MAP",
    "TIMEOUT_S",
    "USER_AGENT",
    "CitationLookup",
    "CourtListenerClient",
    "CourtListenerResult",
]
