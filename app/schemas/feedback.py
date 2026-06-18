"""Pydantic v2 schema for the feedback widget (E1).

``page_path`` is server-validated against the ``safe_url`` filter at the route
layer (only safe http(s)/relative URLs land in storage); the schema enforces the
shape (non-empty body, length caps, a small ``kind`` vocabulary). The body cap
mirrors ``settings.max_feedback_body_chars`` as a defence-in-depth default.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class FeedbackForm(BaseModel):
    """One submitted "deel je gedachte" message + its page context."""

    body: str = Field(min_length=1, max_length=4000)
    page_path: str = Field(default="/", max_length=500)
    kind: str = Field(default="algemeen", max_length=40)

    @field_validator("body")
    @classmethod
    def _strip_body(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Je gedachte mag niet leeg zijn.")
        return value

    @field_validator("page_path")
    @classmethod
    def _strip_page_path(cls, value: str) -> str:
        value = (value or "").strip()
        return value or "/"

    @field_validator("kind")
    @classmethod
    def _strip_kind(cls, value: str) -> str:
        value = (value or "").strip().lower()
        return value or "algemeen"
