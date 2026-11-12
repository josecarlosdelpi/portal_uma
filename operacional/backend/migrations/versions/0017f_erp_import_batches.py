"""Lotes compartilhados de importacao do ERP (contrato das frentes A e B).

Revision ID: 0017f
Revises: 0016

CONTRATO COMPARTILHADO — coordenacao com a Frente A (vendas/devolucoes):
- Uma unica definicao de 'erp_import_batches' serve aos dois dominios;
  cada frente grava seu proprio 'domain' ('despesas', 'vendas', 'devolucoes').
- Reimportar o mesmo arquivo (mesmo domain + sha256) nunca duplica dados.
- 'is_current' marca o snapshot vigente por dominio; lotes antigos ficam
  preservados com payload para auditoria e reconciliacao.
- 'coverage' prepara a migracao futura para arquivos por janela movel.
- Sufixo 'f' no id da revisao evita colisao com a serie numerica que a
  Frente A pode ocupar em paralelo (0017...); na integracao, as revisoes
  sao reordenadas ou unidas por uma revisao de merge do Alembic.
"""
from alembic import op
import sqlalchemy as sa

revision = "0017f"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "erp_import_batches",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("domain", sa.String(30), nullable=False),
        sa.Column("channel", sa.String(20), nullable=False),
        sa.Column("drive_file_id", sa.String(120), nullable=True),
        sa.Column("file_name", sa.String(200), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("byte_length", sa.Integer(), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("coverage", sa.String(20), nullable=False, server_default="full_snapshot"),
        sa.Column("period_start", sa.Date(), nullable=True),
        sa.Column("period_end", sa.Date(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("error_detail", sa.String(600), nullable=True),
        sa.Column("quality_flags", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("quality_flag_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("payload", sa.LargeBinary(), nullable=False),
        sa.Column("imported_by", sa.Uuid(),
                  sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("imported_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.func.now()),
        sa.Column("duration_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.UniqueConstraint("domain", "sha256", name="uq_erp_batch_domain_hash"),
        sa.CheckConstraint("status IN ('imported','failed')", name="ck_erp_batch_status"),
        sa.CheckConstraint("channel IN ('manual','drive')", name="ck_erp_batch_channel"),
        sa.CheckConstraint("coverage IN ('full_snapshot','window')", name="ck_erp_batch_coverage"),
    )
    op.create_index("ix_erp_import_batches_domain", "erp_import_batches", ["domain"])


def downgrade() -> None:
    op.drop_index("ix_erp_import_batches_domain", table_name="erp_import_batches")
    op.drop_table("erp_import_batches")
