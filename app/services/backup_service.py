"""
Backup/restore (Phase 1 §31). Admin-only, always makes a safety copy of
the *current* database before restoring, validates a candidate restore
file before touching the live DB, and rotates old auto-backups so disk
usage doesn't grow unbounded (Phase 1 §M.5).
"""
from __future__ import annotations

import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from app.config.settings import DEFAULT_DB_PATH, settings
from app.security.decorators import require_admin
from app.services import audit_service
from app.security.session_context import current_session
from app.database.session import session_scope
from app.utils.exceptions import ValidationError

# Tables that must exist for a file to be considered a genuine, schema-
# compatible pharmacy database. Kept intentionally short (not the full 26)
# so this check still passes against older-but-compatible backups after
# additive migrations.
_REQUIRED_TABLES = {"users", "medicines", "medicine_batches", "sales", "stock_transactions"}


def _db_path() -> Path:
    if not settings.database_url.startswith("sqlite:///"):
        raise ValidationError("Backup/restore currently supports the local SQLite database only.")
    return Path(settings.database_url.replace("sqlite:///", "", 1))


def validate_backup_file(path: Path) -> None:
    if not path.exists():
        raise ValidationError(f"Backup file not found: {path}")
    try:
        con = sqlite3.connect(str(path))
        cursor = con.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row[0] for row in cursor.fetchall()}
        con.close()
    except sqlite3.Error as exc:
        raise ValidationError(f"File is not a valid SQLite database: {exc}") from exc

    missing = _REQUIRED_TABLES - tables
    if missing:
        raise ValidationError(
            f"File does not look like a Pharmacy Management database — missing table(s): {', '.join(sorted(missing))}"
        )


def _rotate_old_backups(backup_dir: Path, retention_count: int) -> None:
    backups = sorted(backup_dir.glob("pharmacy_backup_*.db"), key=lambda p: p.stat().st_mtime, reverse=True)
    for stale in backups[retention_count:]:
        stale.unlink(missing_ok=True)


@require_admin
def create_backup(destination_dir: Optional[Path] = None) -> Path:
    from app.config.settings import BACKUP_DIR

    destination_dir = destination_dir or BACKUP_DIR
    destination_dir.mkdir(parents=True, exist_ok=True)

    source = _db_path()
    if not source.exists():
        raise ValidationError(f"Live database not found at {source}")

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M%S")
    dest_path = destination_dir / f"pharmacy_backup_{timestamp}.db"

    # SQLite's own backup API produces a consistent snapshot even if a
    # write is in-flight, unlike a raw file copy.
    source_con = sqlite3.connect(str(source))
    dest_con = sqlite3.connect(str(dest_path))
    with dest_con:
        source_con.backup(dest_con)
    source_con.close()
    dest_con.close()

    if destination_dir == BACKUP_DIR:
        _rotate_old_backups(BACKUP_DIR, settings.backup_retention_count)

    with session_scope() as session:
        audit_service.record(
            session, user_id=current_session.user_id, action="BACKUP_CREATED", entity="database",
            new_value={"path": str(dest_path)},
        )
    return dest_path


@require_admin
def restore_backup(backup_path: Path) -> Path:
    """
    Validates the candidate file, takes a safety backup of the current
    live database first, then swaps the file in. Returns the path of the
    safety backup that was made, so the caller can tell the user where it
    went in case something looks wrong after restoring.
    """
    backup_path = Path(backup_path)
    validate_backup_file(backup_path)

    safety_backup_path = create_backup()  # of the CURRENT (pre-restore) database

    live_path = _db_path()

    # Force every pooled connection to release its file handle before we
    # touch the file on disk.
    from app.database.session import get_engine

    get_engine().dispose()

    shutil.copyfile(backup_path, live_path)

    # `backup_path` is a fully-checkpointed single-file snapshot (produced
    # by SQLite's backup API in create_backup()), but the *live* database
    # was running in WAL mode and may still have a `-wal`/`-shm` sidecar
    # sitting next to it with frames from after the backup was taken. Left
    # in place, those stale sidecars would get replayed on top of the
    # restored file and silently resurrect post-backup changes — so they
    # must be cleared for the restore to actually take effect.
    for suffix in ("-wal", "-shm"):
        sidecar = live_path.with_name(live_path.name + suffix)
        sidecar.unlink(missing_ok=True)

    with session_scope() as session:
        audit_service.record(
            session, user_id=current_session.user_id, action="DATABASE_RESTORED", entity="database",
            new_value={"restored_from": str(backup_path), "safety_backup": str(safety_backup_path)},
        )
    return safety_backup_path
