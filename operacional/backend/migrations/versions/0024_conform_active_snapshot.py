"""Conformar conjunto ativo ao snapshot vigente

Revision ID: 0024
Revises: 0023
Create Date: 2026-02-20

A nova regra de integracao torna o arquivo CSV vigente a unica fonte ativa
de cada tipo. Linhas ativas que pertencem a lotes anteriores ao ultimo
APPLIED recebem superseded_at — ficam no banco para auditoria/recuperacao,
mas deixam de alimentar os paineis. Idempotente: linhas ja conformes nao
sao tocadas.
"""
from alembic import op

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def _conform(table: str, kind: str) -> None:
    op.execute(
        f"""
        UPDATE {table}
        SET superseded_at = now()
        WHERE superseded_at IS NULL
          AND batch_id <> (
              SELECT id FROM erp_import_batches
              WHERE kind = '{kind}' AND status = 'APPLIED'
              ORDER BY applied_at DESC, created_at DESC
              LIMIT 1
          )
          AND EXISTS (
              SELECT 1 FROM erp_import_batches
              WHERE kind = '{kind}' AND status = 'APPLIED'
          )
        """
    )


def upgrade() -> None:
    _conform("erp_sale_rows", "VENDAS")
    _conform("erp_return_rows", "DEVOLUCOES")


def downgrade() -> None:
    # Irreversivel por desenho: nao restaura o estado misto anterior.
    pass
