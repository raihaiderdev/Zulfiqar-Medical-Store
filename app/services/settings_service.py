"""
Application settings (Phase 1 §33). Simple key/value store — the UI's
Settings screen reads/writes through here rather than touching
ApplicationSetting directly, so every change is audited.
"""
from __future__ import annotations

from typing import Optional

from app.database.session import session_scope
from app.models import ApplicationSetting
from app.security.decorators import require_admin
from app.security.session_context import current_session
from app.services import audit_service


@require_admin
def set_setting(key: str, value: str) -> None:
    with session_scope() as session:
        row = session.query(ApplicationSetting).filter_by(key=key).one_or_none()
        old_value = row.value if row else None
        if row:
            row.value = value
            session.add(row)
        else:
            session.add(ApplicationSetting(key=key, value=value))
        audit_service.record(
            session, user_id=current_session.user_id, action="SETTING_CHANGED", entity="application_settings",
            old_value={key: old_value}, new_value={key: value},
        )


def get_setting(key: str, default: Optional[str] = None) -> Optional[str]:
    """Read-only lookups are not permission-gated — many non-admin screens
    (e.g. the invoice printer) need the pharmacy name/address."""
    with session_scope() as session:
        row = session.query(ApplicationSetting).filter_by(key=key).one_or_none()
        return row.value if row else default


@require_admin
def get_all_settings() -> dict[str, str]:
    with session_scope() as session:
        rows = session.query(ApplicationSetting).all()
        return {r.key: r.value for r in rows}
