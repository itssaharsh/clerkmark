"""Optional advisory pass (AC-16, DECISION-RULE step 11, ADR-0002): never changes a class.

For each ``verified`` row that carries a quoted passage, ask the model one question:
does the quoted passage support the sentence the filing cites it for? The answer is
JSON ``{"verdict": "supports" | "does_not_support" | "cannot_tell", "why": "..."}``
and lands in ``CitationResult.advisory``. Everything else stays exactly as the rule
engine left it.

Public surface
--------------
``advisory_enabled(env=None) -> bool``
    True when ``ANTHROPIC_API_KEY`` is set and non-blank.
``make_client(timeout=15.0)``
    An ``anthropic.Anthropic`` client (``max_retries=0``, 15 s timeout), or None
    when the key is missing or the SDK is not importable.
``proposition_for(result, text) -> str``
    The filing sentence(s) around the citation span (≤ 1200 chars): what the
    filer says the case stands for.
``run_advisory(results, text, *, client=None, model=DEFAULT_MODEL, max_calls=20)``
    ``(new_results, elapsed_ms | None)``. With ``client=None`` nothing runs and
    ``elapsed_ms`` is None ("Advisory: not run"). At most ``max_calls`` rows are
    asked (filing order); a refusal, malformed JSON, an unknown verdict, a timeout
    or any SDK error leaves that row's ``advisory`` as None. Classes are never
    touched.

Model: ``claude-haiku-4-5-20251001`` (BUILD-NOTES §2), overridable with
``CITEMEMO_ADVISORY_MODEL``. The client is duck-typed (``client.messages.create``)
so tests pass a fake.
"""

from __future__ import annotations

import json
import os
import re
import time
from typing import Any, Mapping, Optional

from .models import Advisory, CitationResult

DEFAULT_MODEL = os.environ.get("CITEMEMO_ADVISORY_MODEL", "claude-haiku-4-5-20251001")
MAX_CALLS = 20
TIMEOUT_S = 15.0
VERDICTS = ("supports", "does_not_support", "cannot_tell")

SYSTEM = (
    "You check legal citations for a court intake desk. You are given a sentence from a filing "
    "(the proposition the filer cites a case for) and the passage the filing quotes from that case, "
    "which has already been confirmed to appear in the opinion. Decide only whether the quoted passage "
    "supports the filer's proposition. Answer with one JSON object and nothing else: "
    '{"verdict": "supports" | "does_not_support" | "cannot_tell", "why": "<one plain sentence>"}. '
    "Use cannot_tell when the proposition is not stated near the quote or the passage is too short to judge."
)

_JSON_RE = re.compile(r"\{.*\}", re.S)


def advisory_enabled(env: Optional[Mapping[str, str]] = None) -> bool:
    """True when ``ANTHROPIC_API_KEY`` is set and non-blank."""
    e = os.environ if env is None else env
    return bool((e.get("ANTHROPIC_API_KEY") or "").strip())


def make_client(timeout: float = TIMEOUT_S) -> Optional[Any]:
    """An Anthropic client when the key is configured; None otherwise (never raises)."""
    if not advisory_enabled():
        return None
    try:
        import anthropic  # type: ignore

        return anthropic.Anthropic(timeout=timeout, max_retries=0)
    except Exception:  # pragma: no cover - SDK missing or misconfigured
        return None


def proposition_for(result: CitationResult, text: str, *, window: int = 900, limit: int = 1200) -> str:
    """The filing sentence(s) before the citation: what the filer cites the case for."""
    cite = result.citation
    start = None
    if cite is not None and cite.span:
        start = cite.span[0]
    if start is None and cite is not None and cite.text:
        i = text.find(cite.text)
        start = i if i >= 0 else None
    if start is None:
        i = text.find(result.cite_text)
        start = i if i >= 0 else 0
    lo = max(0, start - window)
    chunk = text[lo:start]
    # begin at a sentence boundary when there is one in the window
    m = re.search(r"[.!?]\s+(?=[A-Z\"“])", chunk[: max(0, len(chunk) - 200)])
    if m:
        chunk = chunk[m.end():]
    chunk = re.sub(r"\s+", " ", chunk).strip()
    if len(chunk) > limit:
        chunk = chunk[-limit:]
    return chunk


def parse_verdict(raw: str, model: str) -> Optional[Advisory]:
    """``Advisory`` from the model's text, or None when it is not the JSON asked for."""
    if not raw:
        return None
    m = _JSON_RE.search(raw)
    if not m:
        return None
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    verdict = str(data.get("verdict", "")).strip().lower().replace(" ", "_")
    why = str(data.get("why", "")).strip()
    if verdict not in VERDICTS:
        return None
    return Advisory(verdict=verdict, why=why or "(no reason given)", model=model)  # type: ignore[arg-type]


def _ask(client: Any, model: str, proposition: str, quote: str, cite_text: str) -> Optional[Advisory]:
    user = (
        f"Citation: {cite_text}\n\n"
        f"Filing sentence (the proposition): {proposition or '(no sentence found before the citation)'}\n\n"
        f"Quoted passage (confirmed in the opinion): \"{quote}\"\n\n"
        "Does the quoted passage support the proposition? Reply with the JSON object only."
    )
    try:
        resp = client.messages.create(
            model=model,
            max_tokens=300,
            system=SYSTEM,
            messages=[{"role": "user", "content": user}],
        )
    except Exception:
        return None
    if getattr(resp, "stop_reason", None) == "refusal":
        return None
    text = ""
    for block in getattr(resp, "content", []) or []:
        if getattr(block, "type", None) == "text":
            text += getattr(block, "text", "") or ""
    return parse_verdict(text, model)


def eligible(result: CitationResult) -> Optional[str]:
    """The quote to check when the row is ``verified`` and carries a quoted passage, else None."""
    if result.class_ != "verified":
        return None
    if result.quote_check is not None and result.quote_check.quote:
        return result.quote_check.quote
    if result.citation is not None and result.citation.quotes:
        return result.citation.quotes[0]
    return None


def run_advisory(
    results: list[CitationResult],
    text: str,
    *,
    client: Any = None,
    model: str = DEFAULT_MODEL,
    max_calls: int = MAX_CALLS,
) -> tuple[list[CitationResult], Optional[float]]:
    """Attach an ``Advisory`` to eligible rows. Returns ``(rows, elapsed_ms)``; ``None`` elapsed = not run."""
    if client is None:
        return [r.model_copy(deep=True) for r in results], None
    t0 = time.perf_counter()
    out: list[CitationResult] = []
    calls = 0
    for r in results:
        quote = eligible(r)
        if quote is None or calls >= max_calls:
            out.append(r.model_copy(deep=True))
            continue
        calls += 1
        verdict = _ask(client, model, proposition_for(r, text), quote, r.cite_text)
        out.append(r.model_copy(deep=True, update={"advisory": verdict}))
    return out, round((time.perf_counter() - t0) * 1000, 1)


__all__ = [
    "DEFAULT_MODEL",
    "MAX_CALLS",
    "TIMEOUT_S",
    "advisory_enabled",
    "eligible",
    "make_client",
    "parse_verdict",
    "proposition_for",
    "run_advisory",
]
