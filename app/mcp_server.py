"""dewereldvan MCP-server — "praat met dewereldvan.ai vanuit je eigen AI-tool".

Een FastMCP Streamable-HTTP-server, **stateless** (elke call staat op zichzelf →
de Bearer-auth per request klopt en de contextvar propageert naar de tool), gemount
op ``/mcp`` in de bestaande web-container. Dunne laag over de bestaande services.

AUTH: een ASGI-middleware leest ``Authorization: Bearer dwv_…``, resolvet het lid
(``token_service.resolve``, eigen sessie) en zet ``member_id`` in een contextvar;
zonder geldig token → 401. Elke tool leest die contextvar en opent z'n eigen
``SessionLocal`` (de drain-thread mag de request-sessie niet delen). Een token =
"act as dit approved lid"; nooit role-escalatie.

Lifespan: ``mcp.session_manager.run()`` MOET in de host-lifespan draaien (anders
"Task group is not initialized"); zie ``app.main``.
"""

from __future__ import annotations

import contextvars
import logging

from mcp.server.fastmcp import FastMCP

from app.config import settings
from app.db import SessionLocal
from app.email import EmailMessage, EmailSendError, get_email_sender
from app.email import templates as email_templates
from app.models import Member
from app.services import (
    connection_service,
    match_service,
    members_service,
    profile_service,
    token_service,
)

logger = logging.getLogger(__name__)

# Het geauthenticeerde lid-id voor de duur van één request (door de auth-
# middleware gezet; door de tools gelezen).
_member_id: contextvars.ContextVar[int | None] = contextvars.ContextVar(
    "mcp_member_id", default=None
)

mcp = FastMCP("dewereldvan", stateless_http=True, json_response=True)
mcp.settings.streamable_http_path = "/"  # gemount op /mcp → serveer op de root


def _me(db) -> Member | None:
    mid = _member_id.get()
    return db.get(Member, mid) if mid is not None else None


# --------------------------------------------------------------------------- #
# Tools — alle gescoped tot het geauthenticeerde lid                          #
# --------------------------------------------------------------------------- #


@mcp.tool()
def wie_ben_ik() -> dict:
    """Toon het profiel van het ingelogde lid: kopregel, bio, wat ik maak,
    projecten, zoekvragen, tags, compleetheid en zichtbaarheid."""
    with SessionLocal() as db:
        member = _me(db)
        if member is None:
            return {"fout": "niet ingelogd"}
        p = profile_service.get_or_create_profile(db, member)
        db.commit()
        return {
            "naam": p.display_name,
            "kopregel": p.headline or "",
            "bio": p.bio or "",
            "wat_ik_maak": p.makes_summary or "",
            "projecten": [o.title for o in p.offerings],
            "zoekvragen": [n.title for n in p.needs],
            "tags": [t.name for t in p.tags],
            "compleetheid": p.completeness,
            "zichtbaarheid": p.visibility.value,
        }


@mcp.tool()
def werk_profiel_bij(
    kopregel: str | None = None,
    bio: str | None = None,
    wat_ik_maak: str | None = None,
    tags: str | None = None,
) -> dict:
    """Werk je profiel bij. Alleen meegegeven velden wijzigen. ``tags`` is een
    komma-gescheiden lijst. Publiceren/zichtbaarheid blijft ongemoeid."""
    with SessionLocal() as db:
        member = _me(db)
        if member is None:
            return {"fout": "niet ingelogd"}
        p = profile_service.get_or_create_profile(db, member)
        if kopregel is not None:
            p.headline = kopregel.strip()[:200]
        profile_service.update_profile(
            db, p,
            display_name=p.display_name,
            bio=bio if bio is not None else p.bio,
            makes_summary=wat_ik_maak if wat_ik_maak is not None else p.makes_summary,
            raw_tags=tags if tags is not None else ", ".join(t.name for t in p.tags),
        )
        db.commit()
        return {"ok": True, "compleetheid": p.completeness}


@mcp.tool()
def voeg_project_toe(titel: str, omschrijving: str | None = None, url: str | None = None) -> dict:
    """Voeg een project toe ('wat ik maak'). Optioneel een omschrijving en link."""
    with SessionLocal() as db:
        member = _me(db)
        if member is None:
            return {"fout": "niet ingelogd"}
        p = profile_service.get_or_create_profile(db, member)
        off = profile_service.add_offering(db, p, title=titel.strip()[:160],
                                           description=(omschrijving or None))
        if url:
            off.url = url.strip()[:1000]
        db.commit()
        return {"ok": True, "project": off.title, "compleetheid": p.completeness}


@mcp.tool()
def voeg_zoekvraag_toe(titel: str, omschrijving: str | None = None) -> dict:
    """Voeg een 'waar ik naar zoek' toe — dit voedt de matchmaking."""
    with SessionLocal() as db:
        member = _me(db)
        if member is None:
            return {"fout": "niet ingelogd"}
        p = profile_service.get_or_create_profile(db, member)
        profile_service.add_need(db, p, title=titel.strip()[:160],
                                 description=(omschrijving or None))
        db.commit()
        return {"ok": True, "compleetheid": p.completeness}


@mcp.tool()
def zoek_makers(zoekterm: str) -> list[dict]:
    """Doorzoek de ledengids op een term (tag, wat iemand maakt of zoekt)."""
    with SessionLocal() as db:
        profiles = members_service.list_public_profiles(db, maakt=zoekterm)
        return [
            {
                "naam": p.display_name,
                "slug": p.slug,
                "kopregel": p.headline or "",
                "tags": [t.name for t in p.tags],
            }
            for p in profiles[:20]
        ]


@mcp.tool()
def mijn_matches() -> list[dict]:
    """Je vraag↔aanbod-koppelingen: wat past bij wat jij zoekt / wie zoekt wat
    jij maakt, met een korte reden."""
    with SessionLocal() as db:
        member = _me(db)
        if member is None:
            return [{"fout": "niet ingelogd"}]
        out = []
        for m in match_service.list_for_member(db, member):
            seeker = m.seeker_member_id == member.id
            out.append({
                "perspectief": "jij zoekt dit" if seeker else "iemand zoekt wat jij maakt",
                "project": m.offering.title,
                "maker": m.offering.profile.display_name,
                "maker_slug": m.offering.profile.slug,
                "vraag": m.need.title,
                "score": m.score,
                "waarom": m.rationale,
            })
        return out


@mcp.tool()
def stel_voor(maker_slug: str, bericht: str) -> dict:
    """Stuur een intro aan een maker (op slug). Hij/zij krijgt een notificatie en
    beslist; contactgegevens worden pas ná wederzijds akkoord gedeeld."""
    with SessionLocal() as db:
        member = _me(db)
        if member is None:
            return {"fout": "niet ingelogd"}
        from app.models import MemberStatus, Profile
        from sqlalchemy import select

        to_member = db.scalar(
            select(Member).join(Profile, Profile.member_id == Member.id).where(
                Profile.slug == maker_slug, Member.status == MemberStatus.approved
            )
        )
        if to_member is None or to_member.id == member.id:
            return {"fout": "die maker kon ik niet vinden"}
        try:
            connection_service.check_intro_rate_limit(db, member)
        except connection_service.IntroRateLimited:
            return {"fout": "je stuurde net al een paar intro's — geef het even tijd"}
        connection_service.create_intro(db, from_member=member, to_member=to_member,
                                       message=bericht)
        db.commit()
        login_url = f"{settings.base_url.rstrip('/')}/login"
        try:
            get_email_sender().send(EmailMessage(
                to=to_member.email,
                subject=f"{member.name} wil kennismaken — dewereldvan.ai",
                text_body=f"Hoi {to_member.name},\n\n{member.name} wil kennismaken:\n\n{bericht}\n\nLog in: {login_url}\n",
                html_body=email_templates.render_intro(to_member.name, member.name, bericht, login_url),
            ))
        except EmailSendError:
            logger.warning("Intro-mail faalde (MCP) voor %s", to_member.id)
        return {"ok": True, "naar": to_member.name}


@mcp.tool()
def hoe_werkt_dewereldvan() -> str:
    """Korte uitleg over dewereldvan.ai voor je eigen agent."""
    return (
        "dewereldvan.ai is een besloten community van AI-makers in NL/BE. Maak een "
        "profiel (wie je bent, wat je maakt, waar je naar zoekt); het platform brengt "
        "vraag en aanbod bij elkaar en je kunt makers een intro sturen. Via deze "
        "MCP-server doe je dat allemaal vanuit je eigen tool."
    )


@mcp.tool()
def bouw_profiel_uit_link(url: str) -> dict:
    """Laat de AI je profiel optrekken uit een link (je site, GitHub, LinkedIn).
    Dit kan even duren (de AI haalt de pagina op en vat 'm samen). Overschrijft je
    profieltekst met een concept; zichtbaarheid blijft ongewijzigd."""
    if not settings.ai_enrich_enabled:
        return {"fout": "AI-profielbouw staat uit"}
    from app.services import ai_profile as ai

    with SessionLocal() as db:
        member = _me(db)
        if member is None:
            return {"fout": "niet ingelogd"}
        p = profile_service.get_or_create_profile(db, member)
        messages = [{"role": "user", "content": f"Bouw mijn profiel uit deze link: {url}"}]
        try:
            final = ai.stream_turn(messages, lambda _t: None)
            messages.append({"role": "assistant", "content": final.content})
            draft = ai.finalize_draft(messages)
            profile_service.persist_draft(db, p, draft, source_messages=messages)
            db.commit()
        except Exception:  # noqa: BLE001 — best-effort; nooit de tool laten crashen
            logger.exception("bouw_profiel_uit_link faalde voor member %s", member.id)
            return {"fout": "het bouwen lukte niet — probeer het later of via de site"}
        return {"ok": True, "kopregel": p.headline or "", "compleetheid": p.completeness}


# --------------------------------------------------------------------------- #
# ASGI: Bearer-auth-middleware rond de Streamable-HTTP-app                     #
# --------------------------------------------------------------------------- #


class _BearerAuth:
    """Authenticeert élke request met een persoonlijk Bearer-token en zet het lid
    in de contextvar. Geen/ongeldig token → 401 (geen MCP-handshake zonder auth)."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = dict(scope.get("headers") or [])
        auth = headers.get(b"authorization", b"").decode()
        raw = auth[7:].strip() if auth[:7].lower() == "bearer " else ""
        member_id = None
        if raw:
            with SessionLocal() as db:
                member = token_service.resolve(db, raw)
                if member is not None:
                    member_id = member.id
                    db.commit()  # last_used_at
        if member_id is None:
            await send({"type": "http.response.start", "status": 401,
                        "headers": [(b"content-type", b"application/json")]})
            await send({"type": "http.response.body",
                        "body": '{"error":"unauthorized - geef een geldig dwv_-token mee"}'.encode()})
            return
        tok = _member_id.set(member_id)
        try:
            await self.app(scope, receive, send)
        finally:
            _member_id.reset(tok)


def mcp_asgi_app():
    """De gemounte ASGI-app: auth-middleware rond de Streamable-HTTP-app."""
    return _BearerAuth(mcp.streamable_http_app())
