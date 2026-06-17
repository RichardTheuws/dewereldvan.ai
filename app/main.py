"""FastAPI application factory.

Wires SessionMiddleware (signed cookies), Jinja2 templates, static files,
the healthcheck, the FOUNDATION-owned landing page, error pages, and the
three feature routers (auth, profiles, admin).
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.sessions import SessionMiddleware
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from app.config import settings
from app.csrf import CSRFMiddleware, get_csrf_token
from app.db import engine
from app.deps import _RedirectToLogin
from app.routers import admin, auth, profiles

logging.basicConfig(level=logging.INFO)

BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"


def _csrf_context(request: Request) -> dict:
    """Expose the per-session CSRF token to every template render."""
    return {"csrf_token": get_csrf_token(request)}


# Shared templates handle, also exposed on app.state for FEATURES routers.
templates = Jinja2Templates(
    directory=str(TEMPLATES_DIR), context_processors=[_csrf_context]
)


def create_app() -> FastAPI:
    app = FastAPI(title="dewereldvan.ai", docs_url=None, redoc_url=None)

    # Order matters (last-added runs outermost). We want, outer -> inner:
    # ProxyHeaders -> Session -> CSRF, so the CSRF layer can read the loaded
    # session and the session sees the corrected (https) scheme.
    app.add_middleware(CSRFMiddleware)
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.secret_key,
        max_age=settings.session_max_age_sec,
        same_site="lax",
        # Cookie carries Secure. TLS terminates at the Cloudflare tunnel
        # (HTTPS end-to-user); ProxyHeadersMiddleware below rewrites the scheme
        # from X-Forwarded-Proto so SessionMiddleware sees https on the internal
        # http hop and the Secure cookie is still issued.
        https_only=True,
    )
    # Trust the forwarded proto/host from the Cloudflare tunnel (the only
    # supported ingress). Added last so it runs first and the corrected scheme
    # is visible to the session/CSRF layers.
    app.add_middleware(ProxyHeadersMiddleware, trusted_hosts="*")

    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    app.state.templates = templates

    _register_core_routes(app)
    _register_error_handlers(app)

    # Feature routers (bodies filled by FEATURES; stubs here keep imports valid).
    app.include_router(auth.router)
    app.include_router(profiles.router)
    app.include_router(admin.router)

    return app


def _register_core_routes(app: FastAPI) -> None:
    @app.get("/", response_class=HTMLResponse)
    def index(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(request, "index.html")

    @app.get("/healthz")
    def healthz() -> JSONResponse:
        """Container healthcheck: confirms the app and the DB are reachable."""
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
        except SQLAlchemyError as exc:
            return JSONResponse(
                {"status": "error", "detail": str(exc)}, status_code=503
            )
        return JSONResponse({"status": "ok"})


def _register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(_RedirectToLogin)
    def _redirect_login(request: Request, exc: _RedirectToLogin) -> RedirectResponse:
        return RedirectResponse(url="/login", status_code=303)

    @app.exception_handler(StarletteHTTPException)
    def _http_exc(request: Request, exc: StarletteHTTPException):
        if exc.status_code == 404:
            return templates.TemplateResponse(
                request, "404.html", status_code=404
            )
        if exc.status_code >= 500:
            return templates.TemplateResponse(
                request, "500.html", status_code=exc.status_code
            )
        # Other client errors render a minimal message via the 404 template shell.
        return templates.TemplateResponse(
            request,
            "404.html",
            {"status_code": exc.status_code, "detail": exc.detail},
            status_code=exc.status_code,
        )


app = create_app()
