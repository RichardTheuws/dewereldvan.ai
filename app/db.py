"""Database engine, session factory, and the FastAPI get_db dependency."""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings
from app.models import Base

# Re-export Base so callers (e.g. Alembic env) can `from app.db import Base`.
__all__ = ["engine", "SessionLocal", "get_db", "Base"]

engine = create_engine(settings.database_url, pool_pre_ping=True, future=True)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def get_db() -> Iterator[Session]:
    """Yield a database session, ensuring it is closed afterward."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
