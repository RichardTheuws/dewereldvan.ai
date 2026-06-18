"""Onboarding-helper (E4b) — eerste-login-detectie → cinematische aankomst.

De ``verify``-route (auth) gebruikt ``is_first_login`` om te beslissen of een lid
naar ``/welkom`` (de gechoreografeerde "Welkom in de wereld van…"-aankomst, die
doorvloeit naar ``/profiel/ai/bouwen``) of naar de gewone ``/profiel/bewerken``
gaat.

"Eerste login" = het lid heeft nog NIETS opgebouwd: geen lopende AI-bouw-
conversatie (``AiChatTurn``) én geen ingevuld profiel (``profile.headline`` leeg).
Beide checks samen voorkomen dat een terugkerend lid dat midden in de bouwflow
zat of al een profiel heeft, opnieuw de intro-aankomst krijgt.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AiChatTurn, Member, Profile

__all__ = ["is_first_login", "first_login_redirect_path"]

# Bestemmingen (single source of truth voor de redirect-targets).
WELCOME_PATH = "/welkom"
PROFILE_EDIT_PATH = "/profiel/bewerken"
AI_BUILD_PATH = "/profiel/ai/bouwen"


def _has_turns(db: Session, member: Member) -> bool:
    """True als het lid al een (lopende) AI-bouw-conversatie heeft."""
    return (
        db.scalar(
            select(AiChatTurn.id)
            .where(AiChatTurn.member_id == member.id)
            .limit(1)
        )
        is not None
    )


def _has_built_profile(db: Session, member: Member) -> bool:
    """True als het lid een profiel met een ingevulde ``headline`` heeft.

    ``headline`` is het AI-bouw-signaal (default None tot het lid bouwt); een
    gevulde headline betekent dat het lid de bouwflow al doorlopen heeft.
    """
    headline = db.scalar(
        select(Profile.headline).where(Profile.member_id == member.id)
    )
    return bool(headline and headline.strip())


def is_first_login(db: Session, member: Member) -> bool:
    """True als dit lid nog niets opbouwde (geen turns én geen ingevuld profiel).

    Gebruikt door ``auth.verify`` om de cinematische ``/welkom``-aankomst alleen
    bij een echte eerste login te tonen.
    """
    return not _has_turns(db, member) and not _has_built_profile(db, member)


def first_login_redirect_path(db: Session, member: Member) -> str:
    """Bestemmings-pad na een geslaagde magic-link-verify.

    Eerste login → ``/welkom`` (cinematische aankomst → doorvloei naar de
    AI-bouwer); anders het gewone ``/profiel/bewerken``.
    """
    return WELCOME_PATH if is_first_login(db, member) else PROFILE_EDIT_PATH
