"""EmailSender interface, message dataclass, and the delivery-failure error."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class EmailMessage:
    to: str
    subject: str
    text_body: str
    html_body: str | None = None


class EmailSendError(RuntimeError):
    """Raised when delivery fails. Callers MUST surface this — never silent-fail."""


class EmailSender(Protocol):
    def send(self, message: EmailMessage) -> None:
        """Deliver the message. Raises EmailSendError on failure."""
        ...
