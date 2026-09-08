"""
Minimal generic repository base. Repositories are pure data access —
no permission checks, no business rules. Those live in the service layer.
"""
from __future__ import annotations

from typing import Generic, Optional, Type, TypeVar

from sqlalchemy.orm import Session

ModelT = TypeVar("ModelT")


class BaseRepository(Generic[ModelT]):
    model: Type[ModelT]

    def __init__(self, session: Session):
        self.session = session

    def get(self, id_: int) -> Optional[ModelT]:
        return self.session.get(self.model, id_)

    def add(self, obj: ModelT) -> ModelT:
        self.session.add(obj)
        self.session.flush()
        return obj

    def list_all(self):
        return self.session.query(self.model).all()
