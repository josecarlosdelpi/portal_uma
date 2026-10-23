"""Modelo inicial de persistencia. Schema mantido por migrations Alembic."""
from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, JSON, Numeric, String, UniqueConstraint, Uuid, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Store(Base):
    __tablename__ = "stores"

    code: Mapped[str] = mapped_column(String(20), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")


class User(Base):
    __tablename__ = "users"
    __table_args__ = (CheckConstraint("profile IN ('administrator', 'seller')", name="ck_users_profile"),)

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    auth_subject: Mapped[str] = mapped_column(String(250), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(150), nullable=False)
    profile: Mapped[str] = mapped_column(String(30), nullable=False)
    is_superadmin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class StoreGroup(Base):
    __tablename__ = "store_groups"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    store_code: Mapped[str] = mapped_column(ForeignKey("stores.code", ondelete="RESTRICT"), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")


class GroupMembership(Base):
    __tablename__ = "group_memberships"

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    group_id: Mapped[UUID] = mapped_column(ForeignKey("store_groups.id", ondelete="CASCADE"), primary_key=True)


class GroupPermission(Base):
    __tablename__ = "group_permissions"

    group_id: Mapped[UUID] = mapped_column(ForeignKey("store_groups.id", ondelete="CASCADE"), primary_key=True)
    code: Mapped[str] = mapped_column(String(100), primary_key=True)
    granted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")


class UserPermissionOverride(Base):
    __tablename__ = "user_permission_overrides"

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    code: Mapped[str] = mapped_column(String(100), primary_key=True)
    granted: Mapped[bool] = mapped_column(Boolean, nullable=False)


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    actor_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    actor_subject: Mapped[str] = mapped_column(String(250), nullable=False)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_id: Mapped[str | None] = mapped_column(String(150), nullable=True)
    details: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class MonthlySalesTarget(Base):
    """Meta e calendario mensal da loja; versionados para evitar perda de alteracoes."""
    __tablename__ = "monthly_sales_targets"
    __table_args__ = (
        UniqueConstraint("store_code", "year", "month", name="uq_monthly_target_store_period"),
        CheckConstraint("year BETWEEN 2020 AND 2100", name="ck_monthly_target_year"),
        CheckConstraint("month BETWEEN 1 AND 12", name="ck_monthly_target_month"),
        CheckConstraint("amount IS NULL OR amount > 0", name="ck_monthly_target_amount"),
        CheckConstraint("revision >= 1", name="ck_monthly_target_revision"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    store_code: Mapped[str] = mapped_column(ForeignKey("stores.code", ondelete="RESTRICT"), nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    month: Mapped[int] = mapped_column(Integer, nullable=False)
    amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    days_off: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    updated_by: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class StoreTargetSettings(Base):
    """Minimo diario adotado *apos* o atingimento da meta; por loja."""
    __tablename__ = "store_target_settings"
    __table_args__ = (
        CheckConstraint("minimum_daily >= 0", name="ck_store_target_minimum_nonnegative"),
        CheckConstraint("revision >= 1", name="ck_store_settings_revision"),
    )

    store_code: Mapped[str] = mapped_column(
        ForeignKey("stores.code", ondelete="RESTRICT"), primary_key=True
    )
    minimum_daily: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    updated_by: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )



class MonthlyClosingDraft(Base):
    """Rascunho mensal unico, salvo com versao e trilha de auditoria."""
    __tablename__ = "monthly_closing_drafts"
    __table_args__ = (
        UniqueConstraint("year", "month", name="uq_closing_draft_period"),
        CheckConstraint("year BETWEEN 2020 AND 2100", name="ck_closing_draft_year"),
        CheckConstraint("month BETWEEN 1 AND 12", name="ck_closing_draft_month"),
        CheckConstraint("revision >= 1", name="ck_closing_draft_revision"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    month: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[dict] = mapped_column(JSON, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    updated_by: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class MonthlyClosingArchive(Base):
    """Versoes congeladas: editar o rascunho nao altera versoes anteriores."""
    __tablename__ = "monthly_closing_archives"
    __table_args__ = (
        UniqueConstraint("year", "month", "version", name="uq_closing_archive_period_version"),
        CheckConstraint("year BETWEEN 2020 AND 2100", name="ck_closing_archive_year"),
        CheckConstraint("month BETWEEN 1 AND 12", name="ck_closing_archive_month"),
        CheckConstraint("version >= 1", name="ck_closing_archive_version"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    month: Mapped[int] = mapped_column(Integer, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    archived_by: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
