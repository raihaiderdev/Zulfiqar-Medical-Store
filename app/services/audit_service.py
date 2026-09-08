"""
Audit logging helper. Every sensitive action goes through `record()` so
the audit trail is written in the same DB transaction as the action it
describes — never as a best-effort afterthought.
"""
from __future__ import annotations

import json
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models import AuditLog


def _to_json(value: Any) -> Optional[str]:
    if value is None:
        return None
    try:
        return json.dumps(value, default=str)
    except TypeError:
        return str(value)


def record(
    session: Session,
    *,
    user_id: Optional[int],
    action: str,
    entity: str,
    entity_id: Optional[int] = None,
    old_value: Any = None,
    new_value: Any = None,
) -> AuditLog:
    log = AuditLog(
        user_id=user_id,
        action=action,
        entity=entity,
        entity_id=entity_id,
        old_value=_to_json(old_value),
        new_value=_to_json(new_value),
    )
    session.add(log)
    session.flush()
    return log
