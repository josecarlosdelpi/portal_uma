"""Fluxo de Caixa Estimado — leitura sobre snapshots vigentes.

Regras centrais:
- Entradas = soma de valor_total das vendas vigentes do periodo. Sao vendas
  registradas, NAO recebimentos: nenhum prazo, parcela ou data bancaria e
  presumido. A origem fica isolada em _entries() para permitir a troca
  futura por um arquivo de recebimentos sem somar as duas fontes.
- Saidas = obrigacoes do lote vigente de DESPESAS com status 'pago' e
  paid_at dentro do periodo. Inclui TODAS as naturezas (operacionais,
  compras p/ revenda, financiamentos, imobilizado, a classificar).
  Vencimento nunca substitui a data efetiva de pagamento; o CMV da DRE
  nao entra aqui — compras pagas ja estao nos pagamentos.
- Saldo = Entradas - Saidas, com abertura fixa em R$ 0,00. Nao e saldo
  bancario nem conciliacao.
- Ausencia de vendas = 'sem dados', nunca zero. Cobertura parcial dos
  arquivos e sinalizada; devolucoes sao apenas informativas, jamais
  abatidas. Linhas identicas nunca sao deduplicadas.
- Permissao 'cashflow.view' por loja; compartilhado e consolidado so
  para quem tem escopo autorizado das tres lojas.
"""
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.dre_classification import (
    ALLOC_SHARED, BUCKET_LABELS, BUCKETS, ClassificationRule,
    SHARED_COLUMN, TOTAL_COLUMN, DEFAULT_RULES, classify,
)
from app.erp_csv import KIND_DESPESAS, KIND_DEVOLUCOES, KIND_VENDAS
from app.erp_import import _latest_applied, kind_availability, latest_batch
from app.erp_sales_service import period_states
from app.finance_service import money
from app.models import (
    DreClassificationRule, ErpImportBatch, ErpReturnRow, ErpSaleRow,
    ErpSourceFile, FinancialObligation, User,
)
from app.operations_service import OperationError
from app.policy import STORE_CODES, can_access
from app.repositories import load_principal

DISCLAIMER = ("FLUXO DE CAIXA ESTIMADO — vendas registradas menos pagamentos "
              "efetivos; não é saldo bancário real")
OPENING_BALANCE = "0.00"
PAGE_SIZE_MAX = 100

# Saidas exibem todas as naturezas na ordem gerencial (nao ha CMV aqui).
CATEGORY_ORDER = (
    "despesa_operacional", "despesa_comercial", "das_identificado",
    "compra_revenda", "financiamento", "imobilizado", "a_classificar",
)

METHODOLOGY = [
    "Saldo inicial do período sempre R$ 0,00 — o saldo é a diferença entre "
    "movimentações do intervalo, não uma soma de saldos bancários.",
    "Entradas = vendas registradas no Vendas.csv vigente — estimativa, não "
    "recebimento efetivo; prazos de cartão e datas bancárias não são presumidos.",
    "Saídas = lançamentos do Despesas.csv vigente com situação 'Pago' e data "
    "efetiva no período — todas as naturezas, valor líquido do pagamento.",
    "A cobertura declarada do Despesas.csv usa vencimentos e NÃO confirma que "
    "todos os pagamentos do período estejam no arquivo — saídas são sempre "
    "indicativas dos registros vigentes.",
    "Pagamentos seguem a atribuição de loja do ERP: a UMA centraliza parte "
    "das operações em Joinville, então saídas por loja não representam "
    "necessariamente o consumo econômico de cada unidade.",
    "Despesas compartilhadas aparecem na coluna própria e entram no "
    "consolidado sem rateio — por isso a soma das lojas difere do total UMA.",
    "Devoluções são informativas: não se presume reembolso e nada é abatido "
    "das entradas automaticamente.",
    "Lançamentos idênticos são preservados — nenhuma deduplicação por "
    "valores ou campos iguais.",
    "Preparado para recebimentos reais: quando o ERP enviar o arquivo de "
    "recebimentos, ele substituirá a fonte de entradas — nunca será somado "
    "às vendas.",
]


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


def _months_in(first: date, last: date) -> list[tuple[int, int, date, date]]:
    """Meses tocados pelo intervalo, com o recorte exato de cada um."""
    months = []
    year, month = first.year, first.month
    while (year, month) <= (last.year, last.month):
        m_first = date(year, month, 1)
        if month == 12:
            m_last = date(year, 12, 31)
            year, month = year + 1, 1
        else:
            m_last = date(year, month + 1, 1) - date.resolution
            month += 1
        months.append((m_first.year, m_first.month,
                       max(m_first, first), min(m_last, last)))
    return months


class CashflowService:
    def __init__(self, db: Session, actor: User):
        self.db = db
        self.actor = actor
        self.principal = load_principal(db, actor)

    # ---------- autorizacao ----------

    def stores_with(self, permission: str = "cashflow.view") -> list[str]:
        return sorted(
            store for store in STORE_CODES
            if can_access(self.principal, permission, store)
        )

    def _store_scope(self, requested: str | None) -> tuple[list[str], bool]:
        allowed = self.stores_with()
        if not allowed:
            raise OperationError(403, "Acesso negado")
        if requested in (None, "", "TODAS"):
            return allowed, STORE_CODES <= set(allowed)
        if requested not in STORE_CODES:
            raise OperationError(404, "Loja desconhecida")
        if requested not in allowed:
            raise OperationError(403, "Acesso negado")
        return [requested], False

    # ---------- regras de classificacao (mesma base da DRE) ----------

    def _rules(self) -> list[ClassificationRule]:
        rows = self.db.scalars(
            select(DreClassificationRule).where(
                DreClassificationRule.active.is_(True))
            .order_by(DreClassificationRule.created_at, DreClassificationRule.id)
        ).all()
        if not rows:
            return list(DEFAULT_RULES)
        return [
            ClassificationRule(
                account_code=row.account_code,
                supplier_pattern=row.supplier_pattern,
                bucket=row.bucket,
                allocation=row.allocation,
                note=row.note,
            )
            for row in rows
        ]

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

    # ---------- periodo ----------

    @staticmethod
    def _range(date_from: str | None, date_to: str | None) -> tuple[date, date]:
        try:
            first = date.fromisoformat((date_from or "").strip())
            last = date.fromisoformat((date_to or "").strip())
        except ValueError as exc:
            raise OperationError(
                422, "Informe o período como date_from/date_to em AAAA-MM-DD.") from exc
        if first > last:
            raise OperationError(422, "Data inicial posterior à final.")
        if (last - first).days > 366 * 3:
            raise OperationError(422, "Período máximo de 3 anos.")
        return first, last

    # ---------- entradas (origem isolada: vendas vigentes) ----------

    def _entries(self, stores: list[str], first: date, last: date) -> tuple[dict, dict]:
        """Entradas estimadas por loja + estado de cobertura das vendas.

        FONTE SUBSTITUIVEL: hoje 'vendas_registradas'. Ao existir arquivo de
        recebimentos, este metodo passa a ler a nova fonte — nunca soma as duas.
        """
        states, overall = period_states(self.db, stores, first, last)
        result = {code: {"amount": None, "rows": 0} for code in stores}
        if overall == "unavailable" or not stores:
            return result, {"states": states, "overall": overall}
        rows = self.db.execute(
            select(ErpSaleRow.store_code, ErpSaleRow.total)
            .where(
                ErpSaleRow.store_code.in_(stores),
                ErpSaleRow.sale_date >= first,
                ErpSaleRow.sale_date <= last,
                ErpSaleRow.superseded_at.is_(None),
            )
        ).all()
        for code, total in rows:
            entry = result[code]
            entry["rows"] += 1
            entry["amount"] = (entry["amount"] or Decimal(0)) + total
        for code in stores:
            if states.get(code) == "missing":
                result[code]["amount"] = None
        return result, {"states": states, "overall": overall}

    # ---------- saidas (pagamentos efetivos do lote vigente) ----------

    def _payments(self, batch: ErpImportBatch, stores: list[str],
                  first: date, last: date):
        return self.db.scalars(
            select(FinancialObligation).where(
                FinancialObligation.batch_id == batch.id,
                FinancialObligation.store_code.in_(stores),
                FinancialObligation.status == "pago",
                FinancialObligation.paid_at >= first,
                FinancialObligation.paid_at <= last,
            )
        ).all()

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

    # ---------- preview ----------

    def preview(self, date_from: str | None, date_to: str | None,
                store: str | None) -> dict:
        stores, full_scope = self._store_scope(store)
        first, last = self._range(date_from, date_to)
        consolidated = store in (None, "", "TODAS") and full_scope
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

        entries, sales_meta = self._entries(stores, first, last)
        if not vendas_ok:
            warnings.append({
                "code": "vendas_indisponiveis",
                "message": "Vendas: arquivo vigente indisponível — aguardando versão válida do ERP.",
            })
        for code in stores:
            state = sales_meta["states"].get(code)
            if state == "missing":
                warnings.append({
                    "code": "periodo_sem_vendas",
                    "message": f"{code}: sem vendas registradas no período no arquivo vigente.",
                })
            elif state == "partial":
                warnings.append({
                    "code": "periodo_parcial",
                    "message": (f"{code}: período parcial — o arquivo de vendas não cobre "
                                "o intervalo inteiro; o saldo não representa período completo."),
                })

        # ---- saidas por pagamento efetivo ----
        despesas_batch = _latest_applied(self.db, KIND_DESPESAS)
        payments_ok = despesas_state == "current" and despesas_batch is not None
        rules = self._rules()
        exits: dict[str, Decimal] = {}
        by_bucket: dict[str, dict[str, Decimal]] = {b: {} for b in BUCKETS}
        counts: dict[str, dict[str, int]] = {b: {} for b in BUCKETS}
        shared_memo = {"amount": Decimal(0), "count": 0}
        payment_rows = 0

        if not payments_ok:
            warnings.append({
                "code": "despesas_indisponiveis",
                "message": "Despesas: arquivo vigente indisponível — saídas não apuráveis.",
            })
        else:
            period_hint = ""
            if (despesas_batch.period_start and despesas_batch.period_end
                    and (last < despesas_batch.period_start
                         or first > despesas_batch.period_end)):
                period_hint = "fora"
            elif (despesas_batch.period_start and despesas_batch.period_end
                    and (first < despesas_batch.period_start
                         or last > despesas_batch.period_end)):
                period_hint = "parcial"
            if period_hint == "fora":
                warnings.append({
                    "code": "despesas_fora_cobertura",
                    "message": ("Despesas: período fora da cobertura declarada do arquivo "
                                "vigente — saídas podem estar incompletas."),
                })
            elif period_hint == "parcial":
                warnings.append({
                    "code": "despesas_parciais",
                    "message": ("Despesas: período apenas parcialmente coberto pelo arquivo "
                                "vigente — saídas podem estar incompletas."),
                })

            for row in self._payments(despesas_batch, stores, first, last):
                payment_rows += 1
                result = classify(
                    category=row.category, account_code=row.account_code,
                    supplier_name=row.supplier_name, rules=rules)
                if result.allocation == ALLOC_SHARED:
                    if consolidated:
                        column = SHARED_COLUMN
                    else:
                        shared_memo["amount"] += row.amount
                        shared_memo["count"] += 1
                        continue
                else:
                    column = row.store_code
                exits[column] = exits.get(column, Decimal(0)) + row.amount
                by_bucket[result.bucket][column] = (
                    by_bucket[result.bucket].get(column, Decimal(0)) + row.amount)
                counts[result.bucket][column] = (
                    counts[result.bucket].get(column, 0) + 1)

        # ---- colunas de sintese ----
        summary_entries = {
            c: (entries.get(c, {}).get("amount") if c in stores
                else Decimal(0) if c == SHARED_COLUMN else None)
            for c in columns
        }
        summary_exits = {
            c: (exits.get(c, Decimal(0)) if payments_ok else None)
            for c in columns if c != total_key
        }
        summary_balance: dict[str, Decimal | None] = {}
        for c in columns:
            if c == total_key:
                continue
            if summary_entries.get(c) is None or summary_exits.get(c) is None:
                summary_balance[c] = None
            else:
                summary_balance[c] = (
                    (summary_entries[c] or Decimal(0))
                    - (summary_exits[c] or Decimal(0)))
        if total_key in columns:
            e_all = [v for v in summary_entries.values() if v is not None]
            s_all = [v for v in summary_exits.values() if v is not None]
            summary_entries[total_key] = (
                sum(e_all) if e_all and vendas_ok else None)
            summary_exits[total_key] = sum(s_all) if payments_ok else None
            summary_balance[total_key] = (
                (summary_entries[total_key] or Decimal(0))
                - (summary_exits[total_key] or Decimal(0))
                if summary_entries[total_key] is not None
                and summary_exits[total_key] is not None else None)

        # ---- confiabilidade do saldo por coluna ----
        # complete: entradas+saidas apuradas e vendas cobrem o periodo todo;
        # partial:  computavel, mas com ressalvas (vendas parciais, coluna
        #           compartilhada sem entradas proprias ou consolidado com
        #           membro incompleto) — numeros visiveis, jamais "completo";
        # unavailable: sem base para a diferenca (sem vendas ou fonte falha).
        balance_state: dict[str, str] = {}
        for c in columns:
            if c == total_key:
                continue
            if summary_balance.get(c) is None:
                balance_state[c] = "unavailable"
            elif c == SHARED_COLUMN:
                balance_state[c] = "partial"
            else:
                st = sales_meta["states"].get(c)
                balance_state[c] = (
                    "unavailable" if st in ("missing", "unavailable")
                    else "partial" if st == "partial" else "complete")
        if total_key in columns:
            members = [balance_state[c] for c in columns if c != total_key]
            if all(s == "unavailable" for s in members):
                balance_state[total_key] = "unavailable"
            elif any(s != "complete" for s in members):
                balance_state[total_key] = "partial"
            else:
                balance_state[total_key] = "complete"

        # ---- evolucao mensal (escopo agregado) ----
        monthly = []
        for y, m, m_first, m_last in _months_in(first, last):
            m_entries, m_meta = self._entries(stores, m_first, m_last)
            e_val = (sum(v["amount"] for v in m_entries.values()
                         if v["amount"] is not None)
                     if any(v["amount"] is not None for v in m_entries.values())
                     else None)
            s_val = None
            p_rows = 0
            if payments_ok:
                s_acc = Decimal(0)
                for row in self._payments(despesas_batch, stores, m_first, m_last):
                    p_rows += 1
                    result = classify(
                        category=row.category, account_code=row.account_code,
                        supplier_name=row.supplier_name, rules=rules)
                    if result.allocation == ALLOC_SHARED and not consolidated:
                        continue
                    s_acc += row.amount
                s_val = s_acc
            monthly.append({
                "month": f"{y:04d}-{m:02d}",
                "entries": money(e_val) if e_val is not None else None,
                "exits": money(s_val) if s_val is not None else None,
                "balance": (money(e_val - s_val)
                            if e_val is not None and s_val is not None else None),
                "balance_state": (
                    "unavailable" if e_val is None or s_val is None
                    else "partial" if m_meta["overall"] != "current"
                    else "complete"),
                "vendas_state": m_meta["overall"],
                "sales_rows": sum(v["rows"] for v in m_entries.values()),
                "payment_rows": p_rows,
            })

        # ---- composicao dos pagamentos ----
        payments = []
        for bucket in CATEGORY_ORDER:
            values = {c: (by_bucket[bucket].get(c) if payments_ok else None)
                      for c in columns if c != total_key}
            payments.append({
                "bucket": bucket,
                "label": BUCKET_LABELS[bucket],
                "columns": {c: money(v) if v is not None else None
                            for c, v in values.items()},
                "amount": money(sum(by_bucket[bucket].values()))
                    if payments_ok else None,
                "count": sum(counts[bucket].values()) if payments_ok else 0,
                "expandable": True,
            })

        # ---- devolucoes (informativo) ----
        returns = self._returns(stores, first, last)
        returns_view = None
        if _availability(self.db, KIND_DEVOLUCOES) == "current":
            returns_view = {
                "state": "current",
                "columns": {c: money(returns.get(c, {}).get("amount", Decimal(0)))
                            for c in stores},
                "count": sum(v["rows"] for v in returns.values()),
            }
        else:
            returns_view = {"state": _availability(self.db, KIND_DEVOLUCOES),
                            "columns": {}, "count": 0}

        if returns_view["state"] != "current":
            warnings.append({
                "code": "devolucoes_indisponiveis",
                "message": "Devoluções indisponíveis — exibidas apenas como informação quando vigentes.",
            })

        return {
            "disclaimer": DISCLAIMER,
            "opening_balance": OPENING_BALANCE,
            "entries_source": {
                "kind": "vendas_registradas",
                "label": "Vendas registradas — estimativa de entradas",
                "note": ("Não são recebimentos efetivos. Quando existir arquivo de "
                         "recebimentos, ele substituirá esta fonte sem soma dupla."),
                "replaceable": True,
            },
            "period": {"first": first.isoformat(), "last": last.isoformat(),
                       "months": [f"{y:04d}-{m:02d}" for y, m, _, _ in _months_in(first, last)]},
            "columns": columns,
            "consolidated": consolidated,
            "store_states": sales_meta["states"],
            "sales_overall": sales_meta["overall"],
            "summary": {
                "entries": {c: money(v) if v is not None else None
                            for c, v in summary_entries.items()},
                "exits": {c: money(v) if v is not None else None
                          for c, v in summary_exits.items()},
                "balance": {c: money(v) if v is not None else None
                            for c, v in summary_balance.items()},
                "balance_state": balance_state,
            },
            # paid_at e real, mas a janela do arquivo usa vencimentos — a
            # integralidade dos pagamentos do periodo nao pode ser confirmada.
            "payments_coverage": "indicative",
            "sales_rows": sum(v["rows"] for v in entries.values()),
            "payment_rows": payment_rows,
            "monthly": monthly,
            "payments": payments,
            "returns": returns_view,
            "shared_memo": (
                {"amount": money(shared_memo["amount"]),
                 "count": shared_memo["count"]}
                if shared_memo["count"] else None),
            "warnings": warnings,
            "sources": sources,
            "methodology": METHODOLOGY,
        }

    # ---------- detalhamento dos pagamentos ----------

    def lines(self, bucket: str, date_from: str | None, date_to: str | None,
              store: str | None, page: int, page_size: int) -> dict:
        stores, full_scope = self._store_scope(store)
        consolidated = store in (None, "", "TODAS") and full_scope
        first, last = self._range(date_from, date_to)
        if bucket not in BUCKETS:
            raise OperationError(404, "Grupo desconhecido")
        page = max(1, page)
        page_size = min(max(1, page_size), PAGE_SIZE_MAX)

        batch = _latest_applied(self.db, KIND_DESPESAS)
        availability = _availability(self.db, KIND_DESPESAS)
        empty = {"items": [], "total": 0, "page": page, "page_size": page_size,
                 "has_data": False, "data_state": availability,
                 "period": {"first": first.isoformat(), "last": last.isoformat()}}
        if batch is None or availability != "current":
            return empty

        rules = self._rules()
        classified = []
        for row in self._payments(batch, stores, first, last):
            result = classify(
                category=row.category, account_code=row.account_code,
                supplier_name=row.supplier_name, rules=rules)
            if result.bucket != bucket:
                continue
            if result.allocation == ALLOC_SHARED and not consolidated:
                continue
            classified.append((row, result))
        classified.sort(key=lambda pair: (pair[0].paid_at, str(pair[0].id)))
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
            "period": {"first": first.isoformat(), "last": last.isoformat()},
        }
