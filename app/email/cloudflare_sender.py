"""Production email backend: Cloudflare Email Service via httpx.

Endpoint: POST /accounts/{account_id}/email/sending/send
Vereist een API-token met de permissie **Email Sending: Edit** en een
onboarded verzenddomein (SPF/DKIM, Cloudflare DNS). Eén vendor voor DNS +
tunnel + e-mail — zie context/decisions.md.
"""

from __future__ import annotations

import httpx

from app.email.base import EmailMessage, EmailSendError

_TIMEOUT_SEC = 10.0


class CloudflareEmailSender:
    """Sends email through the Cloudflare Email Service REST API.

    No retry loop in Fase 1: a failed send raises EmailSendError, which the
    route surfaces to the user as "verzenden mislukt, probeer opnieuw".
    """

    def __init__(self, account_id: str, api_token: str, from_addr: str) -> None:
        self.endpoint = (
            "https://api.cloudflare.com/client/v4/accounts/"
            f"{account_id}/email/sending/send"
        )
        self.api_token = api_token
        self.from_addr = from_addr

    def send(self, message: EmailMessage) -> None:
        payload: dict[str, object] = {
            "from": self.from_addr,
            "to": message.to,
            "subject": message.subject,
            "text": message.text_body,
        }
        if message.html_body is not None:
            payload["html"] = message.html_body

        try:
            response = httpx.post(
                self.endpoint,
                json=payload,
                headers={"Authorization": f"Bearer {self.api_token}"},
                timeout=_TIMEOUT_SEC,
            )
        except httpx.HTTPError as exc:
            raise EmailSendError(f"Cloudflare e-mail netwerkfout: {exc}") from exc

        if response.status_code >= 300:
            raise EmailSendError(
                f"Cloudflare e-mail afgewezen (status {response.status_code}): "
                f"{response.text}"
            )
