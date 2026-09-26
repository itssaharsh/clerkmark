"""Clerkmark — the citation memo API (docs/API.md). One FastAPI app, ``app``, at the repo root.

Routes: ``GET /`` (web/index.html), ``/static/*`` (web/static), ``/favicon.svg``,
``/wordmark.svg``, ``/tokens.css``, ``GET /api/health``, ``GET /api/samples``,
``POST /api/memo`` (multipart ``file`` PDF or form ``text``), ``POST /api/memo/sample/{id}``,
``GET /api/replay``, ``GET /api/eval[?rerun=1]``. Every non-2xx JSON body is the
``ErrorEnvelope`` ``{"error": {"code", "message", "hint"}}``.

Run locally: ``uvicorn main:app --reload``. Vercel detects ``app`` in ``main.py``
zero-config (BUILD-NOTES §6). Env (all optional): ``COURTLISTENER_TOKEN``,
``ANTHROPIC_API_KEY``, ``CITEMEMO_OFFLINE=1``, ``CITEMEMO_CACHE_DIR`` (.env.example).
Size caps and rate limits are T07's.
"""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from types import SimpleNamespace
from typing import Optional

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from citememo import __version__
from citememo import advisory as advisory_mod
from citememo import evaluate as evaluate_mod
from citememo import memo as memo_mod
from citememo.cap import CapClient
from citememo.courtlistener import CourtListenerClient
from citememo.extract import NoTextLayer, UnreadablePdf
from citememo.models import ErrorBody, ErrorEnvelope, EvalReport, Health, Memo

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


def envelope(status: int, code: str, message: str, hint: Optional[str] = None) -> JSONResponse:
    body = ErrorEnvelope(error=ErrorBody(code=code, message=message, hint=hint))  # type: ignore[arg-type]
    return JSONResponse(status_code=status, content=body.model_dump(mode="json"))


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
)


def json_model(model, status: int = 200) -> JSONResponse:
    return JSONResponse(status_code=status, content=model.model_dump(by_alias=True, mode="json"))


app = FastAPI(title="Clerkmark citation memo", version=__version__, docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=str(WEB / "static")), name="static")


@app.exception_handler(ApiError)
async def _api_error(_: Request, exc: ApiError) -> JSONResponse:
    return envelope(exc.status, exc.code, exc.message, exc.hint)


@app.exception_handler(StarletteHTTPException)
async def _http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
    if exc.status_code == 404:
        return envelope(404, "not_found", "No such page or route.", "See docs/API.md for the routes.")
    if exc.status_code == 405:
        return envelope(405, "internal", "Method not allowed.", None)
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
        if not data:
            data = None
    if data is not None:
        if not data.lstrip()[:5].startswith(b"%PDF-"):
            if text and text.strip():
                data = None
            else:
                raise ApiError(415, "unsupported_type", *UNSUPPORTED)
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
