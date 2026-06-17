"""Production email backend: Resend HTTP API via httpx."""

from __future__ import annotations

import httpx

from app.email.base import EmailMessage, EmailSendError

_RESEND_ENDPOINT = "https://api.resend.com/emails"
_TIMEOUT_SEC = 10.0


class ResendEmailSender:
    """Sends email through the Resend API.

    No retry loop in Fase 1: a failed send raises EmailSendError, which the
    route surfaces to the user as "verzenden mislukt, probeer opnieuw".
    """

    def __init__(self, api_key: str, from_addr: str) -> None:
        self.api_key = api_key
        self.from_addr = from_addr

    def send(self, message: EmailMessage) -> None:
        payload: dict[str, object] = {
            "from": self.from_addr,
            "to": [message.to],
            "subject": message.subject,
            "text": message.text_body,
        }
        if message.html_body is not None:
            payload["html"] = message.html_body

        try:
            response = httpx.post(
                _RESEND_ENDPOINT,
                json=payload,
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=_TIMEOUT_SEC,
            )
        except httpx.HTTPError as exc:
            raise EmailSendError(f"Resend netwerkfout: {exc}") from exc

        if response.status_code >= 300:
            raise EmailSendError(
                f"Resend afgewezen (status {response.status_code}): {response.text}"
            )
