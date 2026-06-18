"""Pydantic v2 schema for admin roadmap-item CRUD (E3).

Admin-only input. ``status`` is validated against the ``RoadmapStatus`` vocabulary
(invalid/empty falls back to the default in the service); ``position`` orders items
within a ``phase``.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from app.models import RoadmapStatus


class RoadmapItemForm(BaseModel):
    """Create/update payload for a roadmap item (admin)."""

    title: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=4000)
    status: str = Field(default=RoadmapStatus.overwegen.value, max_length=9)
    phase: str = Field(default="Later", max_length=80)
    position: int = Field(default=0, ge=0)

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
        if value is None:
            return None
        value = value.strip()
        return value or None

    @field_validator("phase")
    @classmethod
    def _strip_phase(cls, value: str) -> str:
        value = (value or "").strip()
        return value or "Later"
