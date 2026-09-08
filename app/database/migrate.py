"""
Runs `alembic upgrade head` programmatically at application startup, so a
packaged .exe upgrades its own database file on launch without requiring
the user to have Python/Alembic installed separately (Phase 1 §43 —
"do not destroy existing user data when updating the application").
"""
from __future__ import annotations

import sys
from pathlib import Path

from alembic import command
from alembic.config import Config


def _resource_root() -> Path:
    """Project root in dev; PyInstaller's extraction dir when frozen."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    return Path(__file__).resolve().parent.parent.parent


def seed_permissions() -> None:
    """
    Ensures every known permission key has a row in the `permissions` table.
    This is idempotent — safe to call on every startup. New keys are inserted;
    existing rows are left untouched.  Without this, non-admin users can never
    receive permission grants because `list_all_keyed()` returns an empty dict.
    """
    from app.database.session import session_scope
    from app.models import Permission
    from app.permissions.keys import ALL_PERMISSIONS

    with session_scope() as session:
        existing_keys = {p.key for p in session.query(Permission).all()}
        for key, description in ALL_PERMISSIONS.items():
            if key not in existing_keys:
                from app.permissions.keys import ADMIN_ONLY_KEYS
                session.add(Permission(
                    key=key,
                    description=description,
                    admin_only=(key in ADMIN_ONLY_KEYS),
                ))


def run_migrations_to_head() -> None:
    root = _resource_root()
    alembic_ini = root / "alembic.ini"
    if not alembic_ini.exists():
        # Dev environments that haven't run `alembic upgrade head` manually
        # yet, or an unusual packaging layout — fall back to create_all()
        # rather than crashing the app on launch.
        from app.database.session import init_db

        init_db()
        seed_permissions()
        return

    config = Config(str(alembic_ini))
    config.set_main_option("script_location", str(root / "database" / "migrations"))
    command.upgrade(config, "head")
    # Seed permission rows AFTER schema is up to date.
    seed_permissions()
