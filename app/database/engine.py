"""
Engine creation and SQLite-specific pragmas.

Foreign keys are OFF by default in SQLite unless explicitly enabled per
connection, so we hook that in here — otherwise all our ForeignKey/
ondelete rules would silently do nothing.
"""
from __future__ import annotations

from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.config.settings import settings


def _create_engine():
    from sqlalchemy import create_engine

    connect_args = {}
    if settings.database_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False

    engine = create_engine(
        settings.database_url,
        echo=False,
        future=True,
        connect_args=connect_args,
    )
    return engine


engine = _create_engine()


@event.listens_for(Engine, "connect")
def _set_sqlite_pragmas(dbapi_connection, connection_record):  # noqa: ANN001
    """Enable FK enforcement and WAL mode for every new SQLite connection."""
    if settings.database_url.startswith("sqlite"):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True, class_=Session)
