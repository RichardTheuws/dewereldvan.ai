"""Pydantic v2 schemas for profile editing (profile, offerings, needs)."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from app.models import Visibility


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


class ProfileForm(BaseModel):
    """Profile fields a member edits themselves."""

    display_name: str = Field(min_length=1, max_length=120)
    bio: str | None = Field(default=None, max_length=4000)
    makes_summary: str | None = Field(default=None, max_length=4000)
    # Comma-separated tag string from the form; parsed in the service layer.
    tags: str | None = Field(default=None, max_length=1000)
    # "Waar ik voor opensta" — checkbox-slugs uit het form; gevalideerd/genormaliseerd
    # tegen de catalogus in de service-laag (max 12 = veilige bovengrens, catalogus < 12).
    open_to: list[str] = Field(default_factory=list, max_length=12)

    @field_validator("display_name")
    @classmethod
    def _strip_display_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Naam mag niet leeg zijn.")
        return value

    @field_validator("bio", "makes_summary", "tags")
    @classmethod
    def _strip_optional(cls, value: str | None) -> str | None:
        return _clean(value)


class OfferingForm(BaseModel):
    """A single "wat ik maak" entry."""

    title: str = Field(min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=4000)

    @field_validator("title")
    @classmethod
    def _strip_title(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Titel mag niet leeg zijn.")
        return value

    @field_validator("description")
    @classmethod
    def _strip_description(cls, value: str | None) -> str | None:
        return _clean(value)


class NeedForm(BaseModel):
    """A single "waar ik naar zoek" entry."""

    title: str = Field(min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=4000)

    @field_validator("title")
    @classmethod
    def _strip_title(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Titel mag niet leeg zijn.")
        return value

    @field_validator("description")
    @classmethod
    def _strip_description(cls, value: str | None) -> str | None:
        return _clean(value)


class VisibilityForm(BaseModel):
    """Visibility toggle input.

    ``consent`` is the explicit AVG opt-in required to go public; it is
    enforced server-side in the visibility service, not just in the form.
    """

    visibility: Visibility
    consent: bool = False
