"""
`@require_permission(key)` — the actual enforcement point for authorization
(Phase 1 §B, §H, §30: "Do not rely on GUI hiding for security"). Every
service method that touches sensitive data or performs a mutation should
be wrapped with this rather than trusting that the calling UI already
checked.
"""
from __future__ import annotations

import functools
from typing import Callable, TypeVar

from app.security.session_context import current_session
from app.utils.exceptions import AuthorizationError, SessionExpiredError

F = TypeVar("F", bound=Callable)


def require_permission(permission_key: str) -> Callable[[F], F]:
    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            if not current_session.is_authenticated:
                raise SessionExpiredError("No active session. Please log in.")
            if current_session.is_expired():
                current_session.clear()
                raise SessionExpiredError("Session timed out. Please log in again.")
            if not current_session.has_permission(permission_key):
                raise AuthorizationError(
                    f"User '{current_session.username}' lacks permission '{permission_key}'."
                )
            current_session.touch()
            return func(*args, **kwargs)

        return wrapper  # type: ignore[return-value]

    return decorator


def require_admin(func: F) -> F:
    """Shortcut for admin-only actions (users.manage, settings.manage, etc.)."""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        if not current_session.is_authenticated:
            raise SessionExpiredError("No active session. Please log in.")
        if current_session.is_expired():
            current_session.clear()
            raise SessionExpiredError("Session timed out. Please log in again.")
        if not current_session.is_admin:
            raise AuthorizationError(f"User '{current_session.username}' is not an administrator.")
        current_session.touch()
        return func(*args, **kwargs)

    return wrapper  # type: ignore[return-value]
