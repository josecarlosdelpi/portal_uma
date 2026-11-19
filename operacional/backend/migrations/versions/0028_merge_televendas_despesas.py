"""Merge de ramos: televendas (0026) + gestao de despesas (0027).

No de uniao sem DDL: une as duas linhas de desenvolvimento em um head
unico. Bancos novos aplicam a cadeia completa em ordem qualquer (as
tabelas sao disjuntas); bancos existentes em 0026 ou 0027 aplicam
apenas este no.

Bancos que possuam fisicamente as alteracoes das duas frentes mas com
alembic_version preso em uma delas (ex.: 0027 com tabelas televendas
ja existentes) devem ser reancorados com `alembic stamp` para a revisao
cuja estrutura fisica esteja completa, e entao `upgrade head` aplica
este no sem reexecutar DDL.

Revision ID: 0028
Revises: 0026, 0027
"""

revision = "0028"
down_revision = ("0026", "0027")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
