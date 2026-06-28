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
# Profielfoto-opslag naar een wegwerp-tmpdir (nooit naar de echte data/uploads).
# Móet vóór de app-import, want app.config.settings is een module-singleton en
# app/storage/photos.py resolvet UPLOAD_DIR op import (zoals CONSOLE_EMAIL_DIR).
_UPLOAD_DIR = tempfile.mkdtemp(prefix="dwv-uploads-")
os.environ.setdefault("UPLOAD_DIR", _UPLOAD_DIR)
# Borg de "geen netwerk"-belofte: wis een eventueel geërfde ANTHROPIC_API_KEY uit de
# dev-shell, zodat een lazy ``anthropic.Anthropic()`` (bv. de registratie-spam-triage)
# nooit écht belt. AI-tests installeren hun eigen fake-client (install_fake_anthropic);
# zonder fake valt elke AI-call veilig terug (triage → review).
os.environ.pop("ANTHROPIC_API_KEY", None)

import pytest  # noqa: E402
from app.email.base import EmailMessage  # noqa: E402
from app.models import (  # noqa: E402
    Base,
    Member,
    MemberRole,
    MemberStatus,
    Offering,
    Profile,
    ProfileEmphasis,
    Visibility,
)
from sqlalchemy import create_engine, event  # noqa: E402
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
    # pysqlite's legacy transaction handling breaks SAVEPOINT (nested) rollback:
    # after a ``begin_nested`` IntegrityError the outer transaction is no longer
    # rolled back cleanly, so rows leak between tests. The documented SQLAlchemy
    # recipe disables pysqlite's implicit BEGIN and emits it ourselves, restoring
    # correct SAVEPOINT semantics — required to faithfully test the idempotent
    # race recovery in registration_service / idea_service (which use savepoints).
    @event.listens_for(eng, "connect")
    def _sqlite_connect(dbapi_connection, _record):
        dbapi_connection.isolation_level = None
        # Enforce FKs at connect time (autocommit, no transaction active yet):
        # ``PRAGMA foreign_keys`` is a no-op inside a transaction, and our explicit
        # BEGIN below means one is always active by the time a test runs — so the
        # pragma must be set here for ON DELETE SET NULL/CASCADE to fire.
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    @event.listens_for(eng, "begin")
    def _sqlite_emit_begin(conn):
        conn.exec_driver_sql("BEGIN")

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
def make_profile(db):
    """Factory: create + flush a Profile for a member at a chosen visibility.

    ``profile.slug`` is NOT NULL; we derive it from the display name (with a
    numeric suffix on collision) so factory-built fixtures are valid without the
    caller having to think about slugs. ``visibility`` / ``emphasis`` are
    settable so the visibility-poort and emphasis-layout tests can pick the
    exact state they need.
    """
    from app.security import slugify, unique_slug

    def _make(
        member: Member,
        *,
        display_name: str | None = None,
        visibility: Visibility = Visibility.public,
        emphasis: ProfileEmphasis = ProfileEmphasis.balanced,
        bio: str | None = None,
        makes_summary: str | None = None,
        headline: str | None = None,
    ) -> Profile:
        name = display_name or member.name or member.email.split("@", 1)[0]

        def _slug_taken(candidate: str) -> bool:
            from sqlalchemy import select

            return (
                db.scalar(select(Profile.id).where(Profile.slug == candidate))
                is not None
            )

        profile = Profile(
            member_id=member.id,
            slug=unique_slug(name or slugify(member.email), _slug_taken),
            display_name=name,
            visibility=visibility,
            emphasis=emphasis,
            bio=bio,
            makes_summary=makes_summary,
            headline=headline,
        )
        db.add(profile)
        db.flush()
        return profile

    return _make


@pytest.fixture
def make_offering(db):
    """Factory: create + flush an Offering ("project") on a profile.

    ``ensure_slug`` is intentionally NOT called here so slug-generation tests can
    observe the unset state; route/sitemap tests that need a slug call
    ``offering_slug.ensure_slug`` themselves (mirrors production write paths).
    """

    def _make(
        profile: Profile,
        *,
        title: str = "Een project",
        description: str | None = None,
        url: str | None = None,
        image_url: str | None = None,
    ) -> Offering:
        offering = Offering(
            title=title,
            description=description,
            url=url,
            image_url=image_url,
            position=len(profile.offerings),
        )
        # Append via de relationship (niet via profile_id in de constructor) zodat
        # de in-session ``profile.offerings``-collectie consistent blijft — anders
        # ziet een query die dezelfde identity-mapped Profile teruggeeft een
        # verouderde lege collectie (mirror van profile_service.add_offering).
        profile.offerings.append(offering)
        db.flush()
        return offering

    return _make


@pytest.fixture
def fake_email() -> FakeEmailSender:
    return FakeEmailSender()


# --- Ervaring-laag factories (E1-E3) -----------------------------------------
@pytest.fixture
def make_feedback(db):
    """Factory: create + flush a Feedback row (member optional = anoniem)."""
    from app.models import Feedback

    def _make(
        *,
        member: Member | None = None,
        page_path: str = "/leden",
        body: str = "Mooie pagina.",
        kind: str = "algemeen",
        hidden: bool = False,
        ai_summary: str | None = None,
    ) -> Feedback:
        row = Feedback(
            member_id=member.id if member is not None else None,
            page_path=page_path,
            body=body,
            kind=kind,
            hidden=hidden,
            ai_summary=ai_summary,
        )
        db.add(row)
        db.flush()
        return row

    return _make


@pytest.fixture
def make_idea(db):
    """Factory: create + flush an Idea (status defaults to ``open``)."""
    from app.models import Idea, IdeaStatus

    def _make(
        member: Member,
        *,
        title: str = "Een fris idee",
        body: str = "We zouden X kunnen doen.",
        status: IdeaStatus = IdeaStatus.open,
        hidden: bool = False,
    ) -> Idea:
        idea = Idea(
            member_id=member.id,
            title=title,
            body=body,
            status=status,
            hidden=hidden,
        )
        db.add(idea)
        db.flush()
        return idea

    return _make


@pytest.fixture
def make_roadmap_item(db):
    """Factory: create + flush a RoadmapItem."""
    from app.models import RoadmapItem, RoadmapStatus

    def _make(
        *,
        title: str = "Een mijlpaal",
        description: str | None = None,
        status: RoadmapStatus = RoadmapStatus.overwegen,
        phase: str = "Later",
        position: int = 0,
        linked_idea_id: int | None = None,
    ) -> RoadmapItem:
        item = RoadmapItem(
            title=title,
            description=description,
            status=status,
            phase=phase,
            position=position,
            linked_idea_id=linked_idea_id,
        )
        db.add(item)
        db.flush()
        return item

    return _make


# --- Fake AI cover-image backend ---------------------------------------------
# The reusable doubles (FakeImageGenerator / FakeAnthropic / install_fake_anthropic)
# live in tests/_ai_helpers.py so test modules can import them directly; the
# fixture below just wraps FakeImageGenerator for dependency-override use.
from tests._ai_helpers import FakeImageGenerator  # noqa: E402


@pytest.fixture
def fake_image_generator() -> FakeImageGenerator:
    return FakeImageGenerator()
