"""Pydantic v2 schemas for AI-native profielbouw (F1-F3).

Twee soorten modellen:
- **Form-input** (``ChatMessageForm``, ``AcceptForm``): wat het lid via htmx-posts
  instuurt tijdens de bouw-flow.
- **Structured-output** (``DraftRole``, ``DraftProject``, ``DraftProfileOut``):
  de Pydantic-spiegel van het Anthropic ``PROFILE_SCHEMA`` (zie
  ``app/services/ai_profile.py``). Velden zijn verplicht in het schema maar mogen
  ``""`` zijn; de service-guard zet lege strings om naar ``None``.

Let op: voor Anthropic structured-output gelden schema-restricties (alle objecten
``additionalProperties: false``, geen string/numeric constraints). Houd deze
modellen daarom plat — geen ``min_length``/``max_length`` op de output-modellen.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


# --- Form-input (htmx posts) ---


class ChatMessageForm(BaseModel):
    """Eén lid-bericht in de bouw-chat."""

    message: str = Field(min_length=1, max_length=8000)

    @field_validator("message")
    @classmethod
    def _strip_message(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Bericht mag niet leeg zijn.")
        return value


class AcceptForm(BaseModel):
    """Bevestiging van het lid om de draft te publiceren.

    ``consent`` is de expliciete AVG-opt-in (hergebruikt uit de bestaande
    zichtbaarheidsflow); server-side afgedwongen, niet alleen in de form.
    """

    consent: bool = False


# --- Structured-output spiegel (Anthropic PROFILE_SCHEMA) ---


class DraftRole(BaseModel):
    model_config = {"extra": "forbid"}

    label: str = ""
    url: str = ""
    description: str = ""
    image_url: str = ""


class DraftProject(BaseModel):
    model_config = {"extra": "forbid"}

    name: str = ""
    url: str = ""
    description: str = ""
    image_url: str = ""


class DraftProfileOut(BaseModel):
    """Het profiel-JSON dat de afsluitende structured-output-call oplevert."""

    model_config = {"extra": "forbid"}

    headline: str = ""
    bio: str = ""
    roles: list[DraftRole] = Field(default_factory=list)
    projects: list[DraftProject] = Field(default_factory=list)
    seeking: str = ""
    tags: list[str] = Field(default_factory=list)
