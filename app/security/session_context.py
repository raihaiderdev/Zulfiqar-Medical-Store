"""
In-memory session for the currently logged-in user.

This is a desktop app with one active user per process, so a single
module-level SessionContext instance (see `current_session` below) is
enough — there's no need for tokens/cookies. `touch()` is called on every
service-layer action to refresh the idle timer; `is_expired()` drives the
auto-lock-to-login behavior from Phase 1 §H.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

from app.config.settings import settings


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class SessionContext:
    user_id: Optional[int] = None
    username: Optional[str] = None
    is_admin: bool = False
    logged_in_at: Optional[datetime] = None
    last_activity_at: Optional[datetime] = None
    _permission_keys: set[str] = field(default_factory=set)

    @property
    def is_authenticated(self) -> bool:
        return self.user_id is not None

    def start(self, user_id: int, username: str, is_admin: bool, permission_keys: set[str]) -> None:
        now = _utcnow()
        self.user_id = user_id
        self.username = username
        self.is_admin = is_admin
        self._permission_keys = set(permission_keys)
        self.logged_in_at = now
        self.last_activity_at = now

    def clear(self) -> None:
        self.user_id = None
        self.username = None
        self.is_admin = False
        self._permission_keys = set()
        self.logged_in_at = None
        self.last_activity_at = None

    def touch(self) -> None:
        if self.is_authenticated:
            self.last_activity_at = _utcnow()

    def is_expired(self) -> bool:
        if not self.is_authenticated or self.last_activity_at is None:
            return False
        idle_for = _utcnow() - self.last_activity_at
        return idle_for > timedelta(minutes=settings.session_timeout_minutes)

    def has_permission(self, key: str) -> bool:
        """Admins implicitly have every permission. Non-admins need an
        explicit grant, and never gain admin-only keys regardless of what
        might be stored in user_permissions (belt-and-braces vs. Phase 1 §B)."""
        if not self.is_authenticated:
            return False
        if self.is_admin:
            return True
        from app.permissions.keys import ADMIN_ONLY_KEYS

        if key in ADMIN_ONLY_KEYS:
            return False
        return key in self._permission_keys


# Single process-wide session — a desktop app has exactly one logged-in
# user at a time. Services import this rather than constructing their own.
current_session = SessionContext()
