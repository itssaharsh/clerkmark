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

Providers: Google Gemini (``GEMINI_API_KEY`` / ``GOOGLE_GENERATIVE_AI_API_KEY`` /
``GOOGLE_API_KEY``; default model ``gemini-3.8-flash``, the model Google names for new API users as of 2026-09-27) is used when its key is set;
otherwise Anthropic (``ANTHROPIC_API_KEY``; ``claude-haiku-4-5-20251001``). Both are
overridable with ``CITEMEMO_ADVISORY_MODEL``. The client is duck-typed
(``client.messages.create`` returning ``.content`` text blocks) so tests pass a fake;
``GeminiClient`` implements that surface over the Gemini REST API with httpx.
"""

from __future__ import annotations

import json
import os
import re
import time
from typing import Any, Mapping, Optional

from .models import Advisory, CitationResult

DEFAULT_MODEL = os.environ.get("CITEMEMO_ADVISORY_MODEL", "claude-haiku-4-5-20251001")
GEMINI_DEFAULT_MODEL = os.environ.get("CITEMEMO_ADVISORY_MODEL", "gemini-3.8-flash")
GEMINI_KEY_VARS = ("GEMINI_API_KEY", "GOOGLE_GENERATIVE_AI_API_KEY", "GOOGLE_API_KEY")
GEMINI_BASE_URL = os.environ.get("CITEMEMO_GEMINI_BASE_URL", "https://generativelanguage.googleapis.com")
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


def gemini_key(env: Optional[Mapping[str, str]] = None) -> str:
    """The first non-blank Gemini key among ``GEMINI_KEY_VARS``, else ''."""
    e = os.environ if env is None else env
    for name in GEMINI_KEY_VARS:
        v = (e.get(name) or "").strip()
        if v:
            return v
    return ""


def provider(env: Optional[Mapping[str, str]] = None) -> Optional[str]:
    """``"gemini"`` when a Gemini key is set, else ``"anthropic"`` when that key is set, else None."""
    e = os.environ if env is None else env
    if gemini_key(e):
        return "gemini"
    if (e.get("ANTHROPIC_API_KEY") or "").strip():
        return "anthropic"
    return None


def advisory_enabled(env: Optional[Mapping[str, str]] = None) -> bool:
    """True when a Gemini or Anthropic key is set and non-blank."""
    return provider(env) is not None


class _TextBlock:
    type = "text"

    def __init__(self, text: str) -> None:
        self.text = text


class _Response:
    def __init__(self, text: str, stop_reason: Optional[str] = None) -> None:
        self.content = [_TextBlock(text)]
        self.stop_reason = stop_reason


class _GeminiMessages:
    """``messages.create(...)`` over ``POST /v1beta/models/{model}:generateContent``."""

    def __init__(self, api_key: str, timeout: float, base_url: str, transport: Any = None) -> None:
        import httpx

        self._key = api_key
        self._base = base_url.rstrip("/")
        self._http = httpx.Client(timeout=timeout, transport=transport)

    def create(self, *, model: str, max_tokens: int, system: str, messages: list[dict[str, str]]) -> _Response:
        user = "\n\n".join(str(m.get("content", "")) for m in messages if m.get("role") == "user")
        body = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {
                "temperature": 0,
                "maxOutputTokens": max(int(max_tokens), 512),
                "responseMimeType": "application/json",
            },
        }
        if model.startswith("gemini-2.5"):
            body["generationConfig"]["thinkingConfig"] = {"thinkingBudget": 0}
        r = self._http.post(
            f"{self._base}/v1beta/models/{model}:generateContent",
            params={"key": self._key},
            json=body,
            headers={"Content-Type": "application/json"},
        )
        r.raise_for_status()
        data = r.json()
        cands = data.get("candidates") or []
        if not cands:
            return _Response("", stop_reason="refusal")
        parts = (cands[0].get("content") or {}).get("parts") or []
        text = "".join(str(p.get("text", "")) for p in parts if isinstance(p, dict))
        finish = str(cands[0].get("finishReason") or "")
        stop = "refusal" if finish in ("SAFETY", "PROHIBITED_CONTENT", "BLOCKLIST", "RECITATION") else None
        return _Response(text, stop)


class GeminiClient:
    """Duck-typed Anthropic-shaped client over the Gemini REST API (httpx, no SDK)."""

    provider = "gemini"

    def __init__(self, api_key: str, *, timeout: float = TIMEOUT_S, model: Optional[str] = None,
                 base_url: str = GEMINI_BASE_URL, transport: Any = None) -> None:
        self.default_model = model or GEMINI_DEFAULT_MODEL
        self.messages = _GeminiMessages(api_key, timeout, base_url, transport)


def make_client(timeout: float = TIMEOUT_S) -> Optional[Any]:
    """A Gemini client when its key is set, else an Anthropic client, else None (never raises)."""
    which = provider()
    if which is None:
        return None
    try:
        if which == "gemini":
            return GeminiClient(gemini_key(), timeout=timeout)
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
    if model == DEFAULT_MODEL and getattr(client, "default_model", None):
        model = str(client.default_model)
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
