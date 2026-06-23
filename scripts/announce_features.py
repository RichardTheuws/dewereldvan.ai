"""Eenmalige aankondigings-mail naar alle goedgekeurde leden — wat er nieuw is +
de uitnodiging om het te proberen (en ideeën in te sturen / mee te bouwen).

VEILIG: dry-run is de DEFAULT. Zonder ``--send`` verstuurt dit script NIETS — het
toont alleen de ontvangers + de tekst-body, zodat de inhoud + lijst gecontroleerd
kunnen worden. Pas met ``--send`` gaat de mail er echt uit (Cloudflare-backend op M4).

    # controleren (verstuurt niets):
    docker compose exec -T web python -m scripts.announce_features
    # echt versturen:
    docker compose exec -T web python -m scripts.announce_features --send

Per-ontvanger fail-safe: een mislukte verzending stopt de batch niet (gelogd +
doorgaan). Personaliseert de aanhef met de lid-naam.
"""

from __future__ import annotations

import argparse
import logging

from sqlalchemy import select

from app.config import settings
from app.db import SessionLocal
from app.email import EmailMessage, EmailSendError, get_email_sender
from app.email.templates import ANNOUNCEMENT_FEATURES, render_announcement
from app.models import Member, MemberStatus

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("announce_features")

SUBJECT = "Er is veel nieuw op dewereldvan.ai"

# Tokens die geen echte aanhef zijn (placeholder-namen) → neutrale aanhef.
_DENY_NAME = {"gebruiker", "onbekend", "user", "naam", "lid", "test"}


def _greeting_name(raw_name: str) -> str:
    """De voornaam voor de aanhef, of '' (→ neutrale 'Er is veel nieuw.').

    Gebruikt alleen een eerste token dat eruitziet als een échte naam (hoofdletter,
    alfabetisch, geen placeholder). Zo voorkomen we 'Er is veel nieuw, herberttenhave.'
    of '…, Gebruiker Onbekend.' — bij twijfel een nette neutrale aanhef."""
    first = (raw_name or "").strip().split()[:1]
    if not first:
        return ""
    token = first[0]
    if token[:1].isupper() and token.replace("-", "").isalpha() and token.lower() not in _DENY_NAME:
        return token
    return ""


def _urls() -> dict[str, str]:
    base = settings.base_url.rstrip("/")
    return {
        "login_url": f"{base}/login",
        "roadmap_url": f"{base}/roadmap",
        "agenda_url": f"{base}/agenda",
        "ideas_url": f"{base}/ideeen",
        "github_url": "https://github.com/RichardTheuws/dewereldvan.ai",
    }


def _text_body(name: str, urls: dict[str, str]) -> str:
    """Platte-tekst-variant (zelfde inhoud als de HTML — sommige clients tonen deze)."""
    greet = f"Er is veel nieuw, {name}." if name else "Er is veel nieuw."
    lines = [
        greet,
        "",
        "Je onderhoudt één profiel, een agent doet het werk. Dit kun je nu:",
        "",
    ]
    lines += [f"- {title} — {text}" for _icon, title, text in ANNOUNCEMENT_FEATURES]
    lines += [
        "",
        f"Log in en probeer het: {urls['login_url']}",
        "",
        "Jij bepaalt wat zichtbaar is: je profiel staat op privé tot je het zelf op",
        "openbaar zet — niemand ziet het voordat jij akkoord geeft.",
        "",
        "Heb je een idee of wil je meebouwen? Het is een open project.",
        f"- Roadmap: {urls['roadmap_url']}",
        f"- Agenda: {urls['agenda_url']}",
        f"- Opper een idee: {urls['ideas_url']}",
        f"- De code op GitHub: {urls['github_url']}",
        "",
        "— dewereldvan.ai",
    ]
    return "\n".join(lines)


def _recipients(db) -> list[Member]:
    return list(
        db.scalars(
            select(Member)
            .where(Member.status == MemberStatus.approved, Member.email.is_not(None))
            .order_by(Member.id)
        ).all()
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--send", action="store_true", help="Echt versturen (anders dry-run).")
    args = parser.parse_args()

    urls = _urls()
    with SessionLocal() as db:
        members = _recipients(db)

    logger.info("Ontvangers (goedgekeurde leden met e-mail): %s", len(members))
    for m in members:
        logger.info("  - %s <%s>", m.name, m.email)

    if not args.send:
        sample = _greeting_name(members[0].name) if members else ""
        logger.info("\n--- DRY-RUN — voorbeeld tekst-body (aanhef: '%s') ---\n%s",
                    sample or "(neutraal)", _text_body(sample, urls))
        logger.info("\nDRY-RUN: er is NIETS verstuurd. Draai met --send om te versturen.")
        return 0

    sender = get_email_sender()
    sent = failed = 0
    for m in members:
        greet = _greeting_name(m.name)
        msg = EmailMessage(
            to=m.email,
            subject=SUBJECT,
            text_body=_text_body(greet, urls),
            html_body=render_announcement(greet, **urls),
        )
        try:
            sender.send(msg)
            sent += 1
        except EmailSendError:
            failed += 1
            logger.warning("Verzending faalde voor %s; doorgaan.", m.email, exc_info=True)
    logger.info("Klaar: %s verstuurd, %s mislukt.", sent, failed)
    return 0


if __name__ == "__main__":  # pragma: no cover
    main()
