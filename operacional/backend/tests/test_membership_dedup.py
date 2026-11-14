"""Deduplicacao da migracao 0021: relatorio de multiplos vinculos e
criterio deterministico de qual grupo e mantido."""
import importlib.util
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

MIGRATION = (Path(__file__).resolve().parent.parent
             / "migrations" / "versions" / "0021_membership_unique.py")

_SCHEMA = """
CREATE TABLE users (id TEXT PRIMARY KEY, display_name TEXT NOT NULL);
CREATE TABLE access_groups (id TEXT PRIMARY KEY, name TEXT NOT NULL, active BOOLEAN NOT NULL);
CREATE TABLE group_memberships (
    user_id TEXT NOT NULL REFERENCES users(id),
    group_id TEXT NOT NULL REFERENCES access_groups(id),
    PRIMARY KEY (user_id, group_id));
"""


def _load_migration():
    spec = importlib.util.spec_from_file_location("mig0021", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def conn():
    """Base 'antiga' sem a constraint de unicidade: duplicatas possiveis."""
    engine = create_engine("sqlite+pysqlite://",
                           connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    with engine.begin() as connection:
        for statement in _SCHEMA.strip().split(";"):
            connection.execute(text(statement.strip()))
        uid, clean_id = str(uuid4()), str(uuid4())
        adm, vend, zzz = str(uuid4()), str(uuid4()), str(uuid4())
        connection.execute(text(
            "INSERT INTO users (id, display_name) VALUES "
            "(:u, 'Usuario Duplicado'), (:c, 'Usuario Limpo')"),
            {"u": uid, "c": clean_id})
        connection.execute(text(
            "INSERT INTO access_groups (id, name, active) VALUES "
            "(:a, 'Administradores', 1), (:v, 'Vendedores', 1), (:z, 'Zzz Outro', 1)"),
            {"a": adm, "v": vend, "z": zzz})
        # usuario com 3 vinculos -> dedup manteria 'Administradores' (menor nome)
        for gid in (vend, adm, zzz):
            connection.execute(text(
                "INSERT INTO group_memberships (user_id, group_id) VALUES (:u, :g)"),
                {"u": uid, "g": gid})
        connection.execute(text(
            "INSERT INTO group_memberships (user_id, group_id) VALUES (:u, :g)"),
            {"u": clean_id, "g": vend})
        yield connection, uid, clean_id, adm, vend, zzz
    engine.dispose()


def test_report_lists_duplicate_users_with_kept_and_removed(conn):
    connection, uid, clean_id, *_ = conn
    mig = _load_migration()
    report = mig.multi_memberships(connection)
    assert len(report) == 1
    entry = report[0]
    assert entry["user_id"] == uid
    assert entry["total"] == 3
    assert entry["kept"]["name"] == "Administradores"
    assert {g["name"] for g in entry["removed"]} == {"Vendedores", "Zzz Outro"}
    # usuario com um unico vinculo nao aparece no relatorio
    assert clean_id not in {e["user_id"] for e in report}


def test_dedup_keeps_alphabetically_first_group(conn):
    connection, uid, clean_id, adm, *_ = conn
    mig = _load_migration()
    assert mig.dedup_memberships(connection) == 2
    remaining = connection.execute(text(
        "SELECT user_id, group_id FROM group_memberships")).all()
    assert (uid, adm) in remaining
    assert len([r for r in remaining if r[0] == uid]) == 1
    # o usuario limpo segue intacto
    assert len([r for r in remaining if r[0] == clean_id]) == 1
    assert mig.multi_memberships(connection) == []


def test_report_empty_when_no_duplicates(conn):
    connection, _, clean_id, *_ = conn
    connection.execute(
        text("DELETE FROM group_memberships WHERE user_id != :u"),
        {"u": clean_id})
    mig = _load_migration()
    assert mig.multi_memberships(connection) == []
    assert mig.dedup_memberships(connection) == 0
