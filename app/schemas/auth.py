"""Pydantic v2 schemas for the auth flows (registration + magic-link request).

E-mail is validated with a pragmatic regex rather than pydantic ``EmailStr`` so
FEATURES adds no new dependency (``email-validator`` is not in requirements).
"""

from __future__ import annotations

import re

from pydantic import BaseModel, Field, field_validator

# Pragmatic e-mail shape check: local@domain.tld. Not RFC-exhaustive, but
# enough to reject obvious garbage before we mail a magic link.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _normalize_email(value: str) -> str:
    value = value.strip().lower()
    if not _EMAIL_RE.match(value):
        raise ValueError("Vul een geldig e-mailadres in.")
    return value


class RegisterForm(BaseModel):
    """Open-registration input: a name and an e-mail address."""

    name: str = Field(min_length=1, max_length=120)
    email: str = Field(max_length=320)

    @field_validator("name")
    @classmethod
    def _strip_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Naam mag niet leeg zijn.")
        return value

    @field_validator("email")
    @classmethod
    def _check_email(cls, value: str) -> str:
        # Store/lookup case-folded so duplicate detection is case-insensitive.
        return _normalize_email(value)


class MagicLinkRequest(BaseModel):
    """Magic-link request input: just the e-mail address."""

    email: str = Field(max_length=320)

    @field_validator("email")
    @classmethod
    def _check_email(cls, value: str) -> str:
        return _normalize_email(value)
