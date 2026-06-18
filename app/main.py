"""FastAPI application factory.

Wires SessionMiddleware (signed cookies), Jinja2 templates, static files,
the healthcheck, the FOUNDATION-owned landing page, error pages, and the
three feature routers (auth, profiles, admin).
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.sessions import SessionMiddleware
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from app.config import settings
from app.csrf import CSRFMiddleware, get_csrf_token
from app.db import engine, get_db
from app.deps import _RedirectToLogin, current_member
from app.models import Member, MemberStatus
from app.routers import (
    admin,
    ai_profile,
    auth,
    concierge,
    feedback,
    ideas,
    invite,
    members,
    onboarding,
    photo,
    profiles,
    projects,
    roadmap,
    seo,
)
from app.services import members_service, seo_service

logging.basicConfig(level=logging.INFO)

BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"


def _csrf_context(request: Request) -> dict:
    """Expose the per-session CSRF token to every template render."""
    return {"csrf_token": get_csrf_token(request)}


def safe_url(value: str | None) -> str:
    """Return ``value`` only if it is a safe http(s)/relative URL, else ``''``.

    Defends against ``javascript:``/``data:``/``vbscript:`` and other dangerous
    schemes reaching ``href``/``src`` sinks on the public profile (where AI- and
    page-supplied URLs land). Jinja autoescaping blocks attribute breakout but
    NOT a ``javascript:`` scheme, so this filter is the guard for that vector.
    Scheme-relative (``//host``) and same-origin relative URLs are allowed.
    """
    if not value:
        return ""
    stripped = value.strip()
    if not stripped:
        return ""
    # A leading scheme is "<scheme>:" with no slash/?/# before the colon.
    head = stripped.split("/", 1)[0]
    if ":" in head:
        scheme = head.split(":", 1)[0].strip().lower()
        if scheme not in ("http", "https"):
            return ""
    return stripped


# Shared templates handle, also exposed on app.state for FEATURES routers.
templates = Jinja2Templates(
    directory=str(TEMPLATES_DIR), context_processors=[_csrf_context]
)
templates.env.filters["safe_url"] = safe_url


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

    # Profielfoto's (L1) worden door de app vanaf het /app/data-volume geserveerd
    # — geen aparte webserver. UPLOAD_DIR valt onder het bestaande data-volume;
    # we maken de subdir aan zodat de mount altijd een geldige directory heeft.
    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    app.mount(
        settings.upload_url_prefix,
        StaticFiles(directory=str(upload_dir)),
        name="uploads",
    )

    app.state.templates = templates

    _register_core_routes(app)
    _register_error_handlers(app)

    # Feature routers (bodies filled by FEATURES; stubs here keep imports valid).
    app.include_router(auth.router)
    app.include_router(profiles.router)
    app.include_router(admin.router)
    app.include_router(ai_profile.router)
    # Ledenpagina-feature (L1-L4): stubs nu, bodies door SERVICES/ROUTES+UI.
    app.include_router(members.router)
    app.include_router(projects.router)
    app.include_router(photo.router)
    app.include_router(seo.router)
    # Ervaring-laag (E1-E4): feedback, ideeenbus, roadmap, onboarding. Stubs nu;
    # route-bodies door SERVICES/ROUTES+UI.
    app.include_router(feedback.router)
    app.include_router(ideas.router)
    app.include_router(roadmap.router)
    app.include_router(onboarding.router)
    # Concierge-laag (Fase 1): intent-oppervlak + gegronde SSE-stroom.
    app.include_router(concierge.router)
    # Groep-invite-link (PRD-verificatie-links §0): één deelbare WhatsApp-link →
    # direct profiel bouwen (pre-approved) + admin-generatie.
    app.include_router(invite.router)

    return app


def _register_core_routes(app: FastAPI) -> None:
    @app.get("/", response_class=HTMLResponse)
    def index(
        request: Request,
        member: Member | None = Depends(current_member),
        db: Session = Depends(get_db),
    ) -> HTMLResponse:
        # Dual-shell (Agent-Shell Fase 1): een ingelogd, GOEDGEKEURD lid landt
        # direct in de agent-canvas (geen navigatie/menu — de agent is de shell).
        # Anoniem ÉN pending/geschorst krijgen de klassieke, crawlbare voordeur,
        # zodat showcase/SEO + de publieke launch heel blijven.
        if member is not None and member.status == MemberStatus.approved:
            # First-run guidance: een lid zonder (compleet) profiel krijgt het
            # rustige "zal ik je profiel opbouwen?"-aanbod in de canvas.
            profile = member.profile
            needs_profile = profile is None or (profile.completeness or 0) < 100
            return templates.TemplateResponse(
                request,
                "concierge/_canvas.html",
                {"member": member, "needs_profile": needs_profile},
            )
        # De voordeur toont één echt signaal (aantal publieke makers) + een
        # constellatie-preview. Eén poort-call (zelfde eager-load als /leden),
        # daarna in-memory tellen + slicen — geen tweede query.
        public_profiles = members_service.list_public_profiles(db)
        return templates.TemplateResponse(
            request,
            "index.html",
            {
                "member_count": len(public_profiles),
                "preview_stars": public_profiles[:5],
                # Publieke voordeur: schone canonical/og:url (geen lege href="").
                "canonical": seo_service.canonical_url("/"),
                # Absolute basis voor og:image (publieke unfurl-kaart).
                "base_url": settings.base_url.rstrip("/"),
            },
        )

    @app.get("/demo", response_class=HTMLResponse)
    def demo(request: Request) -> HTMLResponse:
        """Publieke, gescripte showcase: de agent bouwt een FICTIEF profiel op uit
        een FICTIEVE site (geen AI-call, geen DB). Duidelijk gelabeld als demo;
        indexeerbaar (launch-asset)."""
        return templates.TemplateResponse(
            request,
            "demo.html",
            {
                "canonical": seo_service.canonical_url("/demo"),
                "base_url": settings.base_url.rstrip("/"),
                "seo_title": "Demo — zo bouw je je profiel · dewereldvan.ai",
                "seo_desc": (
                    "Een door AI opgebouwd, fictief makersprofiel — zie in 20 "
                    "seconden hoe dewereldvan.ai werkt."
                ),
                "og_type": "website",
            },
        )

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
