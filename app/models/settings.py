from __future__ import annotations

from typing import Optional

from sqlalchemy import Boolean, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IDMixin, TimestampMixin


class ApplicationSetting(Base, IDMixin, TimestampMixin):
    """Simple key/value settings store (pharmacy info, business rules, etc.)."""
    __tablename__ = "application_settings"
    __table_args__ = (UniqueConstraint("key", name="uq_app_setting_key"),)

    key: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    value: Mapped[Optional[str]] = mapped_column(Text)


class ReportSnapshot(Base, IDMixin, TimestampMixin):
    """
    Immutable cache of a *closed* reporting period (e.g. a month), created
    only via an explicit admin "close period" action. Always regenerable
    from transactional data — this table exists purely so historical
    months load instantly without recomputation, not as the source of
    truth.
    """
    __tablename__ = "report_snapshots"
    __table_args__ = (UniqueConstraint("period_key", "report_type", name="uq_snapshot_period_type"),)

    period_key: Mapped[str] = mapped_column(String(16), nullable=False, index=True)  # e.g. "2026-01"
    report_type: Mapped[str] = mapped_column(String(32), nullable=False)  # e.g. "monthly_pnl"
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    is_closed: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    closed_by_user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
