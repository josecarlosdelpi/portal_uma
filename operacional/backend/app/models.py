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



class GoogleReviewMonth(Base):
    """Contagem manual conferida, nao consulta automatica ao Google."""
    __tablename__ = "google_review_months"
    __table_args__ = (
        UniqueConstraint("store_code", "year", "month", name="uq_google_reviews_store_month"),
        CheckConstraint("year BETWEEN 2020 AND 2100 AND month BETWEEN 1 AND 12", name="ck_google_month"),
        CheckConstraint("count BETWEEN 0 AND 9999", name="ck_google_count"),
        CheckConstraint("revision >= 1", name="ck_google_revision"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    store_code: Mapped[str] = mapped_column(ForeignKey("stores.code", ondelete="RESTRICT"), nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    month: Mapped[int] = mapped_column(Integer, nullable=False)
    count: Mapped[int] = mapped_column(Integer, nullable=False)
    checked_on: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)
    delivered_on: Mapped[datetime | None] = mapped_column(DateTime(timezone=False))
    note: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    updated_by: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class SupplyMaterial(Base):
    __tablename__ = "supply_materials"
    __table_args__ = (UniqueConstraint("name_key", name="uq_supply_material_name_key"),)
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    name_key: Mapped[str] = mapped_column(String(100), nullable=False)
    unit: Mapped[str] = mapped_column(String(30), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)


class SupplyStock(Base):
    __tablename__ = "supply_stocks"
    __table_args__ = (
        CheckConstraint("balance >= 0", name="ck_supply_balance"),
        CheckConstraint("minimum >= 0", name="ck_supply_minimum"),
        CheckConstraint("revision >= 1", name="ck_supply_revision"),
    )
    store_code: Mapped[str] = mapped_column(ForeignKey("stores.code", ondelete="RESTRICT"), primary_key=True)
    material_id: Mapped[UUID] = mapped_column(ForeignKey("supply_materials.id", ondelete="RESTRICT"), primary_key=True)
    balance: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    minimum: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    updated_by: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)


class SupplyMovement(Base):
    __tablename__ = "supply_movements"
    __table_args__ = (
        CheckConstraint("quantity BETWEEN 1 AND 9999", name="ck_supply_move_qty"),
        CheckConstraint("kind IN ('entrada','retirada')", name="ck_supply_move_kind"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    store_code: Mapped[str] = mapped_column(ForeignKey("stores.code", ondelete="RESTRICT"), nullable=False)
    material_id: Mapped[UUID] = mapped_column(ForeignKey("supply_materials.id", ondelete="RESTRICT"), nullable=False)
    kind: Mapped[str] = mapped_column(String(12), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    resulting_balance: Mapped[int] = mapped_column(Integer, nullable=False)
    note: Mapped[str] = mapped_column(String(180), nullable=False, default="")
    actor_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class ContactClient(Base):
    """Carteira por loja, independente das vendas e sem distribuicao individual."""
    __tablename__ = "contact_clients"
    __table_args__ = (UniqueConstraint("store_code", "name_key", name="uq_client_name_store"),)
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    store_code: Mapped[str] = mapped_column(ForeignKey("stores.code", ondelete="RESTRICT"), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    name_key: Mapped[str] = mapped_column(String(120), nullable=False)
    erp_code: Mapped[str | None] = mapped_column(String(50))
    phone: Mapped[str | None] = mapped_column(String(40))
    origin: Mapped[str] = mapped_column(String(25), nullable=False)
    last_purchase_on: Mapped[datetime | None] = mapped_column(DateTime(timezone=False))
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class ContactAttempt(Base):
    """Registro de ligacao; nao equivale a venda, compra nem ativacao."""
    __tablename__ = "contact_attempts"
    __table_args__ = (
        CheckConstraint("outcome IN ('apresentacao','sem_resposta','whatsapp','outro')", name="ck_call_outcome"),
        CheckConstraint("revision >= 1", name="ck_call_revision"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    store_code: Mapped[str] = mapped_column(ForeignKey("stores.code", ondelete="RESTRICT"), nullable=False)
    client_id: Mapped[UUID] = mapped_column(ForeignKey("contact_clients.id", ondelete="RESTRICT"), nullable=False)
    seller_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    contacted_on: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)
    outcome: Mapped[str] = mapped_column(String(25), nullable=False)
    next_on: Mapped[datetime | None] = mapped_column(DateTime(timezone=False))
    note: Mapped[str] = mapped_column(String(240), nullable=False, default="")
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    updated_by: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)



class WeeklyTask(Base):
    """Versoes de rotinas semanais por loja, preservando historico de semanas anteriores."""
    __tablename__ = "weekly_tasks"
    __table_args__ = (
        CheckConstraint("frequency IN ('weekly','once')", name="ck_weekly_task_frequency"),
        CheckConstraint("scheduled_day BETWEEN 0 AND 6", name="ck_weekly_task_day"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    store_code: Mapped[str] = mapped_column(ForeignKey("stores.code", ondelete="RESTRICT"), nullable=False)
    title: Mapped[str] = mapped_column(String(100), nullable=False)
    details: Mapped[str] = mapped_column(String(350), nullable=False, default="")
    frequency: Mapped[str] = mapped_column(String(10), nullable=False)
    scheduled_day: Mapped[int] = mapped_column(Integer, nullable=False)
    start_week: Mapped[datetime] = mapped_column(DateTime(), nullable=False)
    end_week: Mapped[datetime | None] = mapped_column(DateTime())
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)


class WeeklyTaskCheck(Base):
    __tablename__ = "weekly_task_checks"
    task_id: Mapped[UUID] = mapped_column(ForeignKey("weekly_tasks.id", ondelete="RESTRICT"), primary_key=True)
    week_start: Mapped[datetime] = mapped_column(DateTime(), primary_key=True)
    done: Mapped[bool] = mapped_column(Boolean, nullable=False)
    checked_by: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class WeeklyCallGoal(Base):
    __tablename__ = "weekly_call_goals"
    __table_args__ = (CheckConstraint("goal BETWEEN 1 AND 9999", name="ck_weekly_call_goal"),)
    store_code: Mapped[str] = mapped_column(ForeignKey("stores.code", ondelete="RESTRICT"), primary_key=True)
    week_start: Mapped[datetime] = mapped_column(DateTime(), primary_key=True)
    goal: Mapped[int] = mapped_column(Integer, nullable=False)
    confirmed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    confirmed_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    updated_by: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)


class WhatsAppPost(Base):
    __tablename__ = "whatsapp_posts"
    __table_args__ = (
        UniqueConstraint("year", "product_code_key", name="uq_whatsapp_year_product"),
        CheckConstraint("status IN ('planejado','arte_pronta','publicado')", name="ck_whatsapp_status"),
        CheckConstraint("revision >= 1", name="ck_whatsapp_revision"),
    )
    post_date: Mapped[datetime] = mapped_column(DateTime(), primary_key=True)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    product_code: Mapped[str] = mapped_column(String(55), nullable=False)
    product_code_key: Mapped[str] = mapped_column(String(80), nullable=False)
    category: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    note: Mapped[str] = mapped_column(String(450), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(15), nullable=False)
    published_on: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    updated_by: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)


class WhatsAppDayOff(Base):
    __tablename__ = "whatsapp_days_off"
    post_date: Mapped[datetime] = mapped_column(DateTime(), primary_key=True)
    reason: Mapped[str] = mapped_column(String(150), nullable=False, default="")
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)


class InstagramMonth(Base):
    __tablename__ = "instagram_months"
    __table_args__ = (
        UniqueConstraint("store_code", "year", "month", name="uq_instagram_store_month"),
        CheckConstraint("year BETWEEN 2020 AND 2100 AND month BETWEEN 1 AND 12", name="ck_instagram_month"),
        CheckConstraint("planned BETWEEN 0 AND 500 AND completed BETWEEN 0 AND 500", name="ck_instagram_counts"),
        CheckConstraint("revision >= 1", name="ck_instagram_revision"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    store_code: Mapped[str] = mapped_column(ForeignKey("stores.code", ondelete="RESTRICT"), nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    month: Mapped[int] = mapped_column(Integer, nullable=False)
    planned: Mapped[int] = mapped_column(Integer, nullable=False)
    completed: Mapped[int] = mapped_column(Integer, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    updated_by: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)


class TrainingRecord(Base):
    """Metadados de participacao. Assinaturas e PDFs exigem armazenamento privado futuro."""
    __tablename__ = "training_records"
    __table_args__ = (
        CheckConstraint("step IN ('participou','pratica')", name="ck_training_step"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    store_code: Mapped[str] = mapped_column(ForeignKey("stores.code", ondelete="RESTRICT"), nullable=False)
    participant_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    procedure: Mapped[str] = mapped_column(String(40), nullable=False)
    version: Mapped[str] = mapped_column(String(45), nullable=False)
    title: Mapped[str] = mapped_column(String(140), nullable=False, default="")
    instructor: Mapped[str] = mapped_column(String(90), nullable=False)
    happened_on: Mapped[datetime] = mapped_column(DateTime(), nullable=False)
    step: Mapped[str] = mapped_column(String(15), nullable=False)
    note: Mapped[str] = mapped_column(String(350), nullable=False, default="")
    recorded_by: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class AccessInvitation(Base):
    """Pre-cadastro administrativo; NAO e credencial ou convite enviado."""
    __tablename__ = "access_invitations"
    __table_args__ = (
        UniqueConstraint("email_key", name="uq_access_invitations_email_key"),
        CheckConstraint("profile IN ('administrator','seller')", name="ck_invite_profile"),
        CheckConstraint("status IN ('prepared','sent','activated','cancelled','expired')", name="ck_invite_status"),
        CheckConstraint(
            "(profile='administrator' AND store_code IS NULL) OR "
            "(profile='seller' AND store_code IS NOT NULL)",
            name="ck_invite_store_by_profile",
        ),
        CheckConstraint("revision >= 1", name="ck_invite_revision"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    email: Mapped[str] = mapped_column(String(254), nullable=False)
    email_key: Mapped[str] = mapped_column(String(254), nullable=False)
    display_name: Mapped[str] = mapped_column(String(150), nullable=False)
    profile: Mapped[str] = mapped_column(String(30), nullable=False)
    store_code: Mapped[str | None] = mapped_column(
        ForeignKey("stores.code", ondelete="RESTRICT"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="prepared")
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    prepared_by: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    updated_by: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
