"""Email abstraction: ConsoleEmailSender outbox, factory selection, failure surfacing."""

from __future__ import annotations

from pathlib import Path

import pytest
from app.config import settings
from app.email import get_email_sender
from app.email.base import EmailMessage, EmailSendError
from app.email.cloudflare_sender import CloudflareEmailSender
from app.email.console import ConsoleEmailSender
from app.email.resend_sender import ResendEmailSender


def _msg() -> EmailMessage:
    return EmailMessage(
        to="lid@example.com",
        subject="Je inloglink voor dewereldvan.ai",
        text_body="Klik om in te loggen: https://dewereldvan.ai/auth/verify?token=ABC123",
    )


def test_console_sender_writes_outbox_with_link(tmp_path):
    sender = ConsoleEmailSender(str(tmp_path))
    sender.send(_msg())

    log = (tmp_path / "outbox.log").read_text(encoding="utf-8")
    assert "lid@example.com" in log
    assert "token=ABC123" in log  # the magic-link is present for dev click-through

    # A per-message file was also written.
    txt_files = list(Path(tmp_path).glob("*-lid@example.com.txt"))
    assert len(txt_files) == 1
    assert "token=ABC123" in txt_files[0].read_text(encoding="utf-8")


def test_factory_returns_console_by_default():
    # conftest sets EMAIL_BACKEND=console.
    assert settings.email_backend == "console"
    assert isinstance(get_email_sender(), ConsoleEmailSender)


def test_factory_resend_without_key_raises(monkeypatch):
    monkeypatch.setattr(settings, "email_backend", "resend")
    monkeypatch.setattr(settings, "resend_api_key", None)
    with pytest.raises(RuntimeError):
        get_email_sender()


def test_factory_resend_with_key_returns_resend(monkeypatch):
    monkeypatch.setattr(settings, "email_backend", "resend")
    monkeypatch.setattr(settings, "resend_api_key", "re_test_key")
    sender = get_email_sender()
    assert isinstance(sender, ResendEmailSender)  # type only — no network call


def test_resend_non_2xx_raises_email_send_error(monkeypatch):
    """Non-2xx Resend response surfaces as EmailSendError (no silent fail)."""

    class _FakeResponse:
        status_code = 422
        text = '{"message":"invalid from"}'

    def _fake_post(*args, **kwargs):
        return _FakeResponse()

    import app.email.resend_sender as rs

    monkeypatch.setattr(rs.httpx, "post", _fake_post)
    sender = ResendEmailSender("re_test_key", "noreply@dewereldvan.ai")
    with pytest.raises(EmailSendError):
        sender.send(_msg())


def test_resend_network_error_raises_email_send_error(monkeypatch):
    import app.email.resend_sender as rs

    def _boom(*args, **kwargs):
        raise rs.httpx.ConnectError("geen verbinding")

    monkeypatch.setattr(rs.httpx, "post", _boom)
    sender = ResendEmailSender("re_test_key", "noreply@dewereldvan.ai")
    with pytest.raises(EmailSendError):
        sender.send(_msg())


def test_fake_email_sender_records_and_can_fail(fake_email):
    """The in-memory fixture records sends and can simulate a delivery failure."""
    fake_email.send(_msg())
    assert len(fake_email.sent) == 1
    assert fake_email.sent[0].to == "lid@example.com"

    fake_email.fail = True
    with pytest.raises(EmailSendError):
        fake_email.send(_msg())


def test_factory_cloudflare_without_creds_raises(monkeypatch):
    monkeypatch.setattr(settings, "email_backend", "cloudflare")
    monkeypatch.setattr(settings, "cloudflare_account_id", None)
    monkeypatch.setattr(settings, "cloudflare_api_token", None)
    with pytest.raises(RuntimeError):
        get_email_sender()


def test_factory_cloudflare_with_creds_returns_cloudflare(monkeypatch):
    monkeypatch.setattr(settings, "email_backend", "cloudflare")
    monkeypatch.setattr(settings, "cloudflare_account_id", "acct123")
    monkeypatch.setattr(settings, "cloudflare_api_token", "cf_test_token")
    sender = get_email_sender()
    assert isinstance(sender, CloudflareEmailSender)  # type only — no network call


def test_cloudflare_non_2xx_raises_email_send_error(monkeypatch):
    """Non-2xx Cloudflare response surfaces as EmailSendError (no silent fail)."""

    class _FakeResponse:
        status_code = 403
        text = '{"errors":[{"message":"Unable to authenticate request"}]}'

    import app.email.cloudflare_sender as cf

    monkeypatch.setattr(cf.httpx, "post", lambda *a, **k: _FakeResponse())
    sender = CloudflareEmailSender("acct123", "cf_test_token", "noreply@dewereldvan.ai")
    with pytest.raises(EmailSendError):
        sender.send(_msg())


def test_cloudflare_network_error_raises_email_send_error(monkeypatch):
    import app.email.cloudflare_sender as cf

    def _boom(*args, **kwargs):
        raise cf.httpx.ConnectError("geen verbinding")

    monkeypatch.setattr(cf.httpx, "post", _boom)
    sender = CloudflareEmailSender("acct123", "cf_test_token", "noreply@dewereldvan.ai")
    with pytest.raises(EmailSendError):
        sender.send(_msg())
