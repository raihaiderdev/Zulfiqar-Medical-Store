"""
Authentication service — first-run admin bootstrap, login, logout,
session handling, and self-service password change.

This is the service-layer counterpart to Phase 1 §3 (Login System) and
§42 (First-Run Setup Wizard). The UI (Phase 3 login window / setup
wizard) calls only these functions — it never touches the ORM directly.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from app.database.session import session_scope
from app.models import User
from app.repositories.user_repository import PermissionRepository, UserPermissionRepository, UserRepository
from app.security.passwords import hash_password, verify_password
from app.security.session_context import current_session
from app.services import audit_service
from app.utils.exceptions import AuthenticationError, ConflictError, ValidationError

MIN_PASSWORD_LENGTH = 8


def _validate_password_strength(password: str) -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValidationError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.")


def needs_first_run_setup() -> bool:
    """True until at least one administrator account exists."""
    with session_scope() as session:
        return not UserRepository(session).any_admin_exists()


def create_first_admin(username: str, password: str, full_name: Optional[str] = None) -> int:
    """
    Called only by the first-run setup wizard. Refuses to run if an admin
    already exists, so it can never be used to silently create a second
    backdoor admin later.
    """
    username = username.strip()
    if not username:
        raise ValidationError("Username is required.")
    _validate_password_strength(password)

    with session_scope() as session:
        repo = UserRepository(session)
        if repo.any_admin_exists():
            raise ConflictError("An administrator account already exists.")
        if repo.get_by_username(username):
            raise ConflictError(f"Username '{username}' is already taken.")

        admin = User(
            username=username,
            password_hash=hash_password(password),
            full_name=full_name,
            is_admin=True,
            is_active=True,
        )
        session.add(admin)
        session.flush()
        audit_service.record(
            session,
            user_id=admin.id,
            action="FIRST_RUN_ADMIN_CREATED",
            entity="users",
            entity_id=admin.id,
            new_value={"username": username},
        )
        return admin.id


def login(username: str, password: str) -> None:
    """
    Verifies credentials and, on success, populates the process-wide
    `current_session`. Raises AuthenticationError on any failure — the
    message is intentionally generic (doesn't reveal whether the username
    or the password was wrong) to avoid leaking account existence.
    """
    with session_scope() as session:
        repo = UserRepository(session)
        user = repo.get_by_username(username.strip())

        if user is None or not verify_password(password, user.password_hash):
            if user is not None:
                audit_service.record(
                    session, user_id=user.id, action="LOGIN_FAILED", entity="users", entity_id=user.id
                )
            raise AuthenticationError("Invalid username or password.")

        if not user.is_active:
            audit_service.record(
                session, user_id=user.id, action="LOGIN_REJECTED_INACTIVE", entity="users", entity_id=user.id
            )
            raise AuthenticationError("This account has been deactivated. Contact an administrator.")

        perm_repo = UserPermissionRepository(session)
        permission_repo = PermissionRepository(session)
        keyed = permission_repo.list_all_keyed()
        id_to_key = {p.id: key for key, p in keyed.items()}
        granted_keys = {
            id_to_key[up.permission_id]
            for up in perm_repo.get_for_user(user.id)
            if up.granted and up.permission_id in id_to_key
        }

        user.last_login_at = datetime.now(timezone.utc).isoformat()
        session.add(user)

        current_session.start(
            user_id=user.id,
            username=user.username,
            is_admin=user.is_admin,
            permission_keys=granted_keys,
        )

        audit_service.record(session, user_id=user.id, action="LOGIN_SUCCESS", entity="users", entity_id=user.id)


def logout() -> None:
    if current_session.is_authenticated:
        with session_scope() as session:
            audit_service.record(
                session,
                user_id=current_session.user_id,
                action="LOGOUT",
                entity="users",
                entity_id=current_session.user_id,
            )
    current_session.clear()


def change_own_password(old_password: str, new_password: str) -> None:
    if not current_session.is_authenticated:
        raise AuthenticationError("No active session.")
    _validate_password_strength(new_password)

    with session_scope() as session:
        repo = UserRepository(session)
        user = repo.get(current_session.user_id)
        if user is None or not verify_password(old_password, user.password_hash):
            raise AuthenticationError("Current password is incorrect.")
        user.password_hash = hash_password(new_password)
        session.add(user)
        audit_service.record(
            session, user_id=user.id, action="PASSWORD_CHANGED_SELF", entity="users", entity_id=user.id
        )
