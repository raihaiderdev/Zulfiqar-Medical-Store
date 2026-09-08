from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from app.models import Permission, User, UserPermission
from app.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    model = User

    def get_by_username(self, username: str) -> Optional[User]:
        return (
            self.session.query(User)
            .filter(User.username == username)
            .one_or_none()
        )

    def any_admin_exists(self) -> bool:
        return self.session.query(User).filter(User.is_admin.is_(True)).count() > 0

    def list_active(self) -> list[User]:
        return self.session.query(User).filter(User.is_active.is_(True)).order_by(User.username).all()

    def list_all(self) -> list[User]:
        return self.session.query(User).order_by(User.username).all()


class PermissionRepository(BaseRepository[Permission]):
    model = Permission

    def get_by_key(self, key: str) -> Optional[Permission]:
        return self.session.query(Permission).filter(Permission.key == key).one_or_none()

    def list_all_keyed(self) -> dict[str, Permission]:
        return {p.key: p for p in self.session.query(Permission).all()}


class UserPermissionRepository(BaseRepository[UserPermission]):
    model = UserPermission

    def get_for_user(self, user_id: int) -> list[UserPermission]:
        return (
            self.session.query(UserPermission)
            .filter(UserPermission.user_id == user_id)
            .all()
        )

    def get_grant(self, user_id: int, permission_id: int) -> Optional[UserPermission]:
        return (
            self.session.query(UserPermission)
            .filter(UserPermission.user_id == user_id, UserPermission.permission_id == permission_id)
            .one_or_none()
        )
