"""Smoke test: the FastAPI app builds and key routes are wired, plus an
end-to-end auth/visibility check via TestClient against the in-memory DB.

The app's get_db / email_sender dependencies are overridden so no Postgres or
network is touched.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


def test_app_imports_and_builds():
    from app.main import app

    assert app.title == "dewereldvan.ai"
    paths = {route.path for route in app.routes}
    # FOUNDATION core + the three feature routers must be mounted.
    assert "/" in paths
    assert "/healthz" in paths
    assert "/register" in paths
    assert "/login" in paths
    assert "/auth/verify" in paths
    assert "/leden/{slug}" in paths
    assert "/admin/queue" in paths


@pytest.fixture
def client(engine, fake_email, monkeypatch):
    """TestClient with DB + email overridden; routes use the in-memory schema."""
    from app.db import get_db
    from app.deps import email_sender as email_sender_dep
    from app.main import app
    from sqlalchemy.orm import sessionmaker

    SessionTest = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

    def _override_get_db():
        db = SessionTest()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[email_sender_dep] = lambda: fake_email
    try:
        # https base_url so the Secure session cookie (https_only=True) is set,
        # mirroring production where the Cloudflare tunnel terminates TLS.
        yield TestClient(app, base_url="https://testserver")
    finally:
        app.dependency_overrides.clear()


def test_healthz_ok(client):
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_register_page_renders(client):
    resp = client.get("/register")
    assert resp.status_code == 200


def test_protected_profile_edit_redirects_anonymous_to_login(client):
    resp = client.get("/profiel/bewerken", follow_redirects=False)
    # require_member -> 303 redirect to /login for anonymous users.
    assert resp.status_code in (302, 303)
    assert resp.headers["location"].endswith("/login")


def test_post_without_csrf_token_is_rejected(client):
    """A state-changing POST with no CSRF token is blocked with 403."""
    resp = client.post(
        "/login", data={"email": "x@example.com"}, follow_redirects=False
    )
    assert resp.status_code == 403


def test_post_with_valid_csrf_token_passes(client):
    """The same POST succeeds once the session CSRF token is supplied."""
    import re

    page = client.get("/login")
    csrf = re.search(r'name="csrf_token" value="([^"]+)"', page.text).group(1)
    resp = client.post(
        "/login",
        data={"email": "unknown@example.com", "csrf_token": csrf},
        follow_redirects=False,
    )
    # Unknown e-mail -> neutral confirmation page (200), not a CSRF 403.
    assert resp.status_code == 200


def test_admin_bootstrap_via_real_registration_flow(client, fake_email, engine):
    """A configured ADMIN_EMAILS address can reach /admin/queue end-to-end.

    Exercises the real register -> magic-link login -> admin path (no fabricated
    admin), proving the first-admin bootstrap is not deadlocked. This flow
    commits to the shared engine, so we clean up the rows it created at the end
    to keep the session-scoped DB clean for sibling tests.
    """
    import re

    from app.models import AuditLog, MagicLinkToken, Member
    from sqlalchemy import delete, select
    from sqlalchemy.orm import Session

    admin_email = "admin@dewereldvan.ai"  # matches conftest ADMIN_EMAILS

    try:
        # 0. Fetch the CSRF token rendered into the registration form.
        page = client.get("/register")
        csrf = re.search(r'name="csrf_token" value="([^"]+)"', page.text).group(1)

        # 1. Register the configured admin via the public registration form.
        resp = client.post(
            "/register",
            data={"name": "Beheerder", "email": admin_email, "csrf_token": csrf},
        )
        assert resp.status_code == 200

        # 2. Request a magic link; it is "sent" via the fake e-mail backend.
        fake_email.sent.clear()
        resp = client.post("/login", data={"email": admin_email, "csrf_token": csrf})
        assert resp.status_code == 200
        assert len(fake_email.sent) == 1
        body = fake_email.sent[0].text_body
        token = body.split("token=", 1)[1].split()[0].strip()

        # 3. Verify the link -> session established, redirect to profile edit.
        resp = client.get(f"/auth/verify?token={token}", follow_redirects=False)
        assert resp.status_code == 303

        # 4. The bootstrapped admin reaches the approval queue (not 303/403).
        resp = client.get("/admin/queue", follow_redirects=False)
        assert resp.status_code == 200
    finally:
        with Session(engine) as s:
            member = s.scalar(select(Member).where(Member.email == admin_email))
            if member is not None:
                s.execute(
                    delete(MagicLinkToken).where(
                        MagicLinkToken.member_id == member.id
                    )
                )
                s.execute(
                    delete(AuditLog).where(AuditLog.target_member_id == member.id)
                )
                s.delete(member)
            s.commit()
