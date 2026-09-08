"""
Service-layer exceptions. UI code catches these and shows a friendly
dialog instead of letting a raw traceback reach the user (Phase 1 §H, §37).
"""
from __future__ import annotations


class ApplicationError(Exception):
    """Base class for all expected/handled application errors."""


class AuthenticationError(ApplicationError):
    """Raised on invalid login credentials or an inactive account."""


class AuthorizationError(ApplicationError):
    """Raised when a user lacks the permission required for an action."""


class SessionExpiredError(ApplicationError):
    """Raised when an action is attempted on a timed-out/absent session."""


class ValidationError(ApplicationError):
    """Raised on invalid input data (bad fields, business-rule violations)."""


class NotFoundError(ApplicationError):
    """Raised when a referenced record does not exist."""


class ConflictError(ApplicationError):
    """Raised on uniqueness or state conflicts (e.g. duplicate username)."""
