"""Gestao de Despesas — categorias gerenciais sobre os snapshots vigentes.

Dimensao adicional e independente: nao substitui a categoria do ERP, o
codigo de conta nem as regras homologadas da DRE/Fluxo de Caixa.

Regras centrais:
- Universo = obrigacoes do lote vigente de DESPESAS com status 'pago' e
  paid_at no periodo, valor liquido (amount). Elegiveis a categoria
  gerencial: naturezas operacionais (despesa_comercial,
  despesa_operacional, das_identificado) e pendentes de natureza
  (a_classificar, sempre sinalizadas). Compras p/ revenda, financiamentos
  e imobilizado permanecem separados e fora dos percentuais.
- Resolucao da categoria: 1) classificacao manual do lancamento;
  2) regra especifica fornecedor+loja; 3) regra geral do fornecedor;
  4) sem categoria. Regras nunca sobrescrevem escolha manual.
- Persistencia independente dos lotes: a classificacao manual usa o
  'fingerprint' dos campos identitarios (loja, fornecedor, documento,
  parcela, emissao, vencimento, valor), nao o id interno da linha.
  Fingerprints sem correspondente no snapshot vigente viram 'orphan' e
  sao sinalizados para revisao — nunca transferidos por aproximacao.
- Fornecedor identificado por CNPJ/CPF normalizado ('doc:<digitos>');
  sem documento confiavel, pelo nome normalizado ('name:<...>') — nunca
  correspondencia aproximada entre fornecedores distintos.
- Permissoes: 'expenses.view' por loja para leitura; 'expenses.manage'
  por loja para categorias, regras e classificacao manual. Regras gerais
  (UMA) exigem escopo completo. Auditoria em audit_events.
"""
import hashlib
import unicodedata
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.dre_classification import (
    ALLOC_SHARED, BUCKET_A_CLASSIFICAR, BUCKET_COMPRA_REVENDA,
    BUCKET_FINANCIAMENTO, BUCKET_IMOBILIZADO, BUCKET_LABELS,
    ClassificationRule, DEFAULT_RULES, SHARED_COLUMN, TOTAL_COLUMN,
    classify,
)
from app.erp_csv import KIND_DESPESAS
from app.erp_import import _latest_applied, kind_availability
from app.finance_service import money
from app.models import (
    AuditEvent, DreClassificationRule, ErpImportBatch, ExpenseCategory,
    ExpenseLineClassification, FinancialObligation, SupplierCategoryRule,
    User,
)
from app.operations_service import OperationError
from app.policy import STORE_CODES, can_access
from app.repositories import load_principal

PAGE_SIZE_MAX = 100

# Naturezas elegiveis a categoria gerencial e incluidas na analise
# operacional (a_classificar entra sinalizada — nunca excluida em silencio).
ELIGIBLE_BUCKETS = frozenset({
    "despesa_comercial", "despesa_operacional", "das_identificado",
    BUCKET_A_CLASSIFICAR,
})
SEPARATED_BUCKETS = (
    BUCKET_COMPRA_REVENDA, BUCKET_FINANCIAMENTO, BUCKET_IMOBILIZADO,
)

METHODOLOGY = [
    "Universo: lançamentos do Despesas.csv vigente com situação 'Pago' e "
    "data efetiva no período — valor líquido do pagamento.",
    "Categoria gerencial é uma dimensão adicional: não altera a categoria "
    "do ERP, o código de conta, a DRE homologada nem o Fluxo de Caixa.",
    "Resolução: classificação manual > regra do fornecedor na loja > "
    "regra geral do fornecedor > sem categoria. Regras aplicam-se "
    "retroativamente a lançamentos sem classificação manual.",
    "Classificação manual persiste por identidade do lançamento (loja, "
    "fornecedor, documento, parcela, emissão, vencimento e valor) — "
    "sobrevive a novas importações do arquivo.",
    "Lançamentos idênticos em todos os campos identitários são "
    "indistinguíveis e compartilham a mesma classificação manual.",
    "Classificações sem correspondente no arquivo vigente são preservadas "
    "e sinalizadas para revisão — nunca transferidas por aproximação.",
    "Compras p/ revenda, financiamentos e imobilizado ficam fora da "
    "análise operacional — a composição dos totais é sempre conferível.",
    "Atribuição por loja segue o ERP: centralização de operações em "
    "Joinville significa que o gasto por loja não representa "
    "necessariamente o consumo econômico de cada unidade.",
]


# ---------- normalizacao e identidade ----------

def _norm_name(value: str | None) -> str:
    """Nome normalizado: sem acento, maiusculo, espacos colapsados."""
    text = unicodedata.normalize("NFKD", value or "")
    text = "".join(c for c in text if not unicodedata.combining(c))
    return " ".join(text.upper().split())


def _digits(value: str | None) -> str:
    return "".join(c for c in (value or "") if c.isdigit())


def supplier_key(doc: str | None, name: str | None) -> str:
    """'doc:<digitos>' com CPF(11)/CNPJ(14) confiavel; senao 'name:<norm>'.
    Fornecedores distintos nunca sao associados por aproximacao."""
    digits = _digits(doc)
    if len(digits) in (11, 14):
        return "doc:" + digits
    return "name:" + _norm_name(name)


def supplier_label(doc: str | None, name: str | None) -> str:
    digits = _digits(doc)
    return f"{_norm_name(name) or 'SEM NOME'} ({digits})" if digits else \
        (_norm_name(name) or "SEM NOME")


def line_fingerprint(row: FinancialObligation) -> str:
    """Identidade estavel do lancamento entre importacoes do arquivo.

    Campos identitarios: loja, fornecedor (doc confiavel ou nome
    normalizado), numero do documento, parcela, emissao, vencimento e
    valor liquido. paid_at e o id interno NAO entram — mudam entre lotes.
    Linhas identicas nesses campos sao indistinguiveis e compartilham a
    classificacao.
    """
    parts = [
        row.store_code,
        supplier_key(row.supplier_doc, row.supplier_name),
        (row.document_number or "").strip().upper(),
        (row.installment_number or "").strip().upper(),
        row.issued_at.isoformat() if row.issued_at else "",
        row.due_date.isoformat(),
        money(row.amount),
    ]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def _norm_category_name(name: str) -> str:
    return " ".join((name or "").split()).casefold()


class ExpenseService:

    def __init__(self, db: Session, actor: User):
        self.db = db
        self.actor = actor
        self.principal = load_principal(db, actor)

    # ---------- autorizacao ----------

    def stores_with(self, permission: str = "expenses.view") -> list[str]:
        return sorted(
            store for store in STORE_CODES
            if can_access(self.principal, permission, store)
        )

    def _store_scope(self, requested: str | None,
                     permission: str = "expenses.view") -> tuple[list[str], bool]:
        allowed = self.stores_with(permission)
        if not allowed:
            raise OperationError(403, "Acesso negado")
        if requested in (None, "", "TODAS"):
            return allowed, STORE_CODES <= set(allowed)
        if requested not in STORE_CODES:
            raise OperationError(404, "Loja desconhecida")
        if requested not in allowed:
            raise OperationError(403, "Acesso negado")
        return [requested], False

    def _require_admin(self) -> None:
        """Edicao restrita a Admin/SuperAdmin — 'expenses.manage' sozinho
        nao habilita vendedores ou colaboradores."""
        if not (self.actor.is_superadmin
                or self.actor.profile == "administrator"):
            raise OperationError(
                403, "Somente Admin e SuperAdmin podem gerenciar despesas")

    def _require_manage(self, store_code: str | None) -> None:
        """Edicao exige perfil Admin/SuperAdmin + 'expenses.manage' na
        loja; regra geral (store None) exige escopo total."""
        self._require_admin()
        if store_code is None:
            if not STORE_CODES <= set(self.stores_with("expenses.manage")):
                raise OperationError(
                    403, "Regras gerais exigem gestão em todas as lojas")
            return
        if store_code not in STORE_CODES:
            raise OperationError(404, "Loja desconhecida")
        if not can_access(self.principal, "expenses.manage", store_code):
            raise OperationError(403, "Acesso negado")

    def _audit(self, action: str, entity_type: str, entity_id: str | None,
               details: dict) -> None:
        self.db.add(AuditEvent(
            actor_id=self.actor.id,
            actor_subject=self.actor.auth_subject,
            action=action, entity_type=entity_type,
            entity_id=entity_id, details=details,
        ))

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

    # ---------- fonte vigente ----------

    def _batch(self) -> ErpImportBatch | None:
        return _latest_applied(self.db, KIND_DESPESAS)

    def _availability(self) -> str:
        return kind_availability(self.db, KIND_DESPESAS)

    def _dre_rules(self) -> list[ClassificationRule]:
        rows = self.db.scalars(
            select(DreClassificationRule).where(
                DreClassificationRule.active.is_(True))
            .order_by(DreClassificationRule.created_at, DreClassificationRule.id)
        ).all()
        if not rows:
            return list(DEFAULT_RULES)
        return [ClassificationRule(
            account_code=r.account_code, supplier_pattern=r.supplier_pattern,
            bucket=r.bucket, allocation=r.allocation, note=r.note,
        ) for r in rows]

    def _nature(self, row: FinancialObligation, rules) -> tuple[str, str]:
        result = classify(
            category=row.category, account_code=row.account_code,
            supplier_name=row.supplier_name, rules=rules)
        alloc = (SHARED_COLUMN if result.allocation == ALLOC_SHARED
                 else row.store_code)
        return result.bucket, alloc

    # ---------- linhas pagas + resolucao de categoria ----------

    def _paid_lines(self, batch: ErpImportBatch, stores: list[str],
                    first: date, last: date):
        return self.db.scalars(
            select(FinancialObligation).where(
                FinancialObligation.batch_id == batch.id,
                FinancialObligation.store_code.in_(stores),
                FinancialObligation.status == "pago",
                FinancialObligation.paid_at >= first,
                FinancialObligation.paid_at <= last,
            ).order_by(
                FinancialObligation.paid_at,
                FinancialObligation.supplier_name,
                FinancialObligation.id,
            )
        ).all()

    def _all_paid_lines(self, batch: ErpImportBatch, stores: list[str]):
        """Todas as linhas pagas do snapshot vigente (para reconciliar
        fingerprints) — independente do periodo filtrado."""
        return self.db.scalars(
            select(FinancialObligation).where(
                FinancialObligation.batch_id == batch.id,
                FinancialObligation.store_code.in_(stores),
                FinancialObligation.status == "pago",
            )
        ).all()

    def _manual_map(self, fingerprints: list[str]) -> dict[str, ExpenseLineClassification]:
        if not fingerprints:
            return {}
        rows = self.db.scalars(
            select(ExpenseLineClassification).where(
                ExpenseLineClassification.fingerprint.in_(fingerprints))
        ).all()
        return {r.fingerprint: r for r in rows}

    def _rule_map(self) -> dict[str, dict[str | None, SupplierCategoryRule]]:
        """supplier_key -> {store_code ou None: regra ativa com categoria ativa}"""
        rows = self.db.execute(
            select(SupplierCategoryRule)
            .join(ExpenseCategory,
                  SupplierCategoryRule.category_id == ExpenseCategory.id)
            .where(SupplierCategoryRule.active.is_(True),
                   ExpenseCategory.active.is_(True))
        ).scalars().all()
        result: dict[str, dict[str | None, SupplierCategoryRule]] = {}
        for r in rows:
            result.setdefault(r.supplier_key, {})[r.store_code] = r
        return result

    def _category_names(self) -> dict[UUID, str]:
        return {
            c.id: c.name
            for c in self.db.scalars(select(ExpenseCategory)).all()
        }

    def _resolve(self, row: FinancialObligation, manual: dict,
                 rules_map: dict, names: dict) -> dict:
        """Categoria efetiva do lancamento + origem da resolucao."""
        fp = line_fingerprint(row)
        record = manual.get(fp)
        if record is not None:
            return {"fingerprint": fp, "category_id": record.category_id,
                    "category_name": names.get(record.category_id, "—"),
                    "origin": "manual"}
        rules = rules_map.get(supplier_key(row.supplier_doc, row.supplier_name), {})
        rule = rules.get(row.store_code) or rules.get(None)
        if rule is not None:
            return {"fingerprint": fp, "category_id": rule.category_id,
                    "category_name": names.get(rule.category_id, "—"),
                    "origin": ("rule_store" if rule.store_code
                               else "rule_general"),
                    "rule_id": rule.id}
        return {"fingerprint": fp, "category_id": None,
                "category_name": None, "origin": "none"}

    def _sync_orphans(self, batch: ErpImportBatch | None) -> int:
        """Marca/desmarca classificacoes sem correspondente no snapshot
        vigente e atualiza matched_rows. Retorna a quantidade de orfas."""
        records = self.db.scalars(select(ExpenseLineClassification)).all()
        if not records:
            return 0
        counts: dict[str, int] = {}
        if batch is not None:
            for row in self._all_paid_lines(batch, list(STORE_CODES)):
                fp = line_fingerprint(row)
                counts[fp] = counts.get(fp, 0) + 1
        orphans = 0
        changed = False
        for rec in records:
            found = counts.get(rec.fingerprint, 0)
            status = "active" if found else "orphan"
            if found == 0:
                orphans += 1
            if rec.status != status or rec.matched_rows != found:
                rec.status = status
                rec.matched_rows = found
                changed = True
        if changed:
            self.db.commit()
        return orphans

    # ---------- categorias ----------

    def list_categories(self, include_inactive: bool = True) -> dict:
        if not self.stores_with():
            raise OperationError(403, "Acesso negado")
        query = select(ExpenseCategory).order_by(
            ExpenseCategory.active.desc(), ExpenseCategory.name)
        if not include_inactive:
            query = query.where(ExpenseCategory.active.is_(True))
        return {"items": [{
            "id": str(c.id), "name": c.name, "active": c.active,
            "created_at": c.created_at.isoformat(),
        } for c in self.db.scalars(query).all()]}

    def create_category(self, name: str) -> dict:
        self._require_admin()
        if not self.stores_with("expenses.manage"):
            raise OperationError(403, "Acesso negado")
        clean = " ".join((name or "").split())[:80]
        if not clean:
            raise OperationError(422, "Informe o nome da categoria")
        norm = _norm_category_name(clean)
        existing = self.db.scalar(
            select(ExpenseCategory).where(ExpenseCategory.name_norm == norm))
        if existing is not None:
            state = "desativada" if not existing.active else "cadastrada"
            raise OperationError(
                409, f"Categoria já {state}: '{existing.name}'")
        cat = ExpenseCategory(name=clean, name_norm=norm,
                              created_by=self.actor.id)
        self.db.add(cat)
        self.db.flush()
        self._audit("expenses.category.create", "expense_category",
                    str(cat.id), {"name": clean})
        self.db.commit()
        return {"id": str(cat.id), "name": cat.name, "active": cat.active}

    def update_category(self, category_id: str, name: str | None,
                        active: bool | None) -> dict:
        self._require_admin()
        if not self.stores_with("expenses.manage"):
            raise OperationError(403, "Acesso negado")
        cat = self.db.get(ExpenseCategory, UUID(category_id))
        if cat is None:
            raise OperationError(404, "Categoria não encontrada")
        details: dict = {}
        if name is not None:
            clean = " ".join(name.split())[:80]
            if not clean:
                raise OperationError(422, "Informe o nome da categoria")
            norm = _norm_category_name(clean)
            dup = self.db.scalar(
                select(ExpenseCategory).where(
                    ExpenseCategory.name_norm == norm,
                    ExpenseCategory.id != cat.id))
            if dup is not None:
                raise OperationError(
                    409, f"Nome já utilizado pela categoria '{dup.name}'")
            if clean != cat.name:
                details["old_name"] = cat.name
                details["new_name"] = clean
                cat.name, cat.name_norm = clean, norm
        if active is not None and active != cat.active:
            details["old_active"] = cat.active
            details["new_active"] = active
            cat.active = active
        if details:
            self._audit("expenses.category.update", "expense_category",
                        str(cat.id), details)
            self.db.commit()
        return {"id": str(cat.id), "name": cat.name, "active": cat.active}

    # ---------- fornecedores e regras ----------

    def search_suppliers(self, query: str, limit: int = 20) -> dict:
        stores = self.stores_with()
        if not stores:
            raise OperationError(403, "Acesso negado")
        batch = self._batch()
        if batch is None:
            return {"items": []}
        q = _norm_name(query or "")
        rows = self.db.execute(
            select(FinancialObligation.supplier_doc,
                   FinancialObligation.supplier_name,
                   func.count())
            .where(FinancialObligation.batch_id == batch.id,
                   FinancialObligation.store_code.in_(stores))
            .group_by(FinancialObligation.supplier_doc,
                      FinancialObligation.supplier_name)
        ).all()
        items = []
        for doc, name, count in rows:
            key = supplier_key(doc, name)
            label = supplier_label(doc, name)
            if q and q not in _norm_name(name) and q not in _digits(doc):
                continue
            items.append({"supplier_key": key, "label": label,
                          "doc": _digits(doc) or None, "name": name,
                          "rows": count})
        items.sort(key=lambda i: i["name"])
        return {"items": items[:limit]}

    def supplier_catalog(self, query: str, page: int, page_size: int,
                         without_rule: bool, sort: str) -> dict:
        """Catalogo completo de fornecedores do snapshot vigente (pagos e
        em aberto), com as regras automaticas visiveis ao escopo do
        usuario — base da associacao em massa no Gerenciar Categorias."""
        stores = self.stores_with()
        if not stores:
            raise OperationError(403, "Acesso negado")
        batch = self._batch()
        if batch is None:
            return {"items": [], "total": 0, "page": page,
                    "page_size": page_size,
                    "availability": self._availability()}
        rows = self.db.execute(
            select(FinancialObligation.supplier_doc,
                   FinancialObligation.supplier_name,
                   FinancialObligation.store_code,
                   func.count())
            .where(FinancialObligation.batch_id == batch.id,
                   FinancialObligation.store_code.in_(stores))
            .group_by(FinancialObligation.supplier_doc,
                      FinancialObligation.supplier_name,
                      FinancialObligation.store_code)
        ).all()
        grouped: dict[str, dict] = {}
        for doc, name, store, count in rows:
            key = supplier_key(doc, name)
            entry = grouped.setdefault(key, {
                "supplier_key": key, "doc": _digits(doc) or None,
                "name": _norm_name(name) or "SEM NOME",
                "label": supplier_label(doc, name),
                "rows": 0, "stores": set()})
            entry["rows"] += count
            entry["stores"].add(store)
        keys = list(grouped)
        rules = self.db.scalars(
            select(SupplierCategoryRule).where(
                SupplierCategoryRule.supplier_key.in_(keys))
        ).all() if keys else []
        full_scope = STORE_CODES <= set(stores)
        rules_by: dict[str, dict] = {}
        for r in rules:
            slot = "general" if r.store_code is None else r.store_code
            # mesma visibilidade de list_rules: geral so com escopo total
            if slot == "general" and not full_scope:
                continue
            if slot != "general" and slot not in stores:
                continue
            rules_by.setdefault(r.supplier_key, {})[slot] = {
                "id": str(r.id), "category_id": str(r.category_id),
                "category_name": self._category_names().get(
                    r.category_id, "—"),
                "active": r.active}
        q, qd = _norm_name(query or ""), _digits(query or "")
        items = []
        for key, e in grouped.items():
            if q and q not in e["name"] and not (qd and qd in (e["doc"] or "")):
                continue
            supplier_rules = rules_by.get(key, {})
            has_rule = any(r["active"] for r in supplier_rules.values())
            if without_rule and has_rule:
                continue
            items.append({**e, "stores": sorted(e["stores"]),
                          "rules": supplier_rules,
                          "has_rule": has_rule})
        if sort == "unclassified_first":
            items.sort(key=lambda i: (i["has_rule"], i["name"]))
        else:
            items.sort(key=lambda i: i["name"])
        total = len(items)
        start = (page - 1) * page_size
        return {"items": items[start:start + page_size], "total": total,
                "page": page, "page_size": page_size,
                "availability": self._availability()}

    def list_rules(self) -> dict:
        stores = self.stores_with()
        if not stores:
            raise OperationError(403, "Acesso negado")
        names = self._category_names()
        rows = self.db.scalars(
            select(SupplierCategoryRule)
            .order_by(SupplierCategoryRule.supplier_label)
        ).all()
        # Regras de outras lojas nao vazam para quem nao tem escopo.
        visible = [
            r for r in rows
            if r.store_code is None and STORE_CODES <= set(stores)
            or r.store_code in stores
        ]
        return {"items": [{
            "id": str(r.id), "supplier_key": r.supplier_key,
            "supplier_label": r.supplier_label,
            "store_code": r.store_code,
            "scope": "Todas as lojas" if r.store_code is None
                     else r.store_code,
            "category_id": str(r.category_id),
            "category_name": names.get(r.category_id, "—"),
            "active": r.active,
        } for r in visible]}

    def _visible_rule(self, rule_id: str) -> SupplierCategoryRule:
        rule = self.db.get(SupplierCategoryRule, UUID(rule_id))
        if rule is None:
            raise OperationError(404, "Regra não encontrada")
        self._require_manage(rule.store_code)
        return rule

    def _assert_category_active(self, category_id: str) -> ExpenseCategory:
        cat = self.db.get(ExpenseCategory, UUID(category_id))
        if cat is None:
            raise OperationError(404, "Categoria não encontrada")
        if not cat.active:
            raise OperationError(422, "Categoria desativada — reative para usar")
        return cat

    def create_rule(self, supplier_key_value: str, supplier_label_value: str,
                    store_code: str | None, category_id: str) -> dict:
        self._require_manage(store_code)
        cat = self._assert_category_active(category_id)
        key = (supplier_key_value or "").strip()
        if not key.startswith(("doc:", "name:")):
            raise OperationError(422, "Fornecedor inválido")
        existing = self.db.scalars(
            select(SupplierCategoryRule).where(
                SupplierCategoryRule.supplier_key == key,
                SupplierCategoryRule.store_code.is_(None)
                if store_code is None else
                SupplierCategoryRule.store_code == store_code)
        ).all()
        if existing and any(r.active for r in existing):
            raise OperationError(
                409, "Já existe regra ativa para este fornecedor/abrangência")
        if existing:
            rule = existing[0]
            old = str(rule.category_id)
            rule.category_id, rule.active = cat.id, True
            self._audit("expenses.rule.update", "supplier_rule", str(rule.id),
                        {"supplier_key": key, "scope": store_code,
                         "old_category_id": old,
                         "new_category_id": str(cat.id)})
        else:
            rule = SupplierCategoryRule(
                supplier_key=key,
                supplier_label=(supplier_label_value or key)[:220],
                store_code=store_code, category_id=cat.id,
                created_by=self.actor.id)
            self.db.add(rule)
            self.db.flush()
            self._audit("expenses.rule.create", "supplier_rule",
                        str(rule.id),
                        {"supplier_key": key, "scope": store_code,
                         "category_id": str(cat.id)})
        self.db.commit()
        return {"id": str(rule.id)}

    def update_rule(self, rule_id: str, category_id: str | None,
                    active: bool | None) -> dict:
        rule = self._visible_rule(rule_id)
        details: dict = {"supplier_key": rule.supplier_key,
                         "scope": rule.store_code}
        if category_id is not None:
            cat = self._assert_category_active(category_id)
            if str(cat.id) != str(rule.category_id):
                details["old_category_id"] = str(rule.category_id)
                details["new_category_id"] = str(cat.id)
                rule.category_id = cat.id
        if active is not None and active != rule.active:
            details["old_active"] = rule.active
            details["new_active"] = active
            rule.active = active
        if len(details) > 2:
            self._audit("expenses.rule.update", "supplier_rule",
                        str(rule.id), details)
            self.db.commit()
        return {"id": str(rule.id)}

    # ---------- classificacao manual ----------

    def set_classification(self, fingerprint: str,
                           category_id: str | None) -> dict:
        """Classificacao manual por identidade do lancamento (autosave).

        category_id None = remover a classificacao manual — o lancamento
        volta a cair na regra automatica aplicavel ou em sem categoria.
        """
        if self._availability() != "current":
            raise OperationError(
                422, "Arquivo de despesas vigente indisponível ou "
                     "inválido — classificação bloqueada até uma nova "
                     "sincronização válida do ERP")
        batch = self._batch()
        if batch is None:
            raise OperationError(422, "Sem arquivo vigente de despesas")
        rows = self._all_paid_lines(batch, list(STORE_CODES))
        matches = [r for r in rows if line_fingerprint(r) == fingerprint]
        if not matches:
            raise OperationError(
                404, "Lançamento não encontrado no arquivo vigente — "
                     "pode ter sido alterado pelo ERP (revisão pendente)")
        store = matches[0].store_code
        if any(r.store_code != store for r in matches):
            raise OperationError(422, "Identidade ambígua — revisão necessária")
        self._require_manage(store)
        dre_rules = self._dre_rules()
        if any(self._nature(r, dre_rules)[0] not in ELIGIBLE_BUCKETS
               for r in matches):
            raise OperationError(
                422, "Lançamento não elegível — natureza separada da análise "
                     "operacional (revenda, financiamento ou imobilizado)")
        existing = self.db.scalar(
            select(ExpenseLineClassification).where(
                ExpenseLineClassification.fingerprint == fingerprint))
        names = self._category_names()
        old_cat_id = str(existing.category_id) if existing else None
        old_name = names.get(existing.category_id) if existing else None

        if category_id is None:
            if existing is not None:
                self._audit("expenses.classify.remove", "expense_line",
                            fingerprint,
                            {"store": store, "supplier": existing.supplier_label,
                             "old_category_id": old_cat_id,
                             "old_category": old_name,
                             "rows": len(matches)})
                self.db.delete(existing)
                self.db.commit()
            return {"fingerprint": fingerprint, "category_id": None,
                    "origin": "removed", "rows": len(matches)}

        cat = self._assert_category_active(category_id)
        if existing is None:
            existing = ExpenseLineClassification(
                fingerprint=fingerprint, category_id=cat.id,
                store_code=store,
                supplier_key=supplier_key(
                    matches[0].supplier_doc, matches[0].supplier_name),
                supplier_label=supplier_label(
                    matches[0].supplier_doc, matches[0].supplier_name),
                document_number=matches[0].document_number,
                installment_number=matches[0].installment_number,
                issued_at=matches[0].issued_at,
                due_date=matches[0].due_date,
                amount=matches[0].amount,
                matched_rows=len(matches),
                created_by=self.actor.id)
            self.db.add(existing)
        else:
            existing.category_id = cat.id
            existing.matched_rows = len(matches)
            existing.status = "active"
        self.db.flush()
        self._audit("expenses.classify.set", "expense_line", fingerprint,
                    {"store": store, "supplier": existing.supplier_label,
                     "old_category_id": old_cat_id,
                     "old_category": old_name,
                     "new_category_id": str(cat.id),
                     "new_category": cat.name,
                     "rows": len(matches)})
        self.db.commit()
        return {"fingerprint": fingerprint,
                "category_id": str(cat.id), "category_name": cat.name,
                "origin": "manual", "rows": len(matches)}

    # ---------- consulta: linhas classificaveis ----------

    def lines(self, date_from: str | None, date_to: str | None,
              store: str | None, category_id: str | None,
              situation: str | None, supplier: str | None,
              page: int, page_size: int) -> dict:
        stores, full_scope = self._store_scope(store)
        consolidated = store in (None, "", "TODAS") and full_scope
        first, last = self._range(date_from, date_to)
        batch = self._batch()
        orphans = self._sync_orphans(batch)
        if batch is None:
            return {"items": [], "total": 0, "page": page,
                    "page_size": page_size, "orphan_classifications": orphans,
                    "availability": self._availability(),
                    "categories": self.list_categories()["items"]}

        dre_rules = self._dre_rules()
        rows = self._paid_lines(batch, stores, first, last)
        manual = self._manual_map(
            [line_fingerprint(r) for r in rows])
        rules_map = self._rule_map()
        names = self._category_names()
        q = _norm_name(supplier or "")
        cat_filter = None
        if category_id == "none":
            cat_filter = "none"
        elif category_id:
            cat_filter = category_id
        fp_counts: dict[str, int] = {}
        for row in rows:
            fp = line_fingerprint(row)
            fp_counts[fp] = fp_counts.get(fp, 0) + 1

        items = []
        for row in rows:
            resolved = self._resolve(row, manual, rules_map, names)
            bucket, alloc = self._nature(row, dre_rules)
            eligible = bucket in ELIGIBLE_BUCKETS
            # na visao de loja individual, despesas compartilhadas ficam
            # fora da lista — mesma fronteira do total da analise (elas
            # aparecem como memo e na coluna propria do consolidado)
            if not consolidated and alloc == SHARED_COLUMN:
                continue
            if situation == "classified" and resolved["category_id"] is None:
                continue
            if situation == "unclassified" and (
                    resolved["category_id"] is not None or not eligible):
                continue
            if cat_filter == "none" and resolved["category_id"] is not None:
                continue
            if (cat_filter not in (None, "none")
                    and str(resolved["category_id"]) != cat_filter):
                continue
            if q and q not in _norm_name(row.supplier_name) \
                    and q not in _digits(row.supplier_doc):
                continue
            items.append({
                "row_key": str(row.id),
                "fingerprint": resolved["fingerprint"],
                "duplicate_count": fp_counts.get(resolved["fingerprint"], 1),
                "supplier_name": row.supplier_name,
                "supplier_doc": _digits(row.supplier_doc) or None,
                "store_code": row.store_code,
                "paid_at": row.paid_at.isoformat(),
                "document_number": row.document_number,
                "installment_number": row.installment_number,
                "amount": money(row.amount),
                "nature": bucket,
                "nature_label": BUCKET_LABELS.get(bucket, bucket),
                "allocation": alloc,
                "eligible": eligible,
                "category_id": (str(resolved["category_id"])
                                if resolved["category_id"] else None),
                "category_name": resolved["category_name"],
                "origin": resolved["origin"] if eligible else "none",
            })
        total = len(items)
        start = (page - 1) * page_size
        return {"items": items[start:start + page_size], "total": total,
                "page": page, "page_size": page_size,
                "orphan_classifications": orphans,
                "availability": self._availability(),
                "categories": self.list_categories()["items"]}

    # ---------- consulta: analise por categoria ----------

    def analysis(self, date_from: str | None, date_to: str | None,
                 store: str | None, category_id: str | None,
                 situation: str | None, supplier: str | None) -> dict:
        stores, full_scope = self._store_scope(store)
        first, last = self._range(date_from, date_to)
        consolidated = store in (None, "", "TODAS") and full_scope
        batch = self._batch()
        orphans = self._sync_orphans(batch)
        warnings: list[dict] = []
        if self._availability() != "current" or batch is None:
            warnings.append({
                "code": "despesas_indisponiveis",
                "message": "Despesas: arquivo vigente indisponível — "
                           "análise não apurável.",
            })
            return {"availability": self._availability(), "warnings": warnings,
                    "orphan_classifications": orphans,
                    "totals": None, "by_category": [], "by_store": [],
                    "excluded_natures": [], "pending_nature": None,
                    "methodology": METHODOLOGY}

        dre_rules = self._dre_rules()
        rows = self._paid_lines(batch, stores, first, last)
        manual = self._manual_map(
            [line_fingerprint(r) for r in rows])
        rules_map = self._rule_map()
        names = self._category_names()
        q = _norm_name(supplier or "")

        by_cat: dict[str, dict] = {}
        by_store: dict[str, dict] = {s: {} for s in stores}
        if consolidated:
            by_store[SHARED_COLUMN] = {}
        excluded: dict[str, dict] = {}
        shared_memo = {"amount": Decimal(0), "rows": 0}
        pending = Decimal(0)
        paid_total = Decimal(0)
        classified_total = Decimal(0)
        payment_rows = 0
        unclassified_rows = 0

        def pass_filters(resolved) -> bool:
            if situation == "classified" and resolved["category_id"] is None:
                return False
            if situation == "unclassified" and resolved["category_id"] is not None:
                return False
            if category_id == "none" and resolved["category_id"] is not None:
                return False
            if (category_id not in (None, "none")
                    and str(resolved["category_id"]) != category_id):
                return False
            return True

        for row in rows:
            bucket, alloc = self._nature(row, dre_rules)
            resolved = self._resolve(row, manual, rules_map, names)
            if q and q not in _norm_name(row.supplier_name) \
                    and q not in _digits(row.supplier_doc):
                continue
            if bucket not in ELIGIBLE_BUCKETS:
                entry = excluded.setdefault(
                    bucket, {"total": Decimal(0), "rows": 0})
                entry["total"] += row.amount
                entry["rows"] += 1
                continue
            if bucket == BUCKET_A_CLASSIFICAR:
                pending += row.amount
            if not pass_filters(resolved):
                continue
            col = alloc if consolidated and alloc == SHARED_COLUMN \
                else row.store_code
            if alloc == SHARED_COLUMN and not consolidated:
                shared_memo["amount"] += row.amount
                shared_memo["rows"] += 1
                continue
            paid_total += row.amount
            payment_rows += 1
            key = (str(resolved["category_id"])
                   if resolved["category_id"] else "none")
            entry = by_cat.setdefault(key, {
                "category_id": resolved["category_id"],
                "name": resolved["category_name"] or "Sem categoria",
                "total": Decimal(0), "rows": 0})
            entry["total"] += row.amount
            entry["rows"] += 1
            s_entry = by_store.setdefault(col, {}).setdefault(
                key, {"name": entry["name"], "total": Decimal(0)})
            s_entry["total"] += row.amount
            if resolved["category_id"] is None:
                unclassified_rows += 1
            else:
                classified_total += row.amount

        total_dec = paid_total or Decimal(1)
        categories = sorted(
            ({"category_id": v["category_id"], "name": v["name"],
              "total": money(v["total"]),
              "pct": str((v["total"] / total_dec * 100).quantize(Decimal("0.1"))),
              "rows": v["rows"]} for v in by_cat.values()),
            key=lambda c: Decimal(c["total"]), reverse=True)

        store_cols = []
        for code in list(stores) + ([SHARED_COLUMN] if consolidated else []):
            cats = by_store.get(code, {})
            col_total = sum((v["total"] for v in cats.values()), Decimal(0))
            denom = col_total or Decimal(1)
            store_cols.append({
                "store": code,
                "total": money(col_total),
                "categories": sorted(
                    ({"name": v["name"], "total": money(v["total"]),
                      "pct": str((v["total"] / denom * 100)
                                 .quantize(Decimal("0.1")))}
                     for v in cats.values()),
                    key=lambda c: Decimal(c["total"]), reverse=True),
            })

        return {
            "availability": "current",
            "warnings": warnings + ([{
                "code": "classificacoes_orfas",
                "message": f"{orphans} classificação(ões) manual(is) sem "
                           "correspondente no arquivo vigente — revisar.",
            }] if orphans else []) + ([{
                "code": "natureza_pendente",
                "message": f"Inclui {money(pending)} em lançamentos de "
                           "natureza pendente (a classificar na DRE).",
            }] if pending else []),
            "orphan_classifications": orphans,
            "totals": {
                "paid_total": money(paid_total),
                "classified": money(classified_total),
                "unclassified": money(paid_total - classified_total),
                "classified_pct": str(
                    (classified_total / total_dec * 100)
                    .quantize(Decimal("0.1"))) if paid_total else None,
                "payment_rows": payment_rows,
                "unclassified_rows": unclassified_rows,
            },
            "by_category": categories,
            "by_store": store_cols,
            "shared_memo": shared_memo if not consolidated else None,
            "excluded_natures": [{
                "bucket": b, "label": BUCKET_LABELS.get(b, b),
                "total": money(excluded[b]["total"]),
                "rows": excluded[b]["rows"],
            } for b in SEPARATED_BUCKETS if b in excluded],
            "pending_nature": money(pending) if pending else None,
            "methodology": METHODOLOGY,
        }
