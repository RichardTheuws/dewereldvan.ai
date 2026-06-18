"""Shared FastAPI dependencies: session, current member, auth guards, email.

Auth model: the signed session cookie carries ``member_id``. Guards read it,
load the member, and enforce status/role. FEATURES imports these names and
never redefines them.
"""

from __future__ import annotations

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.ai import ImageGenerator, get_image_generator
from app.db import get_db
from app.email import EmailSender, get_email_sender
from app.models import Member, MemberRole, MemberStatus

SESSION_MEMBER_KEY = "member_id"


class _RedirectToLogin(HTTPException):
    """Internal signal turned into a 303 redirect by the exception handler."""

    def __init__(self) -> None:
        super().__init__(status_code=status.HTTP_303_SEE_OTHER, detail="/login")


def current_member(
    request: Request, db: Session = Depends(get_db)
) -> Member | None:
    """Return the logged-in member from the signed session, or None."""
    member_id = request.session.get(SESSION_MEMBER_KEY)
    if not member_id:
        return None
    return db.get(Member, member_id)


def require_member(
    member: Member | None = Depends(current_member),
) -> Member:
    """Require an authenticated, approved member; otherwise redirect to /login."""
    if member is None or member.status != MemberStatus.approved:
        # 303 redirect to the login page (handled in main.py exception handler).
        raise _RedirectToLogin()
    return member


def require_admin(
    member: Member = Depends(require_member),
) -> Member:
    """Require an authenticated admin member; 403 otherwise."""
    if member.role != MemberRole.admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Geen toegang"
        )
    return member


def email_sender() -> EmailSender:
    """Dependency-injected email backend (overridable in tests)."""
    return get_email_sender()


def image_generator() -> ImageGenerator:
    """Dependency-injected cover-image backend (overridable in tests)."""
    return get_image_generator()


__all__ = [
    "SESSION_MEMBER_KEY",
    "current_member",
    "require_member",
    "require_admin",
    "email_sender",
    "image_generator",
    "_RedirectToLogin",
]
