"""FastAPI application factory.

Wires SessionMiddleware (signed cookies), Jinja2 templates, static files,
the healthcheck, the FOUNDATION-owned landing page, error pages, and the
three feature routers (auth, profiles, admin).
"""

from __future__ import annotations

import contextlib
import logging
from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.concurrency import run_in_threadpool
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
    connect,
    connections,
    discovery,
    feedback,
    ideas,
    invite,
    members,
    notifications,
    onboarding,
    photo,
    posts,
    proef,
    profiles,
    projects,
    roadmap,
    seo,
    tools,
)
from app.services import members_service, post_service, seo_service

logging.basicConfig(level=logging.INFO)

BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"


def _csrf_context(request: Request) -> dict:
    """Expose the per-session CSRF token to every template render."""
    return {"csrf_token": get_csrf_token(request)}


def compute_graph_links(profiles: list, *, max_links: int = 12) -> list[list[int]]:
    """Index-paren van profielen die ≥1 tag of tool delen — de constellatie-lijnen.

    Strikt in-memory over de al eager-geladen ``tags``/``tools`` (geen extra query,
    geen LLM → nul kosten, nul hallucinatie): elke lijn staat voor een ECHTE
    gedeelde grond tussen twee makers. Gecapt zodat de hero leesbaar blijft."""
    keys: list[set[str]] = []
    for p in profiles:
        ident: set[str] = set()
        for t in getattr(p, "tags", None) or []:
            slug = getattr(t, "slug", None) or getattr(t, "name", None)
            if slug:
                ident.add(f"tag:{str(slug).lower()}")
        for t in getattr(p, "tools", None) or []:
            slug = getattr(t, "slug", None) or getattr(t, "name", None)
            if slug:
                ident.add(f"tool:{str(slug).lower()}")
        keys.append(ident)

    links: list[list[int]] = []
    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            if keys[i] & keys[j]:
                links.append([i, j])
                if len(links) >= max_links:
                    return links
    return links


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
templates.env.filters["relatieve_tijd"] = post_service.relatieve_tijd
templates.env.filters["nl_datum"] = post_service.nl_datum

# Cache-bust voor statische assets (cosmic.css): de mtime van het bestand als
# query-param. Verandert alleen als de CSS wijzigt → een nieuwe deploy serveert
# een verse URL (de oude blijft gecached, maar wordt niet meer gerefereerd).
# Voorkomt dat Cloudflare een oude cosmic.css blijft serveren ná een deploy —
# kritisch want scroll-reveal-pagina's tonen niets als de .is-in-CSS ontbreekt.
try:
    _ASSET_VER = str(int((STATIC_DIR / "cosmic.css").stat().st_mtime))
except OSError:
    _ASSET_VER = "1"
templates.env.globals["asset_ver"] = _ASSET_VER


@contextlib.asynccontextmanager
async def _lifespan(app: FastAPI):
    """De FastMCP Streamable-HTTP-sessiemanager MOET binnen de host-lifespan
    draaien (anders 'Task group is not initialized'). Importeer lazy zodat de
    app-import niet aan de mcp-dep hangt als die ontbreekt."""
    from app.mcp_server import mcp

    # Zombie-vangnet: een herstart midden in een discovery-job laat de run op
    # ``running`` staan zonder levende thread (een zombie). Veeg die verweesde
    # runs vóór we verkeer accepteren — de DB is bij app-start al gemigreerd
    # (Dockerfile-CMD ``alembic upgrade head``). Best-effort: mag de app nooit
    # ophouden of crashen.
    try:
        from app.db import SessionLocal
        from app.services import discovery_job_service

        with SessionLocal() as db:
            discovery_job_service.sweep_orphaned_runs(db)
    except Exception:  # noqa: BLE001
        logging.getLogger(__name__).warning(
            "Discovery zombie-sweep bij opstart overgeslagen", exc_info=True
        )

    # Telegram-webhook idempotent registreren als de bot-creds er zijn (anders
    # no-op). Best-effort: een mislukte registratie mag de app nooit ophouden.
    try:
        from app.services import telegram_service

        if telegram_service.configured():
            await run_in_threadpool(telegram_service.set_webhook)
    except Exception:  # noqa: BLE001
        logging.getLogger(__name__).warning(
            "Telegram-webhook registreren overgeslagen", exc_info=True
        )

    async with mcp.session_manager.run():
        yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="dewereldvan.ai", docs_url=None, redoc_url=None, lifespan=_lifespan
    )

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

    # MCP-server: "praat met dewereldvan vanuit je eigen AI-tool" (Bearer-auth,
    # eigen ingress mcp.dewereldvan.ai). Gemount op /mcp; de sessiemanager draait
    # via ``_lifespan``. Lazy import zodat de mcp-dep optioneel blijft.
    from app.mcp_server import mcp_asgi_app

    app.mount("/mcp", mcp_asgi_app())

    app.state.templates = templates

    _register_core_routes(app)
    _register_error_handlers(app)

    # Feature routers (bodies filled by FEATURES; stubs here keep imports valid).
    app.include_router(auth.router)
    app.include_router(profiles.router)
    app.include_router(admin.router)
    app.include_router(ai_profile.router)
    app.include_router(discovery.router)
    # Ledenpagina-feature (L1-L4): stubs nu, bodies door SERVICES/ROUTES+UI.
    app.include_router(members.router)
    app.include_router(projects.router)
    app.include_router(tools.router)
    app.include_router(photo.router)
    app.include_router(seo.router)
    # Ervaring-laag (E1-E4): feedback, ideeenbus, roadmap, onboarding. Stubs nu;
    # route-bodies door SERVICES/ROUTES+UI.
    app.include_router(feedback.router)
    app.include_router(ideas.router)
    app.include_router(roadmap.router)
    app.include_router(posts.router)
    app.include_router(connections.router)
    app.include_router(notifications.router)
    app.include_router(connect.router)
    app.include_router(onboarding.router)
    # Concierge-laag (Fase 1): intent-oppervlak + gegronde SSE-stroom.
    app.include_router(concierge.router)
    # Publieke voordeur (Concept A): bezoeker plakt een URL → mini-kaart, áchter
    # de kosten-gate (visitor_ai_guard). Publiek, geen auth-dep.
    app.include_router(proef.router)
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
            # Ambient ruststaat: de canvas mag NIET leeg landen. Geef de echte
            # levende graaf mee (zelfde poort-call als de voordeur) zodat het lid
            # in een ademende wereld landt i.p.v. een leeg veld — gegrond, nul AI.
            public_profiles = members_service.list_public_profiles(db)
            preview_stars = public_profiles[:8]
            return templates.TemplateResponse(
                request,
                "concierge/_canvas.html",
                {
                    "member": member,
                    "needs_profile": needs_profile,
                    "member_count": len(public_profiles),
                    "preview_stars": preview_stars,
                    "star_links": compute_graph_links(preview_stars),
                },
            )
        # De voordeur toont één echt signaal (aantal publieke makers) + een
        # constellatie-preview. Eén poort-call (zelfde eager-load als /leden),
        # daarna in-memory tellen + slicen — geen tweede query.
        public_profiles = members_service.list_public_profiles(db)
        # De hero-constellatie toont tot 8 ECHTE makers; de lijnen tonen echte
        # gedeelde grond (tag/tool). Eén poort-call, daarna in-memory — geen N+1.
        preview_stars = public_profiles[:8]
        return templates.TemplateResponse(
            request,
            "index.html",
            {
                "member_count": len(public_profiles),
                "preview_stars": preview_stars,
                "star_links": compute_graph_links(preview_stars),
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
