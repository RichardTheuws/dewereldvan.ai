"""Shared route-test scaffolding for the Ervaring-laag (E1-E4) suites.

Mirrors the hermetic pattern proven in ``test_ai_profile_routes.py``:

- A DEDICATED throwaway in-memory engine per test (these tests ``commit`` real
  rows through the app, so they must NOT share the rollback-isolated ``db``
  fixture's session-scoped engine — committed data would leak).
- ``current_member`` is overridden to a chosen, session-bound member (or None),
  so ``require_member`` / ``require_admin`` (which chain off ``current_member``)
  see the exact auth state the test needs.
- The ``email_sender`` dependency is overridden to an in-memory recorder.

Kept out of ``conftest`` so the helpers can be imported directly by name.
"""

from __future__ import annotations

import re

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool


def make_route_engine():
    """A fresh in-memory SQLite engine with the full schema (caller disposes)."""
    from app.models import Base

    eng = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(eng)
    return eng


def csrf_token(client: TestClient, path: str = "/login") -> str:
    """Mint + extract the session CSRF token from any GET that renders a template.

    ``get_csrf_token`` mints and stores the token in the session on first use, so
    a single anonymous GET (default ``/login``) is enough; the returned token is
    then valid for a subsequent POST in the same client session — via either the
    hidden ``csrf_token`` form field (light base.html) or the ``hx-headers``
    ``X-CSRF-Token`` (cosmic pages).
    """
    page = client.get(path)
    assert page.status_code == 200, f"CSRF mint page {path} -> {page.status_code}"
    m = (
        re.search(r'name="csrf_token" value="([^"]+)"', page.text)
        or re.search(r'X-CSRF-Token&#34;: &#34;([^&]+)&#34;', page.text)
        or re.search(r'X-CSRF-Token"?: "([^"]+)"', page.text)
    )
    assert m, f"CSRF token not found on {path}"
    return m.group(1)
