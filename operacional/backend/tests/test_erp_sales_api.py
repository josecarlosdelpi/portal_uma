"""Testes do piloto ERP comercial com dados sinteticos — sem CNPJs reais."""
from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.auth import current_user
from app.db import get_db
from app.erp_csv import parse_erp_csv
from app.main import app
from app.models import (
    Base, ErpImportBatch, ErpReturnRow, ErpSaleRow, ErpSourceFile,
    Store, User,
)
from tests.access_helpers import seed_admin_access, seed_group

HEADER = ("data;loja;loja_descricao;vendedor;cnpj_cliente;razao_cliente;"
          "produto;quantidade;valor_unitario;valor_total\n")


def sales_csv(*lines: str) -> bytes:
    return (HEADER + "\n".join(lines) + "\n").encode("ascii")


LINE_JOI = "01/10/2026;1;Joinville;1;00000000000   ;CONSUMIDOR;P100;2;50;100"
LINE_JOI2 = "01/10/2026;1;Joinville;2;12345678000199;CLIENTE TESTE A;P200;1;30;30"
LINE_TUB = "02/10/2026;2;Tubarao;4;00000000000;CONSUMIDOR;P100;1;55;55"
LINE_TUB2 = "03/10/2026;2;Tubarao;4;00000000000;CONSUMIDOR;P300;3;10;30"

DEVOLUCOES_CSV = (
    HEADER
    + "02/10/2026;2;Tubarao;0;12345678000199;CLIENTE TESTE A;P100;1;55;55\n"
    + "09/11/2026;1;Joinville;0;98765432000111;CLIENTE TESTE B;P200;1;88;88\n"
).encode("ascii")


@pytest.fixture
def env():
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as db:
        for code in ("JOINVILLE", "ITAJAI", "TUBARAO"):
            db.add(Store(code=code, name=code))
        admin = User(id=uuid4(), auth_subject="test-admin-oidc", display_name="Admin",
                     profile="administrator", active=True, is_superadmin=False)
        seller = User(id=uuid4(), auth_subject="test-seller-oidc", display_name="Seller",
                      profile="seller", active=True, is_superadmin=False)
        viewer = User(id=uuid4(), auth_subject="test-viewer-oidc", display_name="Viewer",
                      profile="seller", active=True, is_superadmin=False)
        db.add_all([admin, seller, viewer])
        db.flush()
        seed_admin_access(db, admin)
        seed_group(
            db, "Vendedores Joinville", ["JOINVILLE"],
            ["sales.view", "sales.revenue.view", "overview.view", "targets.view"],
            [seller, viewer],
        )
        db.commit()

    active_actor = {"current": admin}

    def db_override():
        with Session(engine) as db:
            yield db

    def user_override():
        return active_actor["current"]

    app.dependency_overrides[get_db] = db_override
    app.dependency_overrides[current_user] = user_override
    try:
        with TestClient(app) as client:
            yield client, active_actor, engine, admin, seller, viewer
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def upload(client: TestClient, kind: str, content: bytes, name="arquivo.csv"):
    return client.post(
        f"/api/v1/sales/imports/{kind}",
        files={"file": (name, content, "text/csv")},
    )


def test_parser_brazilian_format():
    parsed = parse_erp_csv(sales_csv(LINE_JOI, LINE_TUB))
    assert parsed.errors == []
    assert len(parsed.rows) == 2
    first = parsed.rows[0]
    assert first.sale_date == date(2026, 10, 1)
    assert first.store_code == "JOINVILLE"
    assert first.customer_cnpj == "00000000000"  # texto, espacos removidos
    assert first.total == Decimal("100")


def test_parser_rejects_bad_header_and_lines():
    assert parse_erp_csv(b"coluna;errada\n").errors
    parsed = parse_erp_csv(sales_csv(
        "32/10/2026;1;Joinville;1;000;X;P;1;1;1",
        "01/10/2026;9;NaoExiste;1;000;X;P;1;1;1",
        LINE_TUB,
    ))
    assert len(parsed.errors) == 2 and len(parsed.rows) == 1


def test_import_rejects_identical_duplicate_and_applies(env):
    client, _, engine, admin, _, _ = env
    content = sales_csv(LINE_JOI, LINE_TUB)
    first = upload(client, "vendas", content)
    assert first.status_code == 200, first.text
    assert first.json()["batch"]["status"] == "APPLIED"
    assert first.json()["batch"]["rows_applied"] == 2

    again = upload(client, "vendas", content)
    assert again.status_code == 200
    assert again.json()["batch"]["status"] == "DUPLICATE"

    with Session(engine) as db:
        assert len(db.scalars(select(ErpSaleRow)).all()) == 2


def test_replace_window_updates_only_covered_scope(env):
    client, _, engine, admin, _, _ = env
    upload(client, "vendas", sales_csv(LINE_JOI, LINE_TUB))
    # Novo arquivo cobre apenas Tubarao no mesmo dia + um dia novo.
    upload(client, "vendas", sales_csv(
        "02/10/2026;2;Tubarao;4;00000000000;CONSUMIDOR;P999;2;80;160",
        LINE_TUB2,
    ))
    with Session(engine) as db:
        rows = db.scalars(select(ErpSaleRow)).all()
        assert len(rows) == 3
        tub = [r for r in rows if r.store_code == "TUBARAO" and r.sale_date == date(2026, 10, 2)]
        assert len(tub) == 1 and tub[0].product_code == "P999"
        joi = [r for r in rows if r.store_code == "JOINVILLE"]
        assert len(joi) == 1 and joi[0].product_code == "P100"


def test_devolucoes_kept_separate(env):
    client, _, engine, *_ = env
    upload(client, "vendas", sales_csv(LINE_JOI, LINE_TUB))
    response = upload(client, "devolucoes", DEVOLUCOES_CSV)
    assert response.status_code == 200
    assert response.json()["batch"]["rows_applied"] == 2
    with Session(engine) as db:
        assert len(db.scalars(select(ErpReturnRow)).all()) == 2
        assert len(db.scalars(select(ErpSaleRow)).all()) == 2


def test_summary_and_daily_scoped_by_permission(env):
    client, identity, _, _, seller, _ = env
    upload(client, "vendas", sales_csv(LINE_JOI, LINE_JOI2, LINE_TUB, LINE_TUB2))
    upload(client, "devolucoes", DEVOLUCOES_CSV)

    admin_summary = client.get("/api/v1/sales/summary?from=2026-10-01&to=2026-10-31")
    assert admin_summary.status_code == 200
    totals = admin_summary.json()["totals"]
    assert Decimal(totals["revenue"]) == Decimal("215")
    assert Decimal(totals["returns_revenue"]) == Decimal("55")

    daily = client.get("/api/v1/sales/daily?from=2026-10-01&to=2026-10-31")
    joi_day = next(d for d in daily.json()["days"]
                   if d["store_code"] == "JOINVILLE" and d["date"] == "2026-10-01")
    assert Decimal(joi_day["revenue"]) == Decimal("130")

    identity["current"] = seller
    scoped = client.get("/api/v1/sales/summary?from=2026-10-01&to=2026-10-31")
    assert scoped.status_code == 200
    assert [s["code"] for s in scoped.json()["stores"]] == ["JOINVILLE"]
    assert client.get("/api/v1/sales/summary?from=2026-10-01&to=2026-10-31&store=TUBARAO").status_code == 403
    assert upload(client, "vendas", sales_csv(LINE_JOI)).status_code == 403
    assert client.post("/api/v1/sales/sync").status_code == 403


def test_top_dimensions_and_customer_cnpj_masking(env):
    client, identity, _, _, seller, _ = env
    upload(client, "vendas", sales_csv(LINE_JOI, LINE_JOI2, LINE_TUB))

    products = client.get("/api/v1/sales/top/products?from=2026-10-01&to=2026-10-31")
    assert products.status_code == 200
    items = products.json()["items"]
    assert items[0]["key"] == "P100" and Decimal(items[0]["revenue"]) == Decimal("155")

    customers = client.get("/api/v1/sales/top/customers?from=2026-10-01&to=2026-10-31")
    entry = next(i for i in customers.json()["items"] if i["key"] == "CLIENTE TESTE A")
    assert entry["customer_cnpj"] == "12345678000199"

    identity["current"] = seller
    sellers = client.get("/api/v1/sales/top/customers?from=2026-10-01&to=2026-10-31")
    assert sellers.status_code == 200
    assert all(i["customer_cnpj"] is None for i in sellers.json()["items"])


def test_seller_without_sales_view_denied(env):
    client, identity, _, _, _, _ = env
    denied = User(id=uuid4(), auth_subject="x", display_name="D", profile="seller",
                  active=True, is_superadmin=False)
    identity["current"] = denied
    # Sem vinculo de loja nem grants, o principal nao enxerga loja alguma.
    assert client.get("/api/v1/sales/status").status_code == 403
    assert client.get("/api/v1/sales/summary?from=2026-10-01&to=2026-10-31").status_code == 403


def test_overview_and_targets_consume_pilot_data(env):
    client, _, _, admin, seller, _ = env
    client.put("/api/v1/targets/JOINVILLE/2026/10/goal",
               json={"amount": "300.00", "expected_revision": 0})
    upload(client, "vendas", sales_csv(LINE_JOI, LINE_JOI2, LINE_TUB))

    overview = client.get("/api/v1/overview/2026/10")
    assert overview.status_code == 200
    body = overview.json()
    assert body["source"]["sales_status"] == "pilot_unverified"
    joi = next(s for s in body["stores"] if s["code"] == "JOINVILLE")
    assert Decimal(joi["revenue"]) == Decimal("130")
    assert Decimal(joi["attainment_percent"]) > Decimal("0")

    targets = client.get("/api/v1/targets/JOINVILLE/2026/10")
    sales = targets.json()["sales"]
    assert sales["status"] == "pilot_unverified"
    assert Decimal(sales["monthly_revenue"]) == Decimal("130")
    assert sales["dynamic_day_plan"] is not None
    assert sales["daily_sales"][0]["date"] == "2026-10-01"
    assert Decimal(sales["daily_sales"][0]["revenue"]) == Decimal("130")


class FakeDriveClient:
    def __init__(self, files: dict[str, tuple[bytes, str]]):
        self.files = files
        self.download_count = 0

    def find_file(self, expected_name: str):
        for name, (content, file_id) in self.files.items():
            if name.lower() == expected_name.lower():
                return {"id": file_id, "name": name, "md5Checksum": name + "-md5",
                        "modifiedTime": "2026-11-11T10:00:00Z"}
        return None

    def download(self, file_id: str) -> bytes:
        self.download_count += 1
        for name, (content, fid) in self.files.items():
            if fid == file_id:
                return content
        raise AssertionError("arquivo desconhecido")


def test_drive_sync_ingests_and_skips_unchanged(env):
    _, _, engine, *_ = env
    fake = FakeDriveClient({
        "Vendas.csv": (sales_csv(LINE_JOI, LINE_TUB), "drv-1"),
        "Devolucoes.csv": (DEVOLUCOES_CSV, "drv-2"),
    })
    with Session(engine) as db:
        from app.erp_sales_service import sales_handlers
        from app.erp_drive import sync_sources
        results = sync_sources(
            db, handlers=sales_handlers(db), client=fake,
            expected_files={"VENDAS": "vendas.csv", "DEVOLUCOES": "devolucoes.csv"},
        )
        assert all(r["status"] == "OK" for r in results)
        assert len(db.scalars(select(ErpSaleRow)).all()) == 2
        assert len(db.scalars(select(ErpReturnRow)).all()) == 2
        states = {s.file_key: s for s in db.scalars(select(ErpSourceFile)).all()}
        assert states["VENDAS"].last_status == "OK"

        again = sync_sources(
            db, handlers=sales_handlers(db), client=fake,
            expected_files={"VENDAS": "vendas.csv", "DEVOLUCOES": "devolucoes.csv"},
        )
        assert all(r["status"] == "SKIPPED" for r in again)
        third = sync_sources(
            db, handlers=sales_handlers(db), client=fake,
            expected_files={"VENDAS": "vendas.csv", "DEVOLUCOES": "devolucoes.csv"},
        )
        assert all(r["status"] == "SKIPPED" for r in third)
        assert fake.download_count == 2


def test_failed_file_creates_failed_batch_without_touching_rows(env):
    client, _, engine, *_ = env
    upload(client, "vendas", sales_csv(LINE_JOI))
    bad = upload(client, "vendas", b"cabecalho;invalido\n")
    assert bad.status_code == 422
    with Session(engine) as db:
        assert len(db.scalars(select(ErpSaleRow)).all()) == 1
        failed = db.scalars(select(ErpImportBatch).where(
            ErpImportBatch.status == "FAILED")).all()
        assert len(failed) == 1 and failed[0].error_summary["errors"]


def test_status_reports_last_sync(env):
    client, *_ = env
    upload(client, "vendas", sales_csv(LINE_JOI))
    status = client.get("/api/v1/sales/status")
    assert status.status_code == 200
    vendas = next(k for k in status.json()["kinds"] if k["kind"] == "VENDAS")
    assert vendas["last_applied_at"] is not None
    assert vendas["rows_applied"] == 1


def test_top_products_sort_by_quantity(env):
    client, *_ = env
    upload(client, "vendas", sales_csv(LINE_JOI, LINE_JOI2, LINE_TUB2))
    by_revenue = client.get(
        "/api/v1/sales/top/products?from=2026-10-01&to=2026-10-31&sort=revenue").json()["items"]
    assert by_revenue[0]["key"] == "P100"  # maior faturamento (100)
    by_quantity = client.get(
        "/api/v1/sales/top/products?from=2026-10-01&to=2026-10-31&sort=quantity").json()["items"]
    keys = [item["key"] for item in by_quantity]
    assert keys == ["P300", "P100", "P200"]  # 3 > 2 > 1 unidades
    assert client.get(
        "/api/v1/sales/top/products?from=2026-10-01&to=2026-10-31&sort=x").status_code == 422
