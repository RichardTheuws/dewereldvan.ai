"""Email package — backend selection by the EMAIL_BACKEND setting.

The provider is NOT hard-committed: selection is purely env-driven.
"""

from __future__ import annotations

from app.config import settings
from app.email.base import EmailMessage, EmailSender, EmailSendError
from app.email.cloudflare_sender import CloudflareEmailSender
from app.email.console import ConsoleEmailSender
from app.email.resend_sender import ResendEmailSender

__all__ = [
    "EmailMessage",
    "EmailSender",
    "EmailSendError",
    "ConsoleEmailSender",
    "ResendEmailSender",
    "CloudflareEmailSender",
    "get_email_sender",
]


def get_email_sender() -> EmailSender:
    """Return the configured EmailSender backend."""
    if settings.email_backend == "cloudflare":
        if not (settings.cloudflare_account_id and settings.cloudflare_api_token):
            raise RuntimeError(
                "EMAIL_BACKEND=cloudflare but CLOUDFLARE_ACCOUNT_ID/"
                "CLOUDFLARE_API_TOKEN is empty"
            )
        return CloudflareEmailSender(
            settings.cloudflare_account_id,
            settings.cloudflare_api_token,
            settings.email_from,
        )
    if settings.email_backend == "resend":
        if not settings.resend_api_key:
            raise RuntimeError("EMAIL_BACKEND=resend but RESEND_API_KEY is empty")
        return ResendEmailSender(settings.resend_api_key, settings.email_from)
    return ConsoleEmailSender(settings.console_email_dir)
