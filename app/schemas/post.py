"""Pydantic v2 schemas voor het plaatsen van een community-bijdrage (Post).

Twee vormen op één entiteit:
- ``EventForm``  — een agenda-event (titel + frequentie verplicht; datum/locatie/
  link/cadans optioneel).
- ``NewsForm``   — een nieuwsartikel (titel + link verplicht; bron/rol/datum
  optioneel).

De router parst rauwe ``Form``-velden naar deze schemas; de service schrijft.
URL-validatie is licht (http/https) zodat een lid niet struikelt over een schema.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.models.base import EventCategory, EventFrequency, NewsRole


def _clean(value: str | None) -> str | None:
    """Strip en map lege string → ``None`` (optionele tekstvelden)."""
    if value is None:
        return None
    value = value.strip()
    return value or None


def _check_url(value: str | None) -> str | None:
    """Licht: accepteer alleen http(s)-URL's; leeg → ``None``."""
    value = _clean(value)
    if value is None:
        return None
    if not (value.startswith("http://") or value.startswith("https://")):
        raise ValueError("Een link begint met http:// of https://.")
    return value[:500]


class EventForm(BaseModel):
    """Lid-toegevoegd agenda-event."""

    title: str = Field(min_length=1, max_length=200)
    frequency: EventFrequency
    category: EventCategory = EventCategory.meetup
    description: str | None = Field(default=None, max_length=4000)
    url: str | None = Field(default=None)
    location: str | None = Field(default=None, max_length=160)
    cadence_note: str | None = Field(default=None, max_length=120)
    next_at: datetime | None = None

    @field_validator("title")
    @classmethod
    def _strip_title(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Geef het event een titel.")
        return value

    @field_validator("description", "location", "cadence_note")
    @classmethod
    def _strip_optional(cls, value: str | None) -> str | None:
        return _clean(value)

    @field_validator("url")
    @classmethod
    def _validate_url(cls, value: str | None) -> str | None:
        return _check_url(value)


class NewsForm(BaseModel):
    """Lid-toegevoegd nieuwsartikel (titel + link verplicht)."""

    title: str = Field(min_length=1, max_length=200)
    url: str
    role: NewsRole = NewsRole.gedeeld
    source: str | None = Field(default=None, max_length=160)
    description: str | None = Field(default=None, max_length=4000)
    published_at: datetime | None = None

    @field_validator("title")
    @classmethod
    def _strip_title(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Geef het artikel een titel.")
        return value

    @field_validator("description", "source")
    @classmethod
    def _strip_optional(cls, value: str | None) -> str | None:
        return _clean(value)

    @field_validator("url")
    @classmethod
    def _validate_url(cls, value: str) -> str:
        cleaned = _check_url(value)
        if cleaned is None:
            raise ValueError("Een nieuwsartikel heeft een link nodig.")
        return cleaned
