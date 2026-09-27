"""Clerkmark — the citation memo API (docs/API.md). One FastAPI app, ``app``, at the repo root.

Routes: ``GET /`` (web/index.html), ``/static/*`` (web/static), ``/favicon.svg``,
``/wordmark.svg``, ``/tokens.css``, ``GET /api/health``, ``GET /api/samples``,
``POST /api/memo`` (multipart ``file`` PDF or form ``text``), ``POST /api/memo/sample/{id}``,
``GET /api/replay``, ``GET /api/eval[?rerun=1]``. Every non-2xx JSON body is the
``ErrorEnvelope`` ``{"error": {"code", "message", "hint"}}``.

Run locally: ``uvicorn main:app --reload``. Vercel detects ``app`` in ``main.py``
zero-config (BUILD-NOTES §6). Env (all optional): ``COURTLISTENER_TOKEN``,
``ANTHROPIC_API_KEY``, ``CITEMEMO_OFFLINE=1``, ``CITEMEMO_CACHE_DIR`` (.env.example).

Limits (ADR-0005, ``citememo/limits.py``): ``POST /api/memo`` bodies over 4 MB → 413
``too_large`` (checked on ``Content-Length`` before the body is parsed, then on the bytes
read); pasted text over 200,000 characters → 413 ``too_large``; more than 10 memo runs a
minute from one address → 429 ``rate_limited`` with ``Retry-After`` (in-memory sliding
window keyed by the first ``X-Forwarded-For`` hop, else the client host; the sample
endpoint and ``/api/eval`` are exempt). More than 250 full citations, or PDF text over
200,000 characters, is processed up to the limit with a "Truncated:" line in
``memo.warnings`` (memo.py). A corpus outage never fails the memo: those rows come back
``not_checked`` ("Could not reach the free library.") with the memo at HTTP 200.
"""

from __future__ import annotations

import json
import logging
import math
import threading
from pathlib import Path
from types import SimpleNamespace
from typing import Optional

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.datastructures import Headers
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.types import ASGIApp, Receive, Scope, Send

from citememo import __version__
from citememo import advisory as advisory_mod
from citememo import evaluate as evaluate_mod
from citememo import limits
from citememo import memo as memo_mod
from citememo.cap import CapClient
from citememo.courtlistener import CourtListenerClient
from citememo.extract import NoTextLayer, UnreadablePdf
from citememo.models import ErrorBody, ErrorCode, ErrorEnvelope, EvalReport, Health, Memo

ROOT = Path(__file__).resolve().parent
WEB = ROOT / "web"
REPLAY_PATH = ROOT / "seed" / "replay.json"

log = logging.getLogger("citememo.api")


# --------------------------------------------------------------------------- #
# Errors
# --------------------------------------------------------------------------- #


class ApiError(Exception):
    """Raised inside a route; the handler turns it into the envelope."""

    def __init__(self, status: int, code: str, message: str, hint: Optional[str] = None) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.hint = hint


def envelope(status: int, code: ErrorCode, message: str, hint: Optional[str] = None) -> JSONResponse:
    """The ``ErrorEnvelope`` ``{"error": {"code", "message", "hint"}}`` for every non-2xx answer (incl. 429 ``rate_limited``)."""
    content = ErrorEnvelope(error=ErrorBody(code=code, message=message, hint=hint)).model_dump(mode="json")
    return JSONResponse(status_code=status, content=content)


NO_TEXT_LAYER = ("No text layer in this PDF. It looks like a scan; this prototype does not run OCR.", "Try a PDF saved from a word processor, or the sample filing.")
UNSUPPORTED = ("This file is not a PDF.", "Choose a PDF saved from a word processor, or use the sample filing.")
EMPTY = ("Nothing to check: send a PDF as `file` or text as `text`.", "Drop a PDF, paste text, or use the sample filing.")


# --------------------------------------------------------------------------- #
# App state (one CAP client per process; the last sample run feeds /api/eval)
# --------------------------------------------------------------------------- #

state = SimpleNamespace(
    cap=CapClient(),
    courtlistener=CourtListenerClient(),
    last_sample={},  # sample_id -> Memo
    lock=threading.Lock(),
    limiter=limits.RateLimiter(),  # 10 memo runs / minute / address (ADR-0005)
)


def json_model(model, status: int = 200) -> JSONResponse:
    return JSONResponse(status_code=status, content=model.model_dump(by_alias=True, mode="json"))


app = FastAPI(title="Clerkmark citation memo", version=__version__, docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=str(WEB / "static")), name="static")


# --------------------------------------------------------------------------- #
# Limits (ADR-0005): before the body is parsed, for POST /api/memo only
# --------------------------------------------------------------------------- #


def rate_limited_response(retry_after_s: float) -> JSONResponse:
    resp = envelope(429, "rate_limited", *limits.RATE_LIMITED)
    resp.headers["Retry-After"] = str(max(1, math.ceil(retry_after_s)))
    return resp


class LimitsMiddleware:
    """Refuse a throttled address (429) or an oversize ``Content-Length`` (413) before reading the body.

    Applies to ``POST /api/memo`` only: the sample endpoint and ``/api/eval`` are exempt,
    and every other route is untouched. A body without ``Content-Length`` (chunked) is
    counted as it arrives and refused (413) as soon as it passes 4 MB, so a client cannot
    make the multipart parser spool an unbounded upload to disk first (T09); the route
    handler still re-checks the bytes it read.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope.get("method") == "POST" and scope.get("path") == "/api/memo":
            headers = Headers(scope=scope)
            client = scope.get("client")
            key = limits.client_key(headers, client[0] if client else None)
            allowed, retry_after = state.limiter.hit(key)
            if not allowed:
                log.info("rate limited %s (retry after %.0f s)", key, retry_after)
                await rate_limited_response(retry_after)(scope, receive, send)
                return
            length = headers.get("content-length", "")
            if length.isdigit() and int(length) > limits.MAX_BODY_BYTES:
                await envelope(413, "too_large", *limits.TOO_LARGE_PDF)(scope, receive, send)
                return
            await self.app(scope, _counting_receive(receive, limits.MAX_BODY_BYTES), send)
            return
        await self.app(scope, receive, send)


def _counting_receive(receive: Receive, limit: int) -> Receive:
    """``receive`` that raises 413 once more than ``limit`` body bytes have arrived (mapped to ``too_large``)."""
    seen = 0

    async def wrapped():
        nonlocal seen
        message = await receive()
        if message.get("type") == "http.request":
            seen += len(message.get("body", b""))
            if seen > limit:
                raise StarletteHTTPException(status_code=413, detail="request body larger than the limit")
        return message

    return wrapped


# Headers on every response. The page's policy allows only same-origin script (no inline
# script, no eval) and Google Fonts for type; filing text is rendered with textContent
# (web/static/app.js), and the policy is the second line of defence if that ever slips.
CONTENT_SECURITY_POLICY = (
    "default-src 'self'; script-src 'self'; "
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
    "font-src 'self' https://fonts.gstatic.com data:; img-src 'self' data:; connect-src 'self'; "
    "object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
)
SECURITY_HEADERS = [
    (b"x-content-type-options", b"nosniff"),
    (b"referrer-policy", b"strict-origin-when-cross-origin"),
]


class SecurityHeadersMiddleware:
    """Add ``nosniff`` and a referrer policy to every response, and the CSP to HTML pages."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                present = {k.lower() for k, _ in headers}
                headers += [(k, v) for k, v in SECURITY_HEADERS if k not in present]
                ctype = next((v for k, v in headers if k.lower() == b"content-type"), b"")
                if ctype.startswith(b"text/html") and b"content-security-policy" not in present:
                    headers.append((b"content-security-policy", CONTENT_SECURITY_POLICY.encode()))
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, send_with_headers)


app.add_middleware(LimitsMiddleware)
app.add_middleware(SecurityHeadersMiddleware)  # outermost: also covers 413/429 answered by LimitsMiddleware


@app.exception_handler(ApiError)
async def _api_error(_: Request, exc: ApiError) -> JSONResponse:
    return envelope(exc.status, exc.code, exc.message, exc.hint)


@app.exception_handler(StarletteHTTPException)
async def _http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
    if exc.status_code == 404:
        return envelope(404, "not_found", "No such page or route.", "See docs/API.md for the routes.")
    if exc.status_code == 405:
        return envelope(405, "internal", "Method not allowed.", None)
    if exc.status_code == 400 and "maximum size" in str(exc.detail or "").lower():  # multipart part > 1 MB (Starlette)
        return envelope(413, "too_large", *limits.TOO_LARGE_TEXT)
    if exc.status_code == 413:  # a chunked body passed 4 MB while it was being read (_counting_receive)
        return envelope(413, "too_large", *limits.TOO_LARGE_PDF)
    return envelope(exc.status_code, "internal", str(exc.detail or "Request failed."), None)


@app.exception_handler(RequestValidationError)
async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
    return envelope(400, "empty", EMPTY[0], EMPTY[1])


@app.exception_handler(Exception)
async def _unhandled(_: Request, exc: Exception) -> JSONResponse:
    log.exception("unhandled error: %s", exc)
    return envelope(500, "internal", f"The server could not complete the check ({type(exc).__name__}).", "Run again; if it repeats, use the sample filing.")


# --------------------------------------------------------------------------- #
# Page and assets
# --------------------------------------------------------------------------- #


@app.get("/", include_in_schema=False)
async def index():
    page = WEB / "index.html"
    if not page.exists():
        return envelope(404, "not_found", "The memo page is not built yet.", "web/index.html is missing; the API routes under /api still answer.")
    return FileResponse(str(page), media_type="text/html; charset=utf-8")


def _asset(name: str, media_type: str):
    async def handler():
        path = WEB / name
        if not path.exists():
            return envelope(404, "not_found", f"No asset called '{name}'.", None)
        return FileResponse(str(path), media_type=media_type)

    handler.__name__ = f"asset_{name.replace('.', '_')}"
    return handler


app.get("/favicon.svg", include_in_schema=False)(_asset("favicon.svg", "image/svg+xml"))
app.get("/wordmark.svg", include_in_schema=False)(_asset("wordmark.svg", "image/svg+xml"))
app.get("/tokens.css", include_in_schema=False)(_asset("tokens.css", "text/css; charset=utf-8"))


# --------------------------------------------------------------------------- #
# API
# --------------------------------------------------------------------------- #


@app.get("/api/health")
async def health() -> JSONResponse:
    cap: CapClient = state.cap
    return json_model(
        Health(
            ok=True,
            version=__version__,
            offline=bool(cap.offline),
            courtlistener=bool(state.courtlistener.configured),
            advisory=advisory_mod.advisory_enabled(),
            replay_available=REPLAY_PATH.exists(),
            cache_dir=str(cap.cache_dir),
        )
    )


@app.get("/api/samples")
async def samples() -> JSONResponse:
    return JSONResponse(content=[s.model_dump(mode="json") for s in memo_mod.load_samples()])


def _run_memo_sync(**kwargs) -> Memo:
    try:
        return memo_mod.run_memo(cap=state.cap, courtlistener=state.courtlistener, **kwargs)
    except NoTextLayer:
        raise ApiError(422, "no_text_layer", *NO_TEXT_LAYER)
    except UnreadablePdf as exc:
        raise ApiError(415, "unsupported_type", UNSUPPORTED[0], f"The PDF could not be opened ({exc}). {UNSUPPORTED[1]}")


@app.post("/api/memo")
async def post_memo(file: Optional[UploadFile] = File(default=None), text: Optional[str] = Form(default=None)) -> JSONResponse:
    data: Optional[bytes] = None
    if file is not None:
        data = await file.read()
        if len(data) > limits.MAX_BODY_BYTES:  # a chunked upload has no Content-Length for the middleware to read
            raise ApiError(413, "too_large", *limits.TOO_LARGE_PDF)
        if not data:
            data = None
    if data is not None:
        if not data.lstrip()[:5].startswith(b"%PDF-"):
            if text and text.strip():
                data = None
            else:
                raise ApiError(415, "unsupported_type", *UNSUPPORTED)
    if data is None and text is not None and len(text) > limits.MAX_TEXT_CHARS:
        raise ApiError(413, "too_large", *limits.TOO_LARGE_TEXT)
    if data is None and not (text and text.strip()):
        raise ApiError(400, "empty", *EMPTY)
    if data is not None:
        memo = await run_in_threadpool(_run_memo_sync, pdf_bytes=data, filename=(file.filename if file and file.filename else "upload.pdf"), label=None)
    else:
        memo = await run_in_threadpool(_run_memo_sync, text=text, filename="pasted-text", label=None)
    return json_model(memo)


def _run_sample_sync(sample_id: str) -> Memo:
    memo = memo_mod.run_sample(sample_id, cap=state.cap, courtlistener=state.courtlistener)
    with state.lock:
        state.last_sample[sample_id] = memo
    return memo


@app.post("/api/memo/sample/{sample_id}")
async def post_sample(sample_id: str) -> JSONResponse:
    if memo_mod.sample_record(sample_id) is None:
        raise ApiError(404, "not_found", f"No sample called '{sample_id}'.", "GET /api/samples lists the seeded samples.")
    memo = await run_in_threadpool(_run_sample_sync, sample_id)
    return json_model(memo)


@app.get("/api/replay")
async def replay() -> JSONResponse:
    if not REPLAY_PATH.exists():
        raise ApiError(404, "not_found", "No replay recorded yet.", "Run scripts/record_replay.py.")
    try:
        data = json.loads(REPLAY_PATH.read_text(encoding="utf-8"))
        memo = Memo.model_validate(data)
    except Exception as exc:  # a corrupt recording is a server problem, not the user's
        raise ApiError(500, "internal", f"The replay file could not be read ({type(exc).__name__}).", "Run scripts/record_replay.py again.")
    memo.replay = True
    return json_model(memo)


@app.get("/api/eval")
async def eval_route(rerun: Optional[str] = None) -> JSONResponse:
    sample_id = memo_mod.KNOWN_SAMPLE_IDS[0] if memo_mod.KNOWN_SAMPLE_IDS else "sample-motion"
    fresh = rerun not in (None, "", "0", "false")
    with state.lock:
        memo = None if fresh else state.last_sample.get(sample_id)
    if memo is None:
        memo = await run_in_threadpool(_run_sample_sync, sample_id)
    report: EvalReport = await run_in_threadpool(evaluate_mod.evaluate, memo)
    return json_model(report)


__all__ = ["app", "state"]
