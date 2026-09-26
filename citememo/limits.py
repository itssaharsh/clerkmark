"""Abuse and platform limits for the public memo endpoint (ADR-0005; contract "Constraints").

The API runs as one Vercel Python function whose request body may not exceed 4.5 MB,
and ``POST /api/memo`` is a public write endpoint that triggers up to six concurrent
corpus fetches and optional paid model calls. The limits, all in one place:

* ``MAX_BODY_BYTES`` — request body ≤ 4 MB (413 ``too_large``; main.py checks the
  ``Content-Length`` header before the multipart body is parsed, then the bytes it read).
* ``MAX_TEXT_CHARS`` — 200,000 characters. Pasted text longer than that is refused
  with 413 ``too_large`` (main.py); text extracted from a PDF that passed the size gate
  is cut at the limit with a "Truncated:" warning line (memo.py via :func:`truncate_text`).
* ``MAX_CITATIONS`` — 250 full citations processed per memo; later citations are
  dropped with a "Truncated:" warning line (:func:`cap_citations`). ``Memo`` has no
  ``truncated`` field, so ``memo.warnings`` carries the reason line.
* ``RATE_LIMIT_RUNS`` / ``RATE_LIMIT_WINDOW_S`` — 10 memo runs per minute per client
  address, an in-memory sliding window (:class:`RateLimiter`) keyed by the first hop
  of ``X-Forwarded-For``, else the connection's host (:func:`client_key`). Only
  ``POST /api/memo`` is limited; the sample endpoint and ``/api/eval`` are exempt.

Envelope wording follows UI-SPEC §9 (its 20 MB revised to 4 MB, a logged deviation)
and docs/API.md §1.1; ``rate_limited`` is the one code added by this module.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from typing import Callable, Deque, Dict, Mapping, Optional, Sequence, Tuple, TypeVar

MAX_BODY_BYTES = 4 * 1024 * 1024
"""Largest accepted request body (Vercel functions stop at 4.5 MB)."""
MAX_BODY_LABEL = "4 MB"
MAX_TEXT_CHARS = 200_000
"""Characters of filing text read per memo."""
MAX_CITATIONS = 250
"""Full citations processed per memo."""
RATE_LIMIT_RUNS = 10
RATE_LIMIT_WINDOW_S = 60.0
"""Memo runs allowed per client address per window."""

TOO_LARGE_PDF = (
    f"This PDF is larger than {MAX_BODY_LABEL}. This prototype reads files up to {MAX_BODY_LABEL}.",
    "Export a smaller PDF or split the filing, or use the sample filing.",
)
TOO_LARGE_TEXT = (
    f"This text is longer than {MAX_TEXT_CHARS:,} characters. This prototype reads up to {MAX_TEXT_CHARS:,} characters.",
    "Paste the filing in parts, or upload it as a PDF.",
)
RATE_LIMITED = (
    f"Too many checks from this address: this prototype runs {RATE_LIMIT_RUNS} memos per minute.",
    "Wait a minute and run again, or use the sample filing.",
)

T = TypeVar("T")


# --------------------------------------------------------------------------- #
# Client identity
# --------------------------------------------------------------------------- #


def client_key(headers: Mapping[str, str], client_host: Optional[str]) -> str:
    """The address a request is rate-limited under.

    The first hop of ``X-Forwarded-For`` (what the platform's proxy prepends), else
    the connection's host, else ``"unknown"``. Works with Starlette's case-insensitive
    ``Headers`` and with a plain dict.
    """
    raw = headers.get("x-forwarded-for") or headers.get("X-Forwarded-For") or ""
    for hop in raw.split(","):
        hop = hop.strip()
        if hop:
            return hop
    return (client_host or "").strip() or "unknown"


# --------------------------------------------------------------------------- #
# Sliding-window rate limiter (one process, in memory)
# --------------------------------------------------------------------------- #


class RateLimiter:
    """``limit`` hits per ``window_s`` seconds per key; refused hits are not counted.

    ``hit(key)`` records one attempt and returns ``(allowed, retry_after_s)``:
    ``retry_after_s`` is 0 when allowed, else the seconds until the oldest counted
    attempt leaves the window. Thread-safe. ``clock`` is injectable for tests
    (default ``time.monotonic``). Memory stays bounded: idle keys are swept once the
    table grows past ``max_keys``.
    """

    def __init__(
        self,
        limit: int = RATE_LIMIT_RUNS,
        window_s: float = RATE_LIMIT_WINDOW_S,
        clock: Callable[[], float] = time.monotonic,
        max_keys: int = 10_000,
    ) -> None:
        self.limit = max(1, int(limit))
        self.window_s = float(window_s)
        self._clock = clock
        self._max_keys = max(1, int(max_keys))
        self._hits: Dict[str, Deque[float]] = {}
        self._lock = threading.Lock()

    def hit(self, key: str) -> Tuple[bool, float]:
        now = self._clock()
        cutoff = now - self.window_s
        with self._lock:
            q = self._hits.get(key)
            if q is None:
                if len(self._hits) >= self._max_keys:
                    self._sweep(cutoff)
                q = self._hits[key] = deque()
            while q and q[0] <= cutoff:
                q.popleft()
            if len(q) >= self.limit:
                return False, max(0.0, q[0] + self.window_s - now)
            q.append(now)
            return True, 0.0

    def _sweep(self, cutoff: float) -> None:
        for k in [k for k, q in self._hits.items() if not q or q[-1] <= cutoff]:
            del self._hits[k]

    def remaining(self, key: str) -> int:
        """Attempts left in the current window for ``key`` (does not record one)."""
        cutoff = self._clock() - self.window_s
        with self._lock:
            q = self._hits.get(key)
            live = sum(1 for t in q if t > cutoff) if q else 0
            return max(0, self.limit - live)

    def reset(self) -> None:
        """Forget every key (tests)."""
        with self._lock:
            self._hits.clear()


# --------------------------------------------------------------------------- #
# Input truncation (the memo still runs; the cut is said out loud)
# --------------------------------------------------------------------------- #


def truncate_text(text: str, limit: int = MAX_TEXT_CHARS) -> Tuple[str, Optional[str]]:
    """Cut ``text`` to at most ``limit`` characters (at the last whitespace within 200 chars of it).

    Returns ``(text, None)`` when nothing was cut, else ``(head, reason_line)`` where the
    reason line starts with ``"Truncated:"`` and is meant for ``memo.warnings``.
    """
    if len(text) <= limit:
        return text, None
    lo = max(0, limit - 200)
    cut = max(text.rfind(" ", lo, limit), text.rfind("\n", lo, limit))
    if cut <= 0:
        cut = limit
    note = f"Truncated: the filing has {len(text):,} characters; only the first {limit:,} were read. Run the rest separately."
    return text[:cut], note


def cap_citations(cites: Sequence[T], limit: int = MAX_CITATIONS) -> Tuple[list, Optional[str]]:
    """Keep the citations up to the ``limit``-th full one (``kind == "full"``); drop the rest.

    Non-full citations (Id., supra, statutes, unrecognized reporters) before the cut
    stay so the rows read in filing order. Returns ``(cites, None)`` when nothing was
    cut, else ``(head, reason_line)`` for ``memo.warnings``.
    """
    n_full = 0
    cut: Optional[int] = None
    for i, c in enumerate(cites):
        if getattr(c, "kind", "full") == "full":
            n_full += 1
            if n_full > limit and cut is None:
                cut = i
    if cut is None:
        return list(cites), None
    note = f"Truncated: the filing has {n_full} full citations; only the first {limit} were checked. Run the rest separately."
    return list(cites[:cut]), note


__all__ = [
    "MAX_BODY_BYTES",
    "MAX_BODY_LABEL",
    "MAX_CITATIONS",
    "MAX_TEXT_CHARS",
    "RATE_LIMITED",
    "RATE_LIMIT_RUNS",
    "RATE_LIMIT_WINDOW_S",
    "TOO_LARGE_PDF",
    "TOO_LARGE_TEXT",
    "RateLimiter",
    "cap_citations",
    "client_key",
    "truncate_text",
]
