"""
User management — admin-only per the Phase 1 permission matrix
(`users.manage` is never grantable to a regular user). Every mutation is
audited and permission-checked via `@require_admin`.
"""
from __future__ import annotations

import secrets
import string
from typing import Optional

from app.database.session import session_scope
from app.models import User
from app.repositories.user_repository import PermissionRepository, UserPermissionRepository, UserRepository
from app.security.decorators import require_admin
from app.security.passwords import hash_password
from app.security.session_context import current_session
from app.services import audit_service
from app.services.auth_service import MIN_PASSWORD_LENGTH, _validate_password_strength
from app.utils.exceptions import ConflictError, NotFoundError, ValidationError


def _generate_temp_password(length: int = 12) -> str:
    alphabet = string.ascii_letters + string.digits + "!@#$%"
    return "".join(secrets.choice(alphabet) for _ in range(length))


@require_admin
def create_user(
    username: str,
    password: str,
    full_name: Optional[str] = None,
    is_admin: bool = False,
    permission_keys: Optional[list[str]] = None,
) -> int:
    username = username.strip()
    if not username:
        raise ValidationError("Username is required.")
    _validate_password_strength(password)

    with session_scope() as session:
        repo = UserRepository(session)
        if repo.get_by_username(username):
            raise ConflictError(f"Username '{username}' is already taken.")

        user = User(
            username=username,
            password_hash=hash_password(password),
            full_name=full_name,
            is_admin=is_admin,
            is_active=True,
        )
        session.add(user)
        session.flush()

        if permission_keys and not is_admin:
            _apply_permission_grants(session, user.id, permission_keys)

        audit_service.record(
            session,
            user_id=current_session.user_id,
            action="USER_CREATED",
            entity="users",
            entity_id=user.id,
            new_value={"username": username, "is_admin": is_admin, "permissions": permission_keys or []},
        )
        return user.id


@require_admin
def edit_user(user_id: int, full_name: Optional[str] = None, is_admin: Optional[bool] = None) -> None:
    with session_scope() as session:
        repo = UserRepository(session)
        user = repo.get(user_id)
        if user is None:
            raise NotFoundError(f"User {user_id} not found.")
        old_value = {"full_name": user.full_name, "is_admin": user.is_admin}

        if full_name is not None:
            user.full_name = full_name
        if is_admin is not None:
            user.is_admin = is_admin
        session.add(user)

        audit_service.record(
            session,
            user_id=current_session.user_id,
            action="USER_EDITED",
            entity="users",
            entity_id=user.id,
            old_value=old_value,
            new_value={"full_name": user.full_name, "is_admin": user.is_admin},
        )


@require_admin
def deactivate_user(user_id: int) -> None:
    """Soft delete — historical sales/purchases/audit rows referencing this
    user must remain intact (Phase 1 §47.6)."""
    with session_scope() as session:
        repo = UserRepository(session)
        user = repo.get(user_id)
        if user is None:
            raise NotFoundError(f"User {user_id} not found.")
        if user.id == current_session.user_id:
            raise ValidationError("You cannot deactivate your own account.")
        user.is_active = False
        session.add(user)
        audit_service.record(
            session, user_id=current_session.user_id, action="USER_DEACTIVATED", entity="users", entity_id=user.id
        )


@require_admin
def reactivate_user(user_id: int) -> None:
    with session_scope() as session:
        repo = UserRepository(session)
        user = repo.get(user_id)
        if user is None:
            raise NotFoundError(f"User {user_id} not found.")
        user.is_active = True
        session.add(user)
        audit_service.record(
            session, user_id=current_session.user_id, action="USER_REACTIVATED", entity="users", entity_id=user.id
        )


@require_admin
def reset_password(user_id: int, new_password: Optional[str] = None) -> str:
    """Admin-initiated reset. Returns the new password so the admin can
    relay it to the user out-of-band; the user should change it on next
    login (enforcing that is a UI-layer nicety for a later phase)."""
    temp_password = new_password or _generate_temp_password()
    _validate_password_strength(temp_password)

    with session_scope() as session:
        repo = UserRepository(session)
        user = repo.get(user_id)
        if user is None:
            raise NotFoundError(f"User {user_id} not found.")
        user.password_hash = hash_password(temp_password)
        session.add(user)
        audit_service.record(
            session,
            user_id=current_session.user_id,
            action="PASSWORD_RESET_BY_ADMIN",
            entity="users",
            entity_id=user.id,
        )
    return temp_password


def _apply_permission_grants(session, user_id: int, permission_keys: list[str]) -> None:
    from app.models import Permission, UserPermission
    from app.permissions.keys import ADMIN_ONLY_KEYS, GRANTABLE_PERMISSIONS

    perm_repo = PermissionRepository(session)
    user_perm_repo = UserPermissionRepository(session)
    keyed = perm_repo.list_all_keyed()

    for key in permission_keys:
        if key in ADMIN_ONLY_KEYS:
            continue
        if key not in GRANTABLE_PERMISSIONS:
            continue

        # Auto-create the Permission master row if it was never seeded.
        permission = keyed.get(key)
        if permission is None:
            permission = Permission(
                key=key,
                description=GRANTABLE_PERMISSIONS[key],
                admin_only=False,
            )
            session.add(permission)
            session.flush()
            keyed[key] = permission  # update local cache

        existing = user_perm_repo.get_grant(user_id, permission.id)
        if existing:
            existing.granted = True
        else:
            session.add(UserPermission(user_id=user_id, permission_id=permission.id, granted=True))


@require_admin
def set_user_permissions(user_id: int, permission_keys: list[str]) -> None:
    """Replaces the user's grantable-permission set wholesale (revokes
    anything not in the list, grants everything in it)."""
    from app.permissions.keys import ADMIN_ONLY_KEYS, GRANTABLE_PERMISSIONS

    with session_scope() as session:
        repo = UserRepository(session)
        user = repo.get(user_id)
        if user is None:
            raise NotFoundError(f"User {user_id} not found.")

        perm_repo = PermissionRepository(session)
        user_perm_repo = UserPermissionRepository(session)
        keyed = perm_repo.list_all_keyed()
        id_to_key = {p.id: k for k, p in keyed.items()}

        requested = {k for k in permission_keys if k in GRANTABLE_PERMISSIONS and k not in ADMIN_ONLY_KEYS}
        current_grants = {
            id_to_key[g.permission_id]: g
            for g in user_perm_repo.get_for_user(user_id)
            if g.permission_id in id_to_key
        }

        for key, grant in current_grants.items():
            grant.granted = key in requested
            session.add(grant)

        for key in requested - current_grants.keys():
            permission = keyed.get(key)
            if permission:
                from app.models import UserPermission

                session.add(UserPermission(user_id=user_id, permission_id=permission.id, granted=True))

        audit_service.record(
            session,
            user_id=current_session.user_id,
            action="USER_PERMISSIONS_SET",
            entity="users",
            entity_id=user_id,
            new_value={"permissions": sorted(requested)},
        )


@require_admin
def list_users() -> list[User]:
    with session_scope() as session:
        repo = UserRepository(session)
        users = repo.list_all()
        session.expunge_all()
        return users


@require_admin
def get_user_permissions(user_id: int) -> set[str]:
    with session_scope() as session:
        perm_repo = PermissionRepository(session)
        user_perm_repo = UserPermissionRepository(session)
        keyed = perm_repo.list_all_keyed()
        id_to_key = {p.id: k for k, p in keyed.items()}
        return {
            id_to_key[g.permission_id]
            for g in user_perm_repo.get_for_user(user_id)
            if g.granted and g.permission_id in id_to_key
        }
