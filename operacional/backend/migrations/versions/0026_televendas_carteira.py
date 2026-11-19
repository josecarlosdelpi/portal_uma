"""Carteira comercial de televendas: cadastro ampliado, tags, configuracoes e importacao.

- contact_clients ganha cidade, celular, pessoa de contato, aniversario (dia/mes),
  status comercial, tag, ultimo contato, observacoes longas, telefones
  normalizados para busca e controle de revisao;
- a unicidade por nome normalizado deixa de ser bloqueio fisico e passa a ser
  aviso confirmavel, permitindo registros homonimos legitimados pelo usuario;
- contact_attempts ganha canal (ligacao/whatsapp) e baixa de retorno agendado;
- novas tabelas: catalogo de tags, configuracao do modulo e sessoes de
  importacao de planilhas.

Revision ID: 0026
Revises: 0025
"""
from alembic import op
import sqlalchemy as sa

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("uq_client_name_store", "contact_clients", type_="unique")
    op.add_column("contact_clients", sa.Column("phone_norm", sa.String(40)))
    op.add_column("contact_clients", sa.Column("cellphone", sa.String(40)))
    op.add_column("contact_clients", sa.Column("cellphone_norm", sa.String(40)))
    op.add_column("contact_clients", sa.Column("city", sa.String(60)))
    op.add_column("contact_clients", sa.Column("contact_person", sa.String(100)))
    op.add_column("contact_clients", sa.Column("birthday_day", sa.Integer()))
    op.add_column("contact_clients", sa.Column("birthday_month", sa.Integer()))
    op.add_column("contact_clients", sa.Column("status", sa.String(12)))
    op.add_column("contact_clients", sa.Column("tag", sa.String(60)))
    op.add_column("contact_clients", sa.Column("last_contact_on", sa.DateTime()))
    op.add_column("contact_clients", sa.Column("notes", sa.String(2000)))
    op.add_column("contact_clients", sa.Column("revision", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("contact_clients", sa.Column(
        "updated_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT")))
    op.execute(
        "UPDATE contact_clients SET phone_norm = regexp_replace(phone, '\\D', '', 'g') "
        "WHERE phone IS NOT NULL"
    )
    op.create_check_constraint(
        "ck_client_status", "contact_clients",
        "status IS NULL OR status IN ('ativo','inativo','prospect')")
    op.create_check_constraint(
        "ck_client_birthday_day", "contact_clients",
        "birthday_day IS NULL OR birthday_day BETWEEN 1 AND 31")
    op.create_check_constraint(
        "ck_client_birthday_month", "contact_clients",
        "birthday_month IS NULL OR birthday_month BETWEEN 1 AND 12")
    op.create_check_constraint(
        "ck_client_revision", "contact_clients", "revision >= 1")
    op.create_index("ix_contact_clients_store_city", "contact_clients", ["store_code", "city"])
    op.create_index("ix_contact_clients_store_status", "contact_clients", ["store_code", "status"])
    op.create_index("ix_contact_clients_store_name", "contact_clients", ["store_code", "name_key"])

    op.add_column("contact_attempts", sa.Column(
        "channel", sa.String(12), nullable=False, server_default="ligacao"))
    op.add_column("contact_attempts", sa.Column(
        "followup_done_at", sa.DateTime(timezone=True)))
    op.create_check_constraint(
        "ck_call_channel", "contact_attempts", "channel IN ('ligacao','whatsapp')")
    op.create_index("ix_calls_store_next_on", "contact_attempts", ["store_code", "next_on"])

    op.create_table(
        "contact_tags",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(60), nullable=False),
        sa.Column("name_key", sa.String(80), nullable=False),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("name_key", name="uq_contact_tag_name_key"),
    )
    op.create_table(
        "contact_settings",
        sa.Column("key", sa.String(40), primary_key=True),
        sa.Column("inactivity_days", sa.Integer(), nullable=False, server_default="45"),
        sa.Column("updated_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("inactivity_days BETWEEN 1 AND 365", name="ck_settings_inactivity"),
    )
    op.execute("INSERT INTO contact_settings (key, inactivity_days) VALUES ('global', 45)")
    op.create_table(
        "client_import_sessions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("store_code", sa.String(20), sa.ForeignKey("stores.code", ondelete="RESTRICT"), nullable=False),
        sa.Column("filename", sa.String(160), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("state", sa.String(12), nullable=False, server_default="preview"),
        sa.Column("report", sa.JSON()),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("applied_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("state IN ('preview','applied','discarded')", name="ck_import_state"),
    )


def downgrade() -> None:
    duplicates = op.get_bind().execute(sa.text(
        "SELECT count(*) FROM ("
        "SELECT 1 FROM contact_clients "
        "GROUP BY store_code, name_key "
        "HAVING count(*) > 1) homonymos"
    )).scalar()
    if duplicates:
        raise RuntimeError(
            "Downgrade da revisão 0026 bloqueado: existem "
            f"{duplicates} grupo(s) de clientes homônimos por loja, "
            "legítimos nesta versão. A reversão recriaria a unicidade de "
            "nome e destruiria essa distinção. Revise os cadastros "
            "manualmente antes de tentar o downgrade novamente.")
    op.drop_table("client_import_sessions")
    op.drop_table("contact_settings")
    op.drop_table("contact_tags")
    op.drop_index("ix_calls_store_next_on", table_name="contact_attempts")
    op.drop_constraint("ck_call_channel", "contact_attempts", type_="check")
    op.drop_column("contact_attempts", "followup_done_at")
    op.drop_column("contact_attempts", "channel")
    op.drop_index("ix_contact_clients_store_name", table_name="contact_clients")
    op.drop_index("ix_contact_clients_store_status", table_name="contact_clients")
    op.drop_index("ix_contact_clients_store_city", table_name="contact_clients")
    op.drop_constraint("ck_client_revision", "contact_clients", type_="check")
    op.drop_constraint("ck_client_birthday_month", "contact_clients", type_="check")
    op.drop_constraint("ck_client_birthday_day", "contact_clients", type_="check")
    op.drop_constraint("ck_client_status", "contact_clients", type_="check")
    for column in ("updated_by", "revision", "notes", "last_contact_on", "tag",
                   "status", "birthday_month", "birthday_day", "contact_person",
                   "city", "cellphone_norm", "cellphone", "phone_norm"):
        op.drop_column("contact_clients", column)
    op.create_unique_constraint(
        "uq_client_name_store", "contact_clients", ["store_code", "name_key"])
