"""Tests for E4: gestylede e-mail (html_body render) + cinematische onboarding.

E-mail is never sent over the network — the render helpers are pure string
functions, and the auth integration path uses the in-memory ``FakeEmailSender``.

Covers:
- ``email_templates.render_magic_link`` produces HTML with the verify URL in an
  ``href``, the gold CTA color, and autoescapes the member name.
- ``auth.login_submit`` attaches BOTH a non-empty text_body (fallback) AND an
  html_body carrying the same verify URL.
- First-login detection: a brand-new approved member (no turns, no headline)
  redirects to ``/welkom``; an existing member to ``/profiel/bewerken``.
- ``/welkom`` itself: member -> 200 cosmic markup + link to the AI builder;
  anonymous -> 303 /login.
"""

from __future__ import annotations

import re

import pytest
from fastapi import Depends
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from tests._route_helpers import csrf_token, make_route_engine


# --------------------------------------------------------------------------- #
# Pure render helpers (no Request, no network)                                #
# --------------------------------------------------------------------------- #
def test_render_magic_link_has_url_in_href_and_gold_cta():
    from app.email import templates as email_templates

    url = "https://dewereldvan.ai/auth/verify?token=abc123"
    html = email_templates.render_magic_link("Richard", url, 15)

    assert url in html
    assert f'href="{url}"' in html or f"href='{url}'" in html
    # The kosmische gold pill CTA color must be present.
    assert "#f6cd86" in html
    # The TTL is communicated.
    assert "15" in html


def test_render_magic_link_escapes_name():
    from app.email import templates as email_templates

    html = email_templates.render_magic_link(
        "<script>alert(1)</script>", "https://x/verify?token=t", 15
    )
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_render_approval_and_admin_notify_render():
    from app.email import templates as email_templates

    approval = email_templates.render_approval("Iemand", "https://x/login")
    assert "https://x/login" in approval
    assert "#f6cd86" in approval

    notify = email_templates.render_admin_notify(
        "Nieuw Lid", "nieuw@example.com", "https://x/admin/queue"
    )
    assert "Nieuw Lid" in notify
    assert "https://x/admin/queue" in notify


# --------------------------------------------------------------------------- #
# auth.login_submit attaches html_body alongside text_body                    #
# --------------------------------------------------------------------------- #
@pytest.fixture
def engine_and_session():
    eng = make_route_engine()
    SessionTest = sessionmaker(bind=eng, autoflush=False, autocommit=False, future=True)
    yield eng, SessionTest
    eng.dispose()


@pytest.fixture
def auth_client(engine_and_session):
    from app.db import get_db
    from app.deps import email_sender
    from app.main import app

    from tests.conftest import FakeEmailSender

    _, SessionTest = engine_and_session
    fake_sender = FakeEmailSender()

    def _override_get_db():
        db = SessionTest()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[email_sender] = lambda: fake_sender
    try:
        yield TestClient(app, base_url="https://testserver"), fake_sender, SessionTest
    finally:
        app.dependency_overrides.clear()


def test_login_submit_sends_text_and_html_with_same_url(auth_client):
    from app.models import Member, MemberStatus

    client, fake_sender, SessionTest = auth_client

    # Seed an approved member so a real link is issued.
    s = SessionTest()
    s.add(Member(email="member@example.com", name="Lid", status=MemberStatus.approved))
    s.commit()
    s.close()

    token = csrf_token(client, "/login")
    resp = client.post(
        "/login",
        data={"email": "member@example.com", "csrf_token": token},
    )
    assert resp.status_code == 200
    assert len(fake_sender.sent) == 1
    msg = fake_sender.sent[0]

    assert msg.text_body and msg.text_body.strip()  # fallback present
    assert msg.html_body and msg.html_body.strip()  # styled HTML present

    # Same verify URL appears in both bodies.
    text_url = re.search(r"https?://\S*token=\S+", msg.text_body).group(0).rstrip(".")
    assert text_url in msg.html_body


# --------------------------------------------------------------------------- #
# First-login detection (service)                                            #
# --------------------------------------------------------------------------- #
def test_is_first_login_true_for_brand_new_member(db, make_member):
    from app.services import onboarding_service

    member = make_member(email="fresh@example.com")
    assert onboarding_service.is_first_login(db, member) is True
    assert (
        onboarding_service.first_login_redirect_path(db, member)
        == onboarding_service.WELCOME_PATH
    )


def test_is_first_login_false_with_headline(db, make_member, make_profile):
    from app.services import onboarding_service

    member = make_member(email="built@example.com")
    make_profile(member, headline="Maker van dingen")
    assert onboarding_service.is_first_login(db, member) is False
    assert (
        onboarding_service.first_login_redirect_path(db, member)
        == onboarding_service.PROFILE_EDIT_PATH
    )


def test_is_first_login_false_with_existing_turns(db, make_member):
    from app.models import AiChatTurn
    from app.services import onboarding_service

    member = make_member(email="midflow@example.com")
    db.add(AiChatTurn(member_id=member.id, role="user", content_json='"hoi"'))
    db.flush()
    assert onboarding_service.is_first_login(db, member) is False


# --------------------------------------------------------------------------- #
# /welkom route                                                               #
# --------------------------------------------------------------------------- #
@pytest.fixture
def welcome_client(engine_and_session):
    from app.db import get_db
    from app.deps import current_member
    from app.main import app
    from app.models import Member

    _, SessionTest = engine_and_session

    def _override_get_db():
        db = SessionTest()
        try:
            yield db
        finally:
            db.close()

    def _factory(member_id: int | None):
        def _override_current_member(db: Session = Depends(get_db)):
            if member_id is None:
                return None
            return db.get(Member, member_id)

        app.dependency_overrides[get_db] = _override_get_db
        app.dependency_overrides[current_member] = _override_current_member
        return TestClient(app, base_url="https://testserver")

    yield _factory, SessionTest
    app.dependency_overrides.clear()


def test_welkom_anonymous_redirects_to_login(welcome_client):
    factory, _ = welcome_client
    client = factory(None)
    resp = client.get("/welkom", follow_redirects=False)
    assert resp.status_code in (302, 303)
    assert resp.headers["location"].endswith("/login")


def test_welkom_member_ok_with_link_to_builder(welcome_client):
    from app.models import Member, MemberStatus

    factory, SessionTest = welcome_client
    s = SessionTest()
    m = Member(email="welkom@example.com", name="Nieuw Lid", status=MemberStatus.approved)
    s.add(m)
    s.commit()
    member_id = m.id
    s.close()

    client = factory(member_id)
    resp = client.get("/welkom")
    assert resp.status_code == 200
    assert "/profiel/ai/bouwen" in resp.text
