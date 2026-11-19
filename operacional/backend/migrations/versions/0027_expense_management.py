"""Gestao de Despesas: categorias, regras por fornecedor e classificacoes

Revision ID: 0027
Revises: 0025
Create Date: 2026-11-19

Estrutura persistente e independente dos snapshots do ERP:
- expense_categories: dimensao gerencial compartilhada entre as lojas;
- supplier_category_rules: regra automatica por fornecedor (doc ou nome
  normalizado), com abrangencia por loja ou UMA;
- expense_line_classifications: classificacao manual por 'fingerprint'
  dos campos identitarios do lancamento — nunca pelo id interno, que
  muda a cada importacao.

ATENCAO — DIVERGENCIA 0026/0027 (estrategia documentada, nao executar
sem autorizacao): esta revisao e irma da 0026 (televendas), ambas
descendentes de 0025. Ao integrar as duas linhas de desenvolvimento:

1. BANCO NOVO: com ambos os arquivos presentes no diretorio versions/,
   `alembic heads` mostra dois heads (0026, 0027) e `alembic upgrade
   head` falha. A solucao canonica e criar UMA migration de merge:
       alembic merge -m "merge televendas + gestao de despesas" 0026 0027
   que gera uma revisao vazia com down_revision=("0026","0027"). Nenhuma
   das duas frentes e alterada — apenas um no de uniao e adicionado.
   Depois disso `alembic upgrade head` aplica toda a cadeia em ordem
   qualquer (as tabelas sao disjuntas, nao ha conflito de DDL).

2. BANCO EXISTENTE (ja em 0026 ou 0027): mesma solucao — adicionar o
   arquivo de merge em versions/ e rodar `alembic upgrade head`. O
   Alembic detecta o head corrente e aplica apenas as revisoes
   pendentes + o no de merge; nenhum dado e recriado nem perdido.

3. BANCO COM alembic_version APONTANDO PARA REVISAO AUSENTE (ex.: banco
   local estampado em 0026 rodando a branch da 0027, sem o arquivo):
   NUNCA editar a tabela alembic_version como solucao permanente. O
   workaround local usado em desenvolvimento (`alembic stamp 0025` +
   `upgrade head`) apenas reancora o ponteiro e NAO desfaz DDL — as
   tabelas televendas permanecem intactas no banco. Em ambiente real,
   a correcao definitiva e publicar juntos todos os arquivos de
   versions/ (0026 + 0027 + merge) e rodar `alembic upgrade head`,
   que traz o banco ao head unico sem perda de dados.

4. PROIBIDO: reescrever o down_revision de 0026 ou 0027 para linearizar
   a cadeia (quebraria bancos ja migrados em qualquer um dos ramos) e
   executar `alembic merge`/upgrade em producao sem autorizacao.
"""
from alembic import op
import sqlalchemy as sa


revision = "0027"
down_revision = "0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "expense_categories",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("name_norm", sa.String(80), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("name_norm", name="uq_expense_category_norm"),
    )

    op.create_table(
        "supplier_category_rules",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("supplier_key", sa.String(220), nullable=False),
        sa.Column("supplier_label", sa.String(220), nullable=False),
        sa.Column("store_code", sa.String(20), sa.ForeignKey("stores.code", ondelete="RESTRICT")),
        sa.Column("category_id", sa.Uuid(), sa.ForeignKey("expense_categories.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_supplier_rule_key", "supplier_category_rules", ["supplier_key"])

    op.create_table(
        "expense_line_classifications",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("fingerprint", sa.String(64), nullable=False, unique=True),
        sa.Column("category_id", sa.Uuid(), sa.ForeignKey("expense_categories.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("store_code", sa.String(20), sa.ForeignKey("stores.code", ondelete="RESTRICT"), nullable=False),
        sa.Column("supplier_key", sa.String(220), nullable=False),
        sa.Column("supplier_label", sa.String(220), nullable=False),
        sa.Column("document_number", sa.String(30)),
        sa.Column("installment_number", sa.String(10)),
        sa.Column("issued_at", sa.Date()),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("matched_rows", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("status IN ('active','orphan')",
                           name="ck_expense_line_class_status"),
    )


def downgrade() -> None:
    op.drop_table("expense_line_classifications")
    op.drop_index("ix_supplier_rule_key", table_name="supplier_category_rules")
    op.drop_table("supplier_category_rules")
    op.drop_table("expense_categories")
