"""Independent weekly routines, WhatsApp Status, Instagram and training metadata.

Revision ID: 0006
Revises: 0005
"""
from alembic import op
import sqlalchemy as sa

revision="0006"
down_revision="0005"
branch_labels=None
depends_on=None


def upgrade():
    op.create_table("weekly_tasks",
        sa.Column("id",sa.Uuid(),primary_key=True),
        sa.Column("store_code",sa.String(20),sa.ForeignKey("stores.code",ondelete="RESTRICT"),nullable=False),
        sa.Column("title",sa.String(100),nullable=False),
        sa.Column("details",sa.String(350),nullable=False,server_default=""),
        sa.Column("frequency",sa.String(10),nullable=False),
        sa.Column("scheduled_day",sa.Integer(),nullable=False),
        sa.Column("start_week",sa.DateTime(),nullable=False),
        sa.Column("end_week",sa.DateTime()),
        sa.Column("active",sa.Boolean(),nullable=False,server_default=sa.true()),
        sa.Column("created_by",sa.Uuid(),sa.ForeignKey("users.id",ondelete="RESTRICT"),nullable=False),
        sa.CheckConstraint("frequency IN ('weekly','once')",name="ck_weekly_task_frequency"),
        sa.CheckConstraint("scheduled_day BETWEEN 0 AND 6",name="ck_weekly_task_day"),
    )
    op.create_table("weekly_task_checks",
        sa.Column("task_id",sa.Uuid(),sa.ForeignKey("weekly_tasks.id",ondelete="RESTRICT"),primary_key=True),
        sa.Column("week_start",sa.DateTime(),primary_key=True),
        sa.Column("done",sa.Boolean(),nullable=False),
        sa.Column("checked_by",sa.Uuid(),sa.ForeignKey("users.id",ondelete="RESTRICT"),nullable=False),
        sa.Column("checked_at",sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()),
    )
    op.create_table("weekly_call_goals",
        sa.Column("store_code",sa.String(20),sa.ForeignKey("stores.code",ondelete="RESTRICT"),primary_key=True),
        sa.Column("week_start",sa.DateTime(),primary_key=True),
        sa.Column("goal",sa.Integer(),nullable=False),
        sa.Column("confirmed",sa.Boolean(),nullable=False,server_default=sa.false()),
        sa.Column("confirmed_by",sa.Uuid(),sa.ForeignKey("users.id",ondelete="SET NULL")),
        sa.Column("updated_by",sa.Uuid(),sa.ForeignKey("users.id",ondelete="RESTRICT"),nullable=False),
        sa.CheckConstraint("goal BETWEEN 1 AND 9999",name="ck_weekly_call_goal"),
    )
    op.create_table("whatsapp_posts",
        sa.Column("post_date",sa.DateTime(),primary_key=True),
        sa.Column("year",sa.Integer(),nullable=False),
        sa.Column("product_code",sa.String(55),nullable=False),
        sa.Column("product_code_key",sa.String(80),nullable=False),
        sa.Column("category",sa.String(120),nullable=False,server_default=""),
        sa.Column("note",sa.String(450),nullable=False,server_default=""),
        sa.Column("status",sa.String(15),nullable=False),
        sa.Column("published_on",sa.DateTime(timezone=True)),
        sa.Column("revision",sa.Integer(),nullable=False,server_default="1"),
        sa.Column("updated_by",sa.Uuid(),sa.ForeignKey("users.id",ondelete="RESTRICT"),nullable=False),
        sa.UniqueConstraint("year","product_code_key",name="uq_whatsapp_year_product"),
        sa.CheckConstraint("status IN ('planejado','arte_pronta','publicado')",name="ck_whatsapp_status"),
        sa.CheckConstraint("revision >= 1",name="ck_whatsapp_revision"),
    )
    op.create_table("whatsapp_days_off",
        sa.Column("post_date",sa.DateTime(),primary_key=True),
        sa.Column("reason",sa.String(150),nullable=False,server_default=""),
        sa.Column("created_by",sa.Uuid(),sa.ForeignKey("users.id",ondelete="RESTRICT"),nullable=False),
    )
    op.create_table("instagram_months",
        sa.Column("id",sa.Uuid(),primary_key=True),
        sa.Column("store_code",sa.String(20),sa.ForeignKey("stores.code",ondelete="RESTRICT"),nullable=False),
        sa.Column("year",sa.Integer(),nullable=False),
        sa.Column("month",sa.Integer(),nullable=False),
        sa.Column("planned",sa.Integer(),nullable=False),
        sa.Column("completed",sa.Integer(),nullable=False),
        sa.Column("revision",sa.Integer(),nullable=False,server_default="1"),
        sa.Column("updated_by",sa.Uuid(),sa.ForeignKey("users.id",ondelete="RESTRICT"),nullable=False),
        sa.UniqueConstraint("store_code","year","month",name="uq_instagram_store_month"),
        sa.CheckConstraint("year BETWEEN 2020 AND 2100 AND month BETWEEN 1 AND 12",name="ck_instagram_month"),
        sa.CheckConstraint("planned BETWEEN 0 AND 500 AND completed BETWEEN 0 AND 500",name="ck_instagram_counts"),
        sa.CheckConstraint("revision >= 1",name="ck_instagram_revision"),
    )
    op.create_table("training_records",
        sa.Column("id",sa.Uuid(),primary_key=True),
        sa.Column("store_code",sa.String(20),sa.ForeignKey("stores.code",ondelete="RESTRICT"),nullable=False),
        sa.Column("participant_id",sa.Uuid(),sa.ForeignKey("users.id",ondelete="RESTRICT"),nullable=False),
        sa.Column("procedure",sa.String(40),nullable=False),
        sa.Column("version",sa.String(45),nullable=False),
        sa.Column("title",sa.String(140),nullable=False,server_default=""),
        sa.Column("instructor",sa.String(90),nullable=False),
        sa.Column("happened_on",sa.DateTime(),nullable=False),
        sa.Column("step",sa.String(15),nullable=False),
        sa.Column("note",sa.String(350),nullable=False,server_default=""),
        sa.Column("recorded_by",sa.Uuid(),sa.ForeignKey("users.id",ondelete="RESTRICT"),nullable=False),
        sa.Column("created_at",sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()),
        sa.CheckConstraint("step IN ('participou','pratica')",name="ck_training_step"),
    )
    op.create_index("ix_training_store_on","training_records",["store_code","happened_on"])


def downgrade():
    op.drop_index("ix_training_store_on",table_name="training_records")
    op.drop_table("training_records")
    op.drop_table("instagram_months")
    op.drop_table("whatsapp_days_off")
    op.drop_table("whatsapp_posts")
    op.drop_table("weekly_call_goals")
    op.drop_table("weekly_task_checks")
    op.drop_table("weekly_tasks")
