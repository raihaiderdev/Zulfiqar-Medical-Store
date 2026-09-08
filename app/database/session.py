"""
Session helpers.

`session_scope()` is the standard way every service-layer function should
touch the database: it guarantees commit-on-success / rollback-on-error,
so a failed multi-step operation (e.g. completing a sale) never leaves
partial writes behind.
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Generator

from sqlalchemy.orm import Session

from app.database.engine import SessionLocal


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    session: Session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_db() -> None:
    """Create all tables. Used for first-run bootstrap and tests.
    Production upgrades should go through Alembic migrations instead."""
    from app.models import Base
    from app.database.engine import engine

    Base.metadata.create_all(bind=engine)


def get_engine():
    from app.database.engine import engine

    return engine
