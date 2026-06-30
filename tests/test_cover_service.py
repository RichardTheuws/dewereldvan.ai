"""cover_service — trusted-URL-validatie + rate-limit (hero-studio)."""

from __future__ import annotations

import pytest
from app.services import cover_service


@pytest.mark.parametrize(
    "url",
    [
        "https://v3b.fal.media/files/b/abc/x.png",
        "https://fal.media/files/x.png",
        "https://queue.fal.run/result/x.png",
        "https://cdn.fal.ai/x.png",
    ],
)
def test_trusted_urls_accepted(url):
    assert cover_service.is_trusted_cover_url(url) is True


@pytest.mark.parametrize(
    "url",
    [
        None,
        "",
        "http://v3b.fal.media/x.png",  # geen https
        "https://evil.example.com/x.png",  # vreemde host
        "https://fal.media.evil.com/x.png",  # suffix-spoof
        "javascript:alert(1)",
        "ftp://fal.media/x.png",
        "not a url",
    ],
)
def test_untrusted_urls_rejected(url):
    assert cover_service.is_trusted_cover_url(url) is False


def test_rate_limit_blocks_after_budget(db, make_member):
    from app.config import settings
    from app.models import AuditAction, AuditLog

    member = make_member(email="r@x.nl", name="R")
    db.flush()
    # Vul het uur-budget exact.
    for _ in range(settings.rate_limit_ai_enrich_per_hour):
        db.add(
            AuditLog(
                action=AuditAction.cover_generated,
                actor_member_id=member.id,
                target_member_id=member.id,
                detail="cover_generated",
            )
        )
    db.flush()
    with pytest.raises(cover_service.CoverRateLimited):
        cover_service.check_cover_rate_limit(db, member.id)


def test_rate_limit_allows_under_budget(db, make_member):
    member = make_member(email="r2@x.nl", name="R2")
    db.flush()
    # Geen rijen → moet doorlaten (geen exception).
    cover_service.check_cover_rate_limit(db, member.id)
    cover_service.record_cover_generation(db, member.id)
    cover_service.check_cover_rate_limit(db, member.id)  # 1 < budget → ok
