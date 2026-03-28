from pathlib import Path

import logging
import time
import uuid
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import models  # noqa: F401
from .config import load_env_once
from .utils.api_response import fail, ok
from .database import (
    Base,
    engine,
    ensure_phase1_compatibility,
    ensure_phase2_compatibility,
    ensure_phase3_compatibility,
    ensure_phase4_compatibility,
    ensure_phase5_compatibility,
    ensure_phase6_compatibility,
    ensure_schema,
)
from .routes.auth import router as auth_router
from .routes.dashboard import router as dashboard_router
from .routes.player import router as player_router
from .routes.professor import router as professor_router
from .routes.questions import router as questions_router
from .routes.game import router as game_router
from .routes.analytics import router as analytics_router
from .routes.emotion import router as emotion_router

app = FastAPI(title="AI Adaptive Serious Game Backend", version="1.2.0")

load_env_once()

logger = logging.getLogger("asg")

STATIC_DIR = Path(__file__).resolve().parent / "web" / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _is_api_path(path: str) -> bool:
    # Dashboard and static assets return HTML/CSS/JS, not wrapped JSON.
    if path.startswith("/dashboard/api"):
        return True
    if path.startswith("/dashboard") or path.startswith("/static"):
        return False
    return True


@app.middleware("http")
async def request_logging_middleware(request, call_next):
    """
    Request logging (API-focused):
    - Adds an `X-Request-Id` header to every response.
    - Logs method/path/status/duration.
    - Logs a small JSON payload preview for gameplay endpoints (kept short to avoid secrets / huge bodies).
    """
    request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
    started = time.perf_counter()

    body_preview: str | None = None
    try:
        if _is_api_path(request.url.path) and request.method in ("POST", "PUT", "PATCH"):
            ct = (request.headers.get("content-type") or "").lower()
            # Only preview JSON bodies; skip multipart/binary.
            if ct.startswith("application/json"):
                raw = await request.body()
                if raw:
                    # Keep logs bounded.
                    body_preview = raw[:2048].decode("utf-8", errors="replace")
    except Exception:
        body_preview = None

    response = await call_next(request)
    dur_ms = int((time.perf_counter() - started) * 1000.0)

    # Attach request id for client debugging.
    try:
        response.headers["X-Request-Id"] = request_id
    except Exception:
        pass

    if _is_api_path(request.url.path):
        if body_preview:
            logger.info(
                "HTTP %s %s status=%s dur_ms=%s rid=%s body=%s",
                request.method,
                request.url.path,
                response.status_code,
                dur_ms,
                request_id,
                body_preview,
            )
        else:
            logger.info(
                "HTTP %s %s status=%s dur_ms=%s rid=%s",
                request.method,
                request.url.path,
                response.status_code,
                dur_ms,
                request_id,
            )

    return response


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request, exc: StarletteHTTPException):
    if not _is_api_path(request.url.path):
        if request.url.path.startswith("/dashboard") and not request.url.path.startswith("/dashboard/login"):
            if exc.status_code in (401, 403):
                return RedirectResponse(url="/dashboard/login", status_code=303)
        return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
    return JSONResponse(fail(str(exc.detail)), status_code=exc.status_code)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc: RequestValidationError):
    if not _is_api_path(request.url.path):
        return JSONResponse({"detail": exc.errors()}, status_code=422)
    return JSONResponse(fail("Validation error", details=exc.errors()), status_code=422)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request, exc: Exception):
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    if not _is_api_path(request.url.path):
        return JSONResponse({"detail": "Internal Server Error"}, status_code=500)
    return JSONResponse(fail("Internal server error"), status_code=500)


@app.on_event("startup")
def on_startup() -> None:
    # Log DB target (without secrets) for debugging environment issues.
    try:
        safe = engine.url.render_as_string(hide_password=True)
        logger.info("DB: %s", safe)
    except Exception:
        logger.info("DB: (unable to render url)")
    ensure_schema()
    ensure_phase2_compatibility()
    Base.metadata.create_all(bind=engine)
    ensure_phase1_compatibility()
    ensure_phase3_compatibility()
    ensure_phase4_compatibility()
    ensure_phase5_compatibility()
    ensure_phase6_compatibility()


@app.get("/")
def health_check():
    return ok({"status": "ok", "service": "adaptive-serious-game-backend"})


app.include_router(professor_router)
app.include_router(questions_router)
app.include_router(player_router)
app.include_router(game_router)
app.include_router(analytics_router)
app.include_router(emotion_router)
app.include_router(auth_router)
app.include_router(dashboard_router)
