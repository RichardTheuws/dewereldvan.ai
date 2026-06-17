"""Development email backend: logs and writes messages to an outbox directory."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path

from app.email.base import EmailMessage, EmailSendError

logger = logging.getLogger("dewereldvan.email")


class ConsoleEmailSender:
    """Logs the message and appends it to a dev outbox.

    Writes both an appended line to ``{dir}/outbox.log`` and a per-message
    ``{dir}/{timestamp}-{to}.txt`` file for easy click-through of magic links
    during development. Raises EmailSendError only if the outbox dir is
    unwritable — never in normal operation.
    """

    def __init__(self, outbox_dir: str) -> None:
        self.outbox_dir = Path(outbox_dir)

    def send(self, message: EmailMessage) -> None:
        logger.info(
            "EMAIL → to=%s subject=%r\n%s",
            message.to,
            message.subject,
            message.text_body,
        )
        try:
            self.outbox_dir.mkdir(parents=True, exist_ok=True)
            ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
            safe_to = message.to.replace("/", "_").replace("\\", "_")
            entry = (
                f"--- {ts} ---\n"
                f"To: {message.to}\n"
                f"Subject: {message.subject}\n\n"
                f"{message.text_body}\n"
            )
            with (self.outbox_dir / "outbox.log").open("a", encoding="utf-8") as f:
                f.write(entry)
            (self.outbox_dir / f"{ts}-{safe_to}.txt").write_text(entry, encoding="utf-8")
        except OSError as exc:  # pragma: no cover - filesystem failure path
            raise EmailSendError(f"Outbox niet schrijfbaar: {exc}") from exc
