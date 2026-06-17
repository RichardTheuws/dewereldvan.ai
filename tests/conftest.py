"""Shared test fixtures for the dewereldvan.ai Fase-1 suite.

Runs WITHOUT a live Postgres or network:
- The database is SQLite in-memory (StaticPool, one shared connection). This is
  safe because every enum uses ``native_enum=False`` (VARCHAR + CHECK) and there
  are no Postgres-only column types, so ``Base.metadata.create_all`` reproduces
  the production schema faithfully.
- Email uses an in-memory ``FakeEmailSender`` (or ConsoleEmailSender writing to a
  tmp outbox); the Resend backend is never reached over the network.

The required ``SECRET_KEY`` and a console e-mail backend are injected into the
environment *before* ``app`` is imported, because ``app.config.settings`` is a
module-level singleton constructed at import time.
"""

from __future__ import annotations

import os
import tempfile

# --- Environment must be set BEFORE importing anything under ``app`` ---------
os.environ.setdefault("SECRET_KEY", "test-secret-key-deterministic-0123456789abcdef")
os.environ.setdefault("EMAIL_BACKEND", "console")
os.environ.setdefault("ADMIN_EMAILS", "admin@dewereldvan.ai")
os.environ.setdefault("MAGIC_LINK_TTL_MIN", "15")
os.environ.setdefault("PENDING_EXPIRY_DAYS", "14")
os.environ.setdefault("RATE_LIMIT_MAGIC_PER_HOUR", "5")
# A writable outbox for the ConsoleEmailSender during tests.
_OUTBOX = tempfile.mkdtemp(prefix="dwv-outbox-")
os.environ.setdefault("CONSOLE_EMAIL_DIR", _OUTBOX)
# Point the (lazily-connected) production engine at an in-memory SQLite DB too,
# so importing app.db / app.main never tries to reach Postgres.
os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")

import pytest  # noqa: E402
from app.email.base import EmailMessage  # noqa: E402
from app.models import (  # noqa: E402
    Base,
    Member,
    MemberRole,
    MemberStatus,
)
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402


# --- Fake email backend -------------------------------------------------------
class FakeEmailSender:
    """In-memory EmailSender that records every sent message.

    Set ``fail=True`` to make ``send`` raise EmailSendError, used to prove the
    "email send failure is surfaced, never silent" edge case.
    """

    def __init__(self, *, fail: bool = False) -> None:
        self.sent: list[EmailMessage] = []
        self.fail = fail

    def send(self, message: EmailMessage) -> None:
        if self.fail:
            from app.email.base import EmailSendError

            raise EmailSendError("test: bezorging mislukt")
        self.sent.append(message)


# --- Database fixtures --------------------------------------------------------
@pytest.fixture(scope="session")
def engine():
    """Session-scoped in-memory SQLite engine with the full Fase-1 schema."""
    eng = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(eng)
    yield eng
    Base.metadata.drop_all(eng)
    eng.dispose()


@pytest.fixture
def db(engine) -> Session:
    """A fresh session bound to a rolled-back connection (test isolation).

    Each test runs inside a transaction that is rolled back at teardown, so
    tests never see each other's rows.
    """
    connection = engine.connect()
    transaction = connection.begin()
    SessionTest = sessionmaker(
        bind=connection, autoflush=False, autocommit=False, future=True
    )
    session = SessionTest()
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


# --- Member factories ---------------------------------------------------------
@pytest.fixture
def make_member(db):
    """Factory: create + flush a Member in any status/role."""

    def _make(
        *,
        email: str = "lid@example.com",
        name: str = "Test Lid",
        status: MemberStatus = MemberStatus.approved,
        role: MemberRole = MemberRole.member,
    ) -> Member:
        member = Member(
            email=email.lower(),
            name=name,
            status=status,
            role=role,
        )
        db.add(member)
        db.flush()
        return member

    return _make


@pytest.fixture
def fake_email() -> FakeEmailSender:
    return FakeEmailSender()
