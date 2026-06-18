"""Pydantic v2 schema for submitting an idea (E2)."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class IdeaForm(BaseModel):
    """Member-submitted idea: a title and a body."""

    title: str = Field(min_length=1, max_length=160)
    body: str = Field(min_length=1, max_length=4000)

    @field_validator("title")
    @classmethod
    def _strip_title(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Titel mag niet leeg zijn.")
        return value

    @field_validator("body")
    @classmethod
    def _strip_body(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Beschrijving mag niet leeg zijn.")
        return value
