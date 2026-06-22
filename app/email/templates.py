"""Kosmische HTML-mail render-helpers (E4a).

Vult ``EmailMessage.html_body`` voor de mails die een lid of admin ziet, achter de
bestaande ``EmailSender``. Rendert standalone via een losse Jinja-``Environment``
op ``app/templates/emails/`` — géén ``Request``/route nodig (mails worden ook
buiten een request-context verstuurd).

VEILIGHEID:
- ``autoescape`` staat aan: lid-namen / vrije tekst worden geëscaped (geen
  HTML-injectie in de mail).
- De ``verify_url`` / ``login_url`` worden NIET hier gebouwd — die komen
  kant-en-klaar uit ``auth.py`` (de bestaande veilige weg via ``settings.base_url``);
  deze helper zet ze alleen in een knop-``href``. Géén tokens loggen, géén secrets
  in de mail buiten de magic-link-URL zelf.

ROBUUSTHEID:
- Ontbreekt een child-template (bv. nog niet uitgerold), dan valt de render terug
  op een minimale, nog steeds nette inline-HTML i.p.v. een ``TemplateNotFound`` —
  een mail mag nooit op een ontbrekende sjabloon stranden (de ``text_body``-
  fallback blijft sowieso intact in ``auth.py``).
"""

from __future__ import annotations

import logging
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, TemplateError, select_autoescape
from markupsafe import escape

logger = logging.getLogger(__name__)

EMAILS_DIR = Path(__file__).resolve().parent.parent / "templates" / "emails"

_env = Environment(
    loader=FileSystemLoader(str(EMAILS_DIR)),
    autoescape=select_autoescape(["html", "xml"]),
)

__all__ = [
    "render_magic_link",
    "render_admin_notify",
    "render_approval",
    "render_invite",
    "render_intro",
]


def _render(template_name: str, fallback: str, /, **ctx: object) -> str:
    """Render ``template_name`` met ``ctx``; val terug op ``fallback`` bij elke fout.

    Een ontbrekende of stukke sjabloon mag de mail-verzending nooit breken: dan
    sturen we een minimale inline-HTML (``fallback``) die alsnog de kosmische
    identiteit benadert.
    """
    try:
        return _env.get_template(template_name).render(**ctx)
    except TemplateError as exc:
        logger.warning(
            "E-mail-template %s renderde niet (%s); inline fallback gebruikt.",
            template_name,
            exc,
        )
        return fallback


def _inline_shell(heading: str, body_html: str, cta: str = "") -> str:
    """Minimale kosmische inline-HTML-shell als laatste vangnet (zie ``_render``)."""
    return (
        '<!DOCTYPE html><html lang="nl"><body '
        'style="margin:0;padding:0;background-color:#04040e;">'
        '<table width="100%" cellpadding="0" cellspacing="0" border="0" '
        'bgcolor="#0a0a24" style="background-color:#04040e;"><tr>'
        '<td align="center" style="padding:40px 16px;">'
        '<table width="560" cellpadding="0" cellspacing="0" border="0" '
        'style="width:560px;max-width:100%;"><tr>'
        '<td style="background-color:#0c0c2a;border:1px solid rgba(255,255,255,0.09);'
        'border-radius:16px;padding:32px;">'
        f'<h1 style="margin:0 0 14px 0;font-family:Fraunces,Georgia,serif;'
        f'font-weight:400;font-size:26px;color:#eef0ff;">{heading}</h1>'
        f'<div style="font-family:Helvetica,Arial,sans-serif;font-size:16px;'
        f'line-height:1.6;color:#c6c9e6;">{body_html}</div>{cta}'
        '</td></tr></table></td></tr></table></body></html>'
    )


def _inline_button(label: str, url: str) -> str:
    """Een gouden pill-CTA voor de inline fallback (url al veilig uit auth.py)."""
    safe_url = escape(url)
    return (
        '<table role="presentation" cellpadding="0" cellspacing="0" border="0" '
        'style="margin:24px 0 4px 0;"><tr><td bgcolor="#f6cd86" '
        'style="border-radius:999px;">'
        f'<a href="{safe_url}" style="display:inline-block;padding:13px 28px;'
        'font-family:Helvetica,Arial,sans-serif;font-size:15px;font-weight:600;'
        f'color:#1a1330;text-decoration:none;border-radius:999px;">{escape(label)}</a>'
        '</td></tr></table>'
    )


def render_magic_link(name: str, verify_url: str, ttl_min: int) -> str:
    """HTML-body voor de magic-link-inlogmail.

    ``verify_url`` komt kant-en-klaar uit ``auth.login_submit`` (de bestaande
    veilige weg via ``settings.base_url``); hier alleen in een knop-href gezet.
    """
    fallback = _inline_shell(
        heading=f"Hoi {escape(name)},",
        body_html=(
            "<p style='margin:0 0 12px 0;'>Klik op de knop om in te loggen. "
            f"De link is {int(ttl_min)} minuten geldig en kan één keer gebruikt "
            "worden.</p>"
            "<p style='margin:0;'>Heb je dit niet aangevraagd? Dan kun je deze "
            "e-mail negeren.</p>"
        ),
        cta=_inline_button("Inloggen", verify_url),
    )
    return _render(
        "magic_link.html",
        fallback,
        name=name,
        verify_url=verify_url,
        ttl_min=ttl_min,
    )


def render_admin_notify(name: str, email: str, queue_url: str) -> str:
    """HTML-body voor de admin-notificatie van een nieuwe aanmelding."""
    fallback = _inline_shell(
        heading="Nieuwe aanmelding",
        body_html=(
            "<p style='margin:0 0 12px 0;'>Er wacht een nieuwe aanmelding op "
            "goedkeuring:</p>"
            f"<p style='margin:0;'><strong>{escape(name)}</strong><br>"
            f"{escape(email)}</p>"
        ),
        cta=_inline_button("Naar de queue", queue_url),
    )
    return _render(
        "admin_notify.html",
        fallback,
        name=name,
        email=email,
        queue_url=queue_url,
    )


def render_invite(name: str, invite_url: str) -> str:
    """HTML-body voor de groep-invite-mail (de eerste indruk voor genodigden).

    ``invite_url`` komt kant-en-klaar uit het verzendpad (``settings.base_url`` +
    het actieve invite-token); hier alleen in een knop-href gezet.
    """
    fallback = _inline_shell(
        heading=f"Hoi {escape(name)},",
        body_html=(
            "<p style='margin:0 0 12px 0;'>Je bent uitgenodigd voor de besloten "
            "preview van dewereldvan.ai — de plek voor wie in NL &amp; BE serieus "
            "met AI bouwt. Maak nu je eigen profiel; onze AI bouwt het met je mee.</p>"
            "<p style='margin:0;'>Je houdt altijd de regie: je kunt je profiel met "
            "één klik volledig wissen, wanneer je maar wilt.</p>"
        ),
        cta=_inline_button("Maak je profiel", invite_url),
    )
    return _render("invite.html", fallback, name=name, invite_url=invite_url)


def render_approval(name: str, login_url: str) -> str:
    """HTML-body voor de goedkeurings-mail (lid is zojuist goedgekeurd)."""
    fallback = _inline_shell(
        heading=f"Welkom, {escape(name)}!",
        body_html=(
            "<p style='margin:0 0 12px 0;'>Je bent erbij — een netwerk van AI-makers "
            "uit alle disciplines. Log in en bouw je plek in de wereld op.</p>"
        ),
        cta=_inline_button("Inloggen", login_url),
    )
    return _render(
        "approval.html",
        fallback,
        name=name,
        login_url=login_url,
    )


def render_intro(to_name: str, from_name: str, message: str, login_url: str) -> str:
    """HTML-body voor de intro-notificatie (Tier 1 Fase 2).

    ``message`` is de door de afzender bevestigde intro-tekst; geëscaped (geen
    HTML-injectie). Géén contactgegevens in de mail — die komen pas ná akkoord.
    """
    fallback = _inline_shell(
        heading=f"Hoi {escape(to_name)},",
        body_html=(
            f"<p style='margin:0 0 12px 0;'>{escape(from_name)} wil graag met je "
            "kennismaken via dewereldvan.ai:</p>"
            f"<p style='margin:0 0 12px 0; padding-left:12px; border-left:2px solid "
            f"#6d5dfc; color:#444;'>{escape(message)}</p>"
            "<p style='margin:0;'>Log in om te reageren — accepteren of niet, jij "
            "beslist.</p>"
        ),
        cta=_inline_button("Bekijk de intro", login_url),
    )
    return _render(
        "intro.html",
        fallback,
        to_name=to_name,
        from_name=from_name,
        message=message,
        login_url=login_url,
    )
