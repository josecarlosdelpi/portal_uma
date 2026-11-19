"""Apuracao gerencial preliminar (DRE) — leitura sobre snapshots vigentes.

Regras centrais:
- Mesma base dos paineis: Vendas (linhas nao supersedadas), Devolucoes e o
  ultimo lote APPLIED de DESPESAS. Nenhuma importacao ou tabela duplicada.
- Vencimento como referencia provisoria das despesas (pago + aberto);
  nunca pagamento nem emissao como competencia.
- Receita menos custo informado = margem preliminar; devolucoes aparecem
  separadas, sem abater; saldo parcial nunca e chamado de lucro.
- Mes sem dados = 'sem dados', nunca zero. CMV por linha:
  quantidade x custo_unitario arredondado a centavos (ROUND_HALF_UP),
  somado depois — politica unica, testada e divulgada na resposta.
- Classificacao vem de dre_classification_rules (seed da migration 0025);
  com a tabela vazia, caem os padroes embutidos da diretriz.
- Permissao 'dre.view' por loja; coluna compartilhada e consolidado so
  para quem tem escopo autorizado das tres lojas.
"""
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.dre_classification import (
    ALLOC_SHARED, BUCKET_LABELS, BUCKETS, ClassificationRule,
    EXCLUDED_BUCKETS, RESULT_BUCKETS, SHARED_COLUMN, TOTAL_COLUMN,
    DEFAULT_RULES, classify,
)
from app.erp_csv import KIND_DESPESAS, KIND_DEVOLUCOES, KIND_VENDAS
from app.erp_import import _latest_applied, kind_availability, latest_batch
from app.erp_sales_service import period_states
from app.finance_service import money, month_bounds, parse_month
from app.models import (
    DreClassificationRule, ErpImportBatch, ErpReturnRow, ErpSaleRow,
    ErpSourceFile, FinancialObligation, User,
)
from app.operations_service import OperationError
from app.policy import STORE_CODES, can_access
from app.repositories import load_principal

CENT = Decimal("0.01")
DISCLAIMER = ("DRE GERENCIAL PRELIMINAR — valores em validação; "
              "não representa lucro definitivo")
BASIS = "valores financeiros por vencimento, não competência contábil"
ROUNDING_POLICY = (
    "Custo por linha = quantidade x custo_unitario arredondado a centavos "
    "(ROUND_HALF_UP) antes da soma; receitas e despesas somadas em centavos."
)

PAGE_SIZE_MAX = 100
PAGE_SIZE_DEFAULT = 25


def _availability(db: Session, kind: str) -> str:
    state = kind_availability(db, kind)
    return "missing" if state == "never_imported" else state


def _batch_public(batch: ErpImportBatch | None) -> dict | None:
    if batch is None:
        return None
    stamp = batch.applied_at or batch.created_at
    return {
        "imported_at": stamp.isoformat() if stamp else None,
        "file_name": batch.file_name,
        "row_count": batch.rows_applied or batch.rows_total,
        "period_start": batch.period_start.isoformat() if batch.period_start else None,
        "period_end": batch.period_end.isoformat() if batch.period_end else None,
    }


def _pct(value: Decimal | None, base: Decimal | None) -> str | None:
    if value is None or not base or base <= 0:
        return None
    return str((value * 100 / base).quantize(Decimal("0.1")))


class DreService:
    def __init__(self, db: Session, actor: User):
        self.db = db
        self.actor = actor
        self.principal = load_principal(db, actor)

    # ---------- autorizacao ----------

    def stores_with(self, permission: str = "dre.view") -> list[str]:
        return sorted(
            store for store in STORE_CODES
            if can_access(self.principal, permission, store)
        )

    def require_view(self) -> list[str]:
        stores = self.stores_with()
        if not stores:
            raise OperationError(403, "Acesso negado")
        return stores

    def _store_scope(self, requested: str | None) -> tuple[list[str], bool]:
        """Lojas colunadas + flag de visao consolidada completa."""
        allowed = self.require_view()
        if requested in (None, "", "TODAS"):
            return allowed, STORE_CODES <= set(allowed)
        if requested not in STORE_CODES:
            raise OperationError(404, "Loja desconhecida")
        if requested not in allowed:
            raise OperationError(403, "Acesso negado")
        return [requested], False

    # ---------- regras de classificacao ----------

    def _rules(self) -> tuple[list[ClassificationRule], str]:
        """Regras ativas da tabela; vazia -> padroes embutidos da diretriz."""
        rows = self.db.scalars(
            select(DreClassificationRule).where(
                DreClassificationRule.active.is_(True))
            .order_by(DreClassificationRule.created_at, DreClassificationRule.id)
        ).all()
        if not rows:
            return list(DEFAULT_RULES), "default"
        return [
            ClassificationRule(
                account_code=row.account_code,
                supplier_pattern=row.supplier_pattern,
                bucket=row.bucket,
                allocation=row.allocation,
                note=row.note,
            )
            for row in rows
        ], "db"

    def _classify(self, row: FinancialObligation,
                  rules: list[ClassificationRule]):
        return classify(
            category=row.category, account_code=row.account_code,
            supplier_name=row.supplier_name, rules=rules)

    # ---------- fontes ----------

    def _sources(self) -> dict:
        sources = {}
        for kind in (KIND_VENDAS, KIND_DEVOLUCOES, KIND_DESPESAS):
            batch = _latest_applied(self.db, kind)
            latest = latest_batch(self.db, kind)
            entry = {
                "availability": _availability(self.db, kind),
                "last_import": _batch_public(batch),
                "last_status": latest.status if latest else None,
            }
            if kind == KIND_DESPESAS:
                state = self.db.get(ErpSourceFile, KIND_DESPESAS)
                entry["last_check_at"] = (
                    state.last_check_at.isoformat()
                    if state and state.last_check_at else None)
                entry["sync_status"] = state.last_status if state else None
            sources[kind.lower()] = entry
        return sources

    # ---------- apuracao ----------

    def _period(self, month_raw: str | None, mode: str) -> tuple[date, date, str]:
        year, month = parse_month(month_raw)
        if mode not in ("month", "ytd"):
            raise OperationError(422, "Modo inválido; use 'month' ou 'ytd'")
        first, last = month_bounds(year, month)
        if mode == "ytd":
            first = date(year, 1, 1)
        return first, last, f"{year:04d}-{month:02d}"

    def _sales(self, stores: list[str], first: date, last: date) -> tuple[dict, dict]:
        """Receita e custo informado por loja + estado por loja."""
        states, overall = period_states(self.db, stores, first, last)
        result = {code: {"revenue": None, "cmv": None, "rows": 0,
                         "zero_cost_rows": 0} for code in stores}
        if overall == "unavailable" or not stores:
            return result, {"states": states, "overall": overall}
        rows = self.db.execute(
            select(ErpSaleRow.store_code, ErpSaleRow.total,
                   ErpSaleRow.quantity, ErpSaleRow.unit_cost)
            .where(
                ErpSaleRow.store_code.in_(stores),
                ErpSaleRow.sale_date >= first,
                ErpSaleRow.sale_date <= last,
                ErpSaleRow.superseded_at.is_(None),
            )
        ).all()
        for code, total, qty, cost in rows:
            entry = result[code]
            entry["rows"] += 1
            entry["revenue"] = (entry["revenue"] or Decimal(0)) + total
            if cost is None or cost <= 0:
                entry["zero_cost_rows"] += 1
            else:
                line = (qty * cost).quantize(CENT, rounding=ROUND_HALF_UP)
                entry["cmv"] = (entry["cmv"] or Decimal(0)) + line
        for code in stores:
            if states.get(code) == "missing":
                result[code].update(revenue=None, cmv=None)
        return result, {"states": states, "overall": overall}

    def _returns(self, stores: list[str], first: date, last: date) -> dict:
        if _availability(self.db, KIND_DEVOLUCOES) != "current" or not stores:
            return {}
        rows = self.db.execute(
            select(ErpReturnRow.store_code, ErpReturnRow.total)
            .where(
                ErpReturnRow.store_code.in_(stores),
                ErpReturnRow.sale_date >= first,
                ErpReturnRow.sale_date <= last,
                ErpReturnRow.superseded_at.is_(None),
            )
        ).all()
        totals: dict[str, dict] = {}
        for code, total in rows:
            entry = totals.setdefault(code, {"amount": Decimal(0), "rows": 0})
            entry["amount"] += total
            entry["rows"] += 1
        return totals

    def _obligations(self, batch: ErpImportBatch, stores: list[str],
                     first: date, last: date):
        return self.db.scalars(
            select(FinancialObligation).where(
                FinancialObligation.batch_id == batch.id,
                FinancialObligation.store_code.in_(stores),
                FinancialObligation.due_date >= first,
                FinancialObligation.due_date <= last,
            )
        ).all()

    @staticmethod
    def _despesas_coverage(batch: ErpImportBatch | None,
                           first: date, last: date) -> str:
        """Cobertura do periodo pedido dentro da janela do arquivo vigente."""
        if batch is None or batch.period_start is None or batch.period_end is None:
            return "missing"
        if last < batch.period_start or first > batch.period_end:
            return "outside"
        if first < batch.period_start or last > batch.period_end:
            return "partial"
        return "inside"

    def preview(self, month_raw: str | None, mode: str, store: str | None) -> dict:
        stores, full_scope = self._store_scope(store)
        first, last, month_key = self._period(month_raw, mode)
        consolidated = store in (None, "", "TODAS") and full_scope
        # 'UMA' so aparece no consolidado das tres lojas; escopo parcial
        # recebe 'TOTAL' do universo autorizado e loja unica nao tem total.
        total_key = TOTAL_COLUMN if consolidated else "TOTAL"
        columns = list(stores)
        if consolidated:
            columns.append(SHARED_COLUMN)
        if consolidated or len(stores) > 1:
            columns.append(total_key)

        warnings: list[dict] = []
        sources = self._sources()
        vendas_ok = sources["vendas"]["availability"] == "current"
        despesas_state = sources["despesas"]["availability"]

        # ---- vendas / cmv / devolucoes ----
        sales, sales_meta = self._sales(stores, first, last)
        returns = self._returns(stores, first, last)
        if not vendas_ok:
            warnings.append({
                "code": "vendas_indisponiveis",
                "message": "Vendas: arquivo vigente indisponível — aguardando versão válida do ERP.",
            })
        for code in stores:
            state = sales_meta["states"].get(code)
            if state == "missing":
                warnings.append({
                    "code": "mes_sem_vendas",
                    "message": f"{code}: sem vendas registradas no período no arquivo vigente.",
                })
            elif state == "partial":
                warnings.append({
                    "code": "mes_parcial",
                    "message": f"{code}: período parcial — o arquivo de vendas não cobre o mês inteiro.",
                })
        zero_cost = sum(v["zero_cost_rows"] for v in sales.values())
        if zero_cost:
            warnings.append({
                "code": "custo_ausente",
                "message": (f"{zero_cost} linha(s) de venda sem custo informado — "
                            "CMV subestimado; nenhum markup presumido foi aplicado."),
            })
        if _availability(self.db, KIND_DEVOLUCOES) == "current":
            if not returns:
                warnings.append({
                    "code": "devolucoes_vazias",
                    "message": "Devoluções: arquivo vigente sem registros no período.",
                })
        else:
            warnings.append({
                "code": "devolucoes_indisponiveis",
                "message": "Devoluções indisponíveis — arquivo aguardando correção.",
            })

        # ---- despesas classificadas ----
        despesas_batch = _latest_applied(self.db, KIND_DESPESAS)
        coverage = self._despesas_coverage(despesas_batch, first, last)
        rules, rules_origin = self._rules()
        buckets: dict[str, dict[str, Decimal]] = {b: {} for b in BUCKETS}
        counts: dict[str, dict[str, int]] = {b: {} for b in BUCKETS}
        shared_memo = {"amount": Decimal(0), "count": 0}
        expenses_ok = despesas_state == "current" and coverage != "outside"

        if despesas_state != "current":
            warnings.append({
                "code": "despesas_indisponiveis",
                "message": "Despesas: arquivo vigente indisponível — aguardando versão válida do ERP.",
            })
        elif coverage == "outside":
            warnings.append({
                "code": "despesas_fora_cobertura",
                "message": ("Despesas: período fora da cobertura do arquivo vigente "
                            f"({despesas_batch.period_start} a {despesas_batch.period_end})."),
            })
        elif coverage == "partial":
            warnings.append({
                "code": "despesas_parciais",
                "message": "Despesas: período apenas parcialmente coberto pelo arquivo vigente.",
            })

        if expenses_ok and despesas_batch is not None:
            for row in self._obligations(despesas_batch, stores, first, last):
                result = self._classify(row, rules)
                if result.allocation == ALLOC_SHARED:
                    if consolidated:
                        column = SHARED_COLUMN
                    else:
                        shared_memo["amount"] += row.amount
                        shared_memo["count"] += 1
                        continue
                else:
                    column = row.store_code
                buckets[result.bucket][column] = (
                    buckets[result.bucket].get(column, Decimal(0)) + row.amount)
                counts[result.bucket][column] = (
                    counts[result.bucket].get(column, 0) + 1)

        # ---- montagem das linhas ----
        def cell(bucket: str, column: str) -> Decimal | None:
            if not expenses_ok or column == total_key:
                return None
            return buckets[bucket].get(column, Decimal(0))

        revenue = {code: sales[code]["revenue"] for code in stores}
        receita: dict[str, Decimal | None] = {c: revenue.get(c) for c in columns}
        receita[total_key] = (
            sum(v for v in revenue.values() if v is not None)
            if total_key in columns
            and any(v is not None for v in revenue.values()) else None)

        cmv = {code: sales[code]["cmv"] for code in stores}
        cmv_map: dict[str, Decimal | None] = {c: cmv.get(c) for c in columns}
        cmv_map[total_key] = (
            sum(v for v in cmv.values() if v is not None)
            if total_key in columns
            and any(v is not None for v in cmv.values()) else None)

        margem: dict[str, Decimal | None] = {}
        for column in columns:
            if receita.get(column) is None or cmv_map.get(column) is None:
                margem[column] = None
            else:
                margem[column] = receita[column] - cmv_map[column]

        def expense_row(bucket: str) -> dict[str, Decimal | None]:
            values = {column: cell(bucket, column) for column in columns}
            if expenses_ok and total_key in columns:
                values[total_key] = sum(
                    buckets[bucket].get(c, Decimal(0)) for c in columns
                    if c != total_key)
            return values

        comercial = expense_row("despesa_comercial")
        operacional = expense_row("despesa_operacional")
        das = expense_row("das_identificado")

        saldo: dict[str, Decimal | None] = {}
        for column in columns:
            if column == SHARED_COLUMN:
                saldo[column] = None
                continue
            if margem.get(column) is None or not expenses_ok:
                saldo[column] = None
                continue
            if column == total_key:
                subtotal = sum(
                    buckets[b].get(c, Decimal(0)) for b in RESULT_BUCKETS
                    for c in columns if c != total_key)
            else:
                subtotal = sum(
                    buckets[b].get(column, Decimal(0)) for b in RESULT_BUCKETS)
            saldo[column] = margem[column] - subtotal

        if _availability(self.db, KIND_DEVOLUCOES) == "current":
            devol = {column: None for column in columns}
            for code in stores:
                devol[code] = returns.get(code, {}).get("amount", Decimal(0))
            if total_key in columns:
                devol[total_key] = sum(devol[c] for c in stores)
            devol_state = "current"
        else:
            devol = {column: None for column in columns}
            devol_state = _availability(self.db, KIND_DEVOLUCOES)

        rows = [
            {"key": "receita", "label": "Receita de vendas registradas",
             "kind": "input", "values": receita,
             "note": "Somatório de valor_total do arquivo vigente de Vendas."},
            {"key": "devolucoes", "label": "(-) Devoluções registradas (informativo)",
             "kind": "memo", "values": devol, "state": devol_state,
             "note": "Exibidas separadamente, sem abater o resultado."},
            {"key": "cmv", "label": "(-) Custo informado dos produtos vendidos",
             "kind": "input", "values": cmv_map,
             "note": "quantidade x custo_unitario por linha; linhas sem custo geram alerta."},
            {"key": "margem",
             "label": "Margem bruta preliminar (antes de devoluções e tributos)",
             "kind": "subtotal", "values": margem,
             "note": "Não é lucro bruto definitivo."},
            {"key": "despesa_comercial", "label": "(-) Despesas comerciais por vencimento",
             "kind": "input", "bucket": "despesa_comercial",
             "values": comercial, "expandable": True},
            {"key": "despesa_operacional",
             "label": "(-) Despesas operacionais e pessoal por vencimento",
             "kind": "input", "bucket": "despesa_operacional",
             "values": operacional, "expandable": True},
            {"key": "das", "label": "(-) DAS identificado por vencimento",
             "kind": "input", "bucket": "das_identificado", "values": das,
             "expandable": True,
             "note": "Referência tributária provisória; não implica competência da receita."},
            {"key": "saldo", "label": "Saldo gerencial parcial",
             "kind": "subtotal", "values": saldo,
             "note": "Não é lucro líquido; exibido somente com Vendas e Despesas vigentes."},
        ]
        for entry in rows:
            entry["pct"] = {
                column: _pct(entry["values"].get(column), receita.get(column))
                for column in columns
            }

        excluded = []
        for bucket in EXCLUDED_BUCKETS:
            values = {
                column: (buckets[bucket].get(column, Decimal(0)) if expenses_ok else None)
                for column in columns
            }
            if expenses_ok and total_key in columns:
                values[total_key] = sum(
                    buckets[bucket].get(c, Decimal(0)) for c in columns
                    if c != total_key)
            count = sum(counts[bucket].values()) if expenses_ok else 0
            excluded.append({
                "bucket": bucket, "label": BUCKET_LABELS[bucket],
                "amount": money(sum(buckets[bucket].values()))
                    if expenses_ok else None,
                "count": count,
                "expandable": True,
                "columns": {
                    column: money(values[column]) if values[column] is not None else None
                    for column in columns if column != total_key
                },
            })

        if expenses_ok:
            unclassified = next(e for e in excluded if e["bucket"] == "a_classificar")
            if unclassified["count"]:
                warnings.append({
                    "code": "a_classificar",
                    "message": (f"{unclassified['count']} lançamento(s) a classificar: "
                                f"R$ {unclassified['amount']} — fora do saldo parcial."),
                })
            financ = next(e for e in excluded if e["bucket"] == "financiamento")
            if financ["count"]:
                warnings.append({
                    "code": "financiamentos",
                    "message": (f"Financiamentos/amortizações não segregados: "
                                f"R$ {financ['amount']} ({financ['count']} lançamento(s))."),
                })

        return {
            "disclaimer": DISCLAIMER,
            "basis": BASIS,
            "rounding_policy": ROUNDING_POLICY,
            "period": {"month": month_key, "mode": mode,
                       "first": first.isoformat(), "last": last.isoformat()},
            "columns": columns,
            "consolidated": consolidated,
            "store_states": sales_meta["states"],
            "sales_overall": sales_meta["overall"],
            "despesas_coverage": coverage,
            "rows": [
                {**entry,
                 "values": {c: money(v) if v is not None else None
                            for c, v in entry["values"].items()}}
                for entry in rows
            ],
            "excluded": excluded,
            "shared_memo": (
                {"amount": money(shared_memo["amount"]),
                 "count": shared_memo["count"]}
                if shared_memo["count"] else None),
            "sales_quality": {
                code: {"rows": sales[code]["rows"],
                       "zero_cost_rows": sales[code]["zero_cost_rows"]}
                for code in stores
            },
            "warnings": warnings,
            "sources": sources,
            "rules_origin": rules_origin,
        }

    # ---------- detalhamento ----------

    def lines(self, bucket: str, month_raw: str | None, mode: str,
              store: str | None, page: int, page_size: int) -> dict:
        stores, full_scope = self._store_scope(store)
        consolidated = store in (None, "", "TODAS") and full_scope
        first, last, month_key = self._period(month_raw, mode)
        if bucket not in BUCKETS:
            raise OperationError(404, "Grupo desconhecido")
        page = max(1, page)
        page_size = min(max(1, page_size), PAGE_SIZE_MAX)

        batch = _latest_applied(self.db, KIND_DESPESAS)
        availability = _availability(self.db, KIND_DESPESAS)
        empty = {"items": [], "total": 0, "page": page, "page_size": page_size,
                 "has_data": False, "data_state": availability,
                 "period": {"month": month_key, "mode": mode,
                            "first": first.isoformat(), "last": last.isoformat()}}
        if batch is None or availability != "current":
            return empty

        rules, _ = self._rules()
        classified = []
        for row in self._obligations(batch, stores, first, last):
            result = self._classify(row, rules)
            if result.bucket != bucket:
                continue
            if result.allocation == ALLOC_SHARED and not consolidated:
                continue
            classified.append((row, result))
        classified.sort(key=lambda pair: (pair[0].due_date, str(pair[0].id)))
        total = len(classified)
        window = classified[(page - 1) * page_size: page * page_size]
        return {
            "items": [{
                "id": str(row.id),
                "supplier_name": row.supplier_name,
                "account_code": row.account_code,
                "account_description": row.account_description,
                "store_code": row.store_code,
                "allocation": (SHARED_COLUMN
                             if result.allocation == ALLOC_SHARED
                             else row.store_code),
                "allocation_provisional": True,
                "due_date": row.due_date.isoformat(),
                "paid_at": row.paid_at.isoformat() if row.paid_at else None,
                "status": row.status,
                "amount": money(row.amount),
                "rule": result.reason,
                "rule_note": result.rule.note if result.rule else None,
                "document_number": row.document_number,
                "source_row": row.source_row,
            } for row, result in window],
            "total": total,
            "sum_amount": money(sum(r.amount for r, _ in classified)),
            "page": page, "page_size": page_size,
            "has_data": True, "data_state": "current",
            "period": {"month": month_key, "mode": mode,
                       "first": first.isoformat(), "last": last.isoformat()},
        }

    # ---------- visao da classificacao aplicada ----------

    def classification_view(self) -> dict:
        stores, _ = self._store_scope(None)
        rules, origin = self._rules()
        batch = _latest_applied(self.db, KIND_DESPESAS)
        availability = _availability(self.db, KIND_DESPESAS)

        accounts: dict[str, dict] = {}
        if batch is not None and availability == "current":
            rows = self.db.execute(
                select(
                    FinancialObligation.account_code,
                    FinancialObligation.account_description,
                    FinancialObligation.category,
                    FinancialObligation.supplier_name,
                    FinancialObligation.store_code,
                    FinancialObligation.amount,
                ).where(
                    FinancialObligation.batch_id == batch.id,
                    FinancialObligation.store_code.in_(stores),
                )
            ).all()
            for code, desc, category, supplier, store_code, amount in rows:
                key = (code or "").strip() or "—"
                entry = accounts.setdefault(
                    key, {"account_code": code, "account_description": desc,
                          "count": 0, "amount": Decimal(0),
                          "buckets": {}, "categories": set()})
                entry["count"] += 1
                entry["amount"] += amount
                entry["categories"].add(category)
                if desc and not entry["account_description"]:
                    entry["account_description"] = desc
                result = classify(
                    category=category, account_code=code,
                    supplier_name=supplier, rules=rules)
                bucket = entry["buckets"].setdefault(
                    result.bucket, {"count": 0, "amount": Decimal(0)})
                bucket["count"] += 1
                bucket["amount"] += amount

        account_list = []
        for key, entry in sorted(accounts.items()):
            dominant = max(
                entry["buckets"].items(), key=lambda kv: kv[1]["amount"])
            account_list.append({
                "account_code": entry["account_code"],
                "account_description": entry["account_description"],
                "count": entry["count"],
                "amount": money(entry["amount"]),
                "dominant_bucket": dominant[0],
                "dominant_amount": money(dominant[1]["amount"]),
                "dominant_count": dominant[1]["count"],
                "mixed": len(entry["buckets"]) > 1,
                "buckets": {
                    b: {"count": v["count"], "amount": money(v["amount"])}
                    for b, v in entry["buckets"].items()
                },
                "category_flags": sorted(entry["categories"]),
            })

        return {
            "disclaimer": DISCLAIMER,
            "rules_origin": origin,
            "editable": False,
            "rules": [
                {"account_code": rule.account_code,
                 "supplier_pattern": rule.supplier_pattern,
                 "bucket": rule.bucket, "allocation": rule.allocation,
                 "note": rule.note}
                for rule in rules
            ],
            "accounts": account_list,
            "data_state": availability,
            "last_import": _batch_public(batch),
            "bucket_labels": BUCKET_LABELS,
        }
