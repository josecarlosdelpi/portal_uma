"""Application services for ERP-independent operational routines.

Authorization, store boundaries and audit are checked inside each use case.
Seller accounts remain read-only as approved for operational v1.
"""
import csv
import io
from datetime import date, datetime, time, timedelta
from uuid import UUID, uuid4

from sqlalchemy import func, or_, select
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    AccessGroup, AccessGroupStore, AuditEvent, ClientImportSession,
    ContactAttempt, ContactClient, ContactSetting, ContactTag,
    GoogleReviewMonth, GroupMembership, SupplyMaterial, SupplyMovement,
    SupplyStock, User, UserStoreScope,
)
from app.policy import STORE_CODES, can_access, visible_stores
from app.repositories import load_principal


class OperationError(Exception):
    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.message = message


def normalize(value: str) -> str:
    return " ".join(value.casefold().split())


def phone_digits(value: str | None) -> str:
    return "".join(ch for ch in (value or "") if ch.isdigit())


def _safe_cell(value) -> str:
    """Escapa valores que planilhas interpretariam como formula."""
    text = "" if value is None else str(value)
    if text[:1] in ("=", "+", "-", "@"):
        return "'" + text
    return text


CLIENT_STATUSES = ("ativo", "inativo", "prospect")
CALL_CHANNELS = ("ligacao", "whatsapp")
IMPORT_PREVIEW_TTL = timedelta(hours=24)


def date_time(day: date | None) -> datetime | None:
    return datetime.combine(day, time.min) if day else None


def day_iso(value: datetime | None) -> str | None:
    return value.date().isoformat() if value else None


def reward_tier(count: int) -> str:
    return "maior" if count >= 20 else "simbolico" if count >= 10 else "nenhum"


class OperationsService:
    def __init__(self, db: Session, actor: User):
        self.db = db
        self.actor = actor
        self.principal = load_principal(db, actor)

    def require(self, store: str, permission: str) -> None:
        if store not in STORE_CODES:
            raise OperationError(404, "Loja desconhecida")
        if not can_access(self.principal, permission, store):
            raise OperationError(403, "Acesso negado")

    def require_global(self, permission: str) -> None:
        """Recurso global da UMA (nao pertence a uma loja especifica).

        Basta a concessao efetiva da permissao em qualquer loja autorizada.
        Usado pelo calendario unico de WhatsApp: exigir uma loja fixa criaria
        uma dependencia artificial de abrangencia geografica."""
        if not any(can_access(self.principal, permission, store)
                   for store in STORE_CODES):
            raise OperationError(403, "Acesso negado")

    def allowed(self, permission: str) -> list[str]:
        return sorted(
            store for store in visible_stores(self.principal)
            if can_access(self.principal, permission, store)
        )

    @staticmethod
    def period(year: int, month: int) -> None:
        if not 2020 <= year <= 2100 or not 1 <= month <= 12:
            raise OperationError(422, "Competência inválida")

    @staticmethod
    def revision(row, expected: int) -> None:
        if (row.revision if row else 0) != expected:
            raise OperationError(409, "Registro atualizado em outra sessão. Atualize a tela antes de salvar.")

    def audit(self, action: str, entity: str, identifier: str, details: dict) -> None:
        self.db.add(AuditEvent(
            id=uuid4(), actor_id=self.actor.id, actor_subject=self.actor.auth_subject,
            action=action, entity_type=entity, entity_id=identifier, details=details,
        ))

    def commit(self) -> None:
        try:
            self.db.commit()
        except (IntegrityError, DBAPIError) as error:
            self.db.rollback()
            raise OperationError(409, "Registro já existe ou foi alterado. Atualize os dados.") from error

    def review_list(self, year: int, month: int) -> dict:
        self.period(year, month)
        stores = self.allowed("reviews.view")
        if not stores:
            raise OperationError(403, "Acesso negado")
        rows = self.db.scalars(
            select(GoogleReviewMonth).where(
                GoogleReviewMonth.year == year, GoogleReviewMonth.month == month,
                GoogleReviewMonth.store_code.in_(stores),
            )
        ).all()
        saved = {row.store_code: row for row in rows}
        return {"year": year, "month": month,
                "source": "conferencia_manual_google",
                "stores": [
                    self._review(saved.get(store), store) for store in stores
                ]}

    @staticmethod
    def _review(row: GoogleReviewMonth | None, store: str) -> dict:
        count = row.count if row else None
        tier = reward_tier(count) if count is not None else None
        return {
            "store_code": store, "count": count,
            "tier": tier, "reward_per_seller": tier,
            "checked_on": day_iso(row.checked_on) if row else None,
            "delivered_on": day_iso(row.delivered_on) if row else None,
            "note": row.note if row else "",
            "revision": row.revision if row else 0,
            "status": "not_recorded" if row is None else "verified_manually",
        }

    def save_review(self, store: str, year: int, month: int, *,
                    count: int, checked_on: date, delivered_on: date | None,
                    note: str, expected: int) -> dict:
        self.require(store, "reviews.edit")
        self.period(year, month)
        if checked_on.year < year or checked_on.month < month and checked_on.year == year:
            raise OperationError(422, "A conferência não pode ser anterior à competência")
        if delivered_on and (reward_tier(count) == "nenhum" or delivered_on < checked_on):
            raise OperationError(422, "Não é possível registrar entrega sem prêmio elegível ou antes da conferência")
        row = self.db.scalar(select(GoogleReviewMonth).where(
            GoogleReviewMonth.store_code == store,
            GoogleReviewMonth.year == year, GoogleReviewMonth.month == month,
        ).with_for_update())
        self.revision(row, expected)
        # A entrega antiga não pode migrar silenciosamente para outra faixa.
        if (row is not None and row.delivered_on is not None
                and reward_tier(row.count) != reward_tier(count)
                and delivered_on is not None
                and delivered_on == row.delivered_on.date()):
            raise OperationError(
                422, "A faixa de premiação mudou. Confirme nova entrega ou deixe pendente."
            )
        before = self._review(row, store)
        if row is None:
            row = GoogleReviewMonth(
                id=uuid4(), store_code=store, year=year, month=month,
                count=count, checked_on=date_time(checked_on),
                delivered_on=date_time(delivered_on), note=note,
                revision=1, updated_by=self.actor.id,
            )
            self.db.add(row)
        else:
            # Cannot silently reuse a previous reward-delivery date when tier changes.
            row.count = count
            row.checked_on = date_time(checked_on)
            row.delivered_on = date_time(delivered_on)
            row.note = note
            row.revision += 1
            row.updated_by = self.actor.id
        self.audit("reviews.checked", "google_reviews", f"{store}|{year:04d}-{month:02d}",
                   {"store": store, "period": f"{year:04d}-{month:02d}",
                    "before_count": before["count"], "after_count": count,
                    "tier": reward_tier(count), "delivered_on": delivered_on.isoformat() if delivered_on else None})
        self.commit()
        return self._review(row, store)

    def materials(self, store: str) -> dict:
        self.require(store, "supplies.view")
        rows = self.db.execute(
            select(SupplyStock, SupplyMaterial).join(
                SupplyMaterial, SupplyStock.material_id == SupplyMaterial.id
            ).where(SupplyStock.store_code == store, SupplyMaterial.active.is_(True))
            .order_by(SupplyMaterial.name)
        ).all()
        return {"store_code": store, "items": [
            {"id": str(material.id), "name": material.name, "unit": material.unit,
             "balance": stock.balance, "minimum": stock.minimum,
             "revision": stock.revision,
             "needs_restock": stock.balance <= stock.minimum}
            for stock, material in rows
        ]}

    def create_material(self, name: str, unit: str, minima: dict[str, int]) -> dict:
        # Global master data can only be managed by administrators.
        for store in STORE_CODES:
            self.require(store, "supplies.edit")
        name = name.strip()
        if not name or set(minima) != STORE_CODES:
            raise OperationError(422, "Material e mínimos das três lojas são obrigatórios")
        key = normalize(name)
        if self.db.scalar(select(SupplyMaterial.id).where(SupplyMaterial.name_key == key)):
            raise OperationError(409, "Material já cadastrado")
        material = SupplyMaterial(
            id=uuid4(), name=name, name_key=key, unit=unit, active=True,
            created_by=self.actor.id,
        )
        self.db.add(material)
        for store in STORE_CODES:
            self.db.add(SupplyStock(store_code=store, material_id=material.id,
                                    balance=0, minimum=minima[store],
                                    revision=1, updated_by=self.actor.id))
        self.audit("supplies.material.created", "supply_material", str(material.id),
                   {"name": name, "unit": unit, "minima": minima})
        self.commit()
        return {"id": str(material.id), "name": name, "unit": unit}

    def set_minimum(self, store: str, material_id: UUID,
                    minimum: int, expected: int) -> dict:
        self.require(store, "supplies.edit")
        stock = self.db.scalar(select(SupplyStock).where(
            SupplyStock.store_code == store,
            SupplyStock.material_id == material_id,
        ).with_for_update())
        if not stock:
            raise OperationError(404, "Material não localizado nesta loja")
        self.revision(stock, expected)
        before = stock.minimum
        stock.minimum = minimum
        stock.revision += 1
        stock.updated_by = self.actor.id
        self.audit("supplies.minimum.changed", "supply_stock", f"{store}|{material_id}",
                   {"before": before, "after": minimum})
        self.commit()
        return {"store_code": store, "material_id": str(material_id),
                "minimum": stock.minimum, "revision": stock.revision}

    def movement(self, store: str, material_id: UUID, kind: str,
                 quantity: int, note: str, expected: int) -> dict:
        self.require(store, "supplies.edit")
        stock = self.db.scalar(select(SupplyStock).where(
            SupplyStock.store_code == store,
            SupplyStock.material_id == material_id,
        ).with_for_update())
        if not stock:
            raise OperationError(404, "Material não localizado nesta loja")
        self.revision(stock, expected)
        if kind == "retirada" and quantity > stock.balance:
            raise OperationError(422, "Retirada maior que o saldo disponível")
        if kind not in {"entrada", "retirada"}:
            raise OperationError(422, "Tipo de movimento inválido")
        stock.balance += quantity if kind == "entrada" else -quantity
        stock.revision += 1
        stock.updated_by = self.actor.id
        movement = SupplyMovement(
            id=uuid4(), store_code=store, material_id=material_id, kind=kind,
            quantity=quantity, resulting_balance=stock.balance, note=note,
            actor_id=self.actor.id,
        )
        self.db.add(movement)
        self.audit("supplies.movement.created", "supply_movement", str(movement.id),
                   {"store": store, "material": str(material_id),
                    "kind": kind, "quantity": quantity, "resulting_balance": stock.balance})
        self.commit()
        return {"id": str(movement.id), "store_code": store, "kind": kind,
                "quantity": quantity, "resulting_balance": stock.balance,
                "revision": stock.revision}

    def movements(self, store: str, limit: int = 100) -> list[dict]:
        self.require(store, "supplies.view")
        rows = self.db.execute(
            select(SupplyMovement, SupplyMaterial.name, User.display_name)
            .join(SupplyMaterial, SupplyMaterial.id == SupplyMovement.material_id)
            .join(User, User.id == SupplyMovement.actor_id)
            .where(SupplyMovement.store_code == store)
            .order_by(SupplyMovement.created_at.desc(), SupplyMovement.id.desc())
            .limit(limit)
        ).all()
        return [{
            "id": str(move.id), "material_id": str(move.material_id),
            "material": name, "store_code": store, "kind": move.kind,
            "quantity": move.quantity, "resulting_balance": move.resulting_balance,
            "actor": author, "note": move.note, "created_at": move.created_at.isoformat(),
        } for move, name, author in rows]

    # ---- Carteira de clientes (televendas) ----

    def _settings(self) -> ContactSetting:
        row = self.db.get(ContactSetting, "global")
        if row is None:
            row = ContactSetting(key="global", inactivity_days=45,
                                 updated_by=self.actor.id)
            self.db.add(row)
            self.db.flush()
        return row

    def _inactive(self, row: ContactClient, days: int) -> bool | None:
        """Inatividade por compras so e calculada com ultima compra confiavel."""
        if row.last_purchase_on is None:
            return None
        return (date.today() - row.last_purchase_on.date()).days > days

    def _client(self, row: ContactClient, inactivity_days: int | None = None) -> dict:
        days = inactivity_days if inactivity_days is not None else 45
        birthday = None
        if row.birthday_day and row.birthday_month:
            birthday = f"{row.birthday_day:02d}/{row.birthday_month:02d}"
        return {
            "id": str(row.id), "store_code": row.store_code,
            "name": row.name, "phone": row.phone, "cellphone": row.cellphone,
            "city": row.city, "contact_person": row.contact_person,
            "birthday": birthday, "birthday_day": row.birthday_day,
            "birthday_month": row.birthday_month,
            "status": row.status, "tag": row.tag,
            "last_contact_on": day_iso(row.last_contact_on),
            "erp_code": row.erp_code, "origin": row.origin,
            "notes": row.notes,
            "last_purchase_on": day_iso(row.last_purchase_on),
            "revision": row.revision,
            "inactive_by_purchases": self._inactive(row, days),
        }

    def clients_page(self, store: str, *, q: str | None = None,
                     city: str | None = None, status: str | None = None,
                     tag: str | None = None, phone: str | None = None,
                     inactive: str | None = None,
                     page: int = 1, page_size: int = 50) -> dict:
        self.require(store, "telemarketing.view")
        days = self._settings().inactivity_days
        conditions = self._client_conditions(
            store, q=q, city=city, status=status, tag=tag, phone=phone,
            inactive=inactive, days=days)
        total = self.db.scalar(
            select(func.count()).select_from(ContactClient).where(*conditions))
        rows = self.db.scalars(
            select(ContactClient).where(*conditions)
            .order_by(ContactClient.name)
            .offset((page - 1) * page_size).limit(page_size)
        ).all()
        return {"store_code": store, "total": total or 0, "page": page,
                "page_size": page_size,
                "items": [self._client(row, days) for row in rows]}

    @staticmethod
    def _client_conditions(store: str, *, q, city, status, tag, phone,
                           inactive, days) -> list:
        conditions = [ContactClient.store_code == store]
        if q:
            conditions.append(or_(
                ContactClient.name_key.like(f"%{normalize(q)}%"),
                ContactClient.contact_person.ilike(f"%{q.strip()}%"),
            ))
        if city:
            conditions.append(ContactClient.city == city)
        if status:
            conditions.append(ContactClient.status == status)
        if tag:
            conditions.append(func.lower(ContactClient.tag) == tag.strip().lower())
        if phone:
            wanted = phone_digits(phone)
            if wanted:
                conditions.append(or_(
                    ContactClient.phone_norm.like(f"%{wanted}%"),
                    ContactClient.cellphone_norm.like(f"%{wanted}%"),
                ))
        if inactive == "sim":
            limit = date.today() - timedelta(days=days)
            conditions.append(ContactClient.last_purchase_on.is_not(None))
            conditions.append(ContactClient.last_purchase_on < date_time(limit))
        elif inactive == "nao":
            limit = date.today() - timedelta(days=days)
            conditions.append(ContactClient.last_purchase_on.is_not(None))
            conditions.append(ContactClient.last_purchase_on >= date_time(limit))
        return conditions

    def export_clients(self, store: str, *, q=None, city=None, status=None,
                       tag=None, phone=None, inactive=None,
                       fmt: str = "csv") -> tuple[bytes, str, str]:
        """Exporta a carteira filtrada completa (todas as linhas, sem limite)."""
        self.require(store, "telemarketing.view")
        days = self._settings().inactivity_days
        conditions = self._client_conditions(
            store, q=q, city=city, status=status, tag=tag, phone=phone,
            inactive=inactive, days=days)
        rows = self.db.scalars(select(ContactClient).where(*conditions)
                               .order_by(ContactClient.name)).all()
        header = ["Empresa", "Telefone", "Celular", "Cidade", "Contato",
                  "Aniversário", "Status", "Tag", "Último contato",
                  "Última compra", "Origem", "Observações"]
        def birthday(row):
            if row.birthday_day and row.birthday_month:
                return f"{row.birthday_day:02d}/{row.birthday_month:02d}"
            return ""
        body = [[_safe_cell(c) for c in [
            row.name, row.phone or "", row.cellphone or "", row.city or "",
            row.contact_person or "", birthday(row), row.status or "",
            row.tag or "",
            row.last_contact_on.strftime("%d/%m/%Y") if row.last_contact_on else "",
            row.last_purchase_on.strftime("%d/%m/%Y") if row.last_purchase_on else "",
            row.origin or "", row.notes or ""]] for row in rows]
        stamp = date.today().isoformat()
        self.audit("telemarketing.wallet.exported", "contact_client", store,
                   {"store": store, "format": fmt, "rows": len(body)})
        if fmt == "xlsx":
            import openpyxl
            book = openpyxl.Workbook()
            sheet = book.active
            sheet.title = "Carteira"
            sheet.append(header)
            for entry in body:
                sheet.append(entry)
            buffer = io.BytesIO()
            book.save(buffer)
            return (buffer.getvalue(), f"carteira_{store}_{stamp}.xlsx",
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        buffer = io.StringIO()
        writer = csv.writer(buffer, delimiter=";", lineterminator="\r\n")
        writer.writerow(header)
        writer.writerows(body)
        return (buffer.getvalue().encode("utf-8-sig"),
                f"carteira_{store}_{stamp}.csv", "text/csv; charset=utf-8")

    def client_filters(self, store: str) -> dict:
        self.require(store, "telemarketing.view")
        cities = self.db.scalars(
            select(ContactClient.city).where(
                ContactClient.store_code == store, ContactClient.city.is_not(None))
            .distinct().order_by(ContactClient.city)).all()
        return {"cities": cities,
                "statuses": list(CLIENT_STATUSES),
                "tags": self.tags(store)}

    def client_detail(self, store: str, client_id: UUID, *,
                      history_page: int = 1, history_size: int = 50) -> dict:
        self.require(store, "telemarketing.view")
        row = self.db.scalar(select(ContactClient).where(
            ContactClient.id == client_id, ContactClient.store_code == store))
        if not row:
            raise OperationError(404, "Cliente não encontrado nesta loja")
        days = self._settings().inactivity_days
        hist_total = self.db.scalar(
            select(func.count()).select_from(ContactAttempt)
            .where(ContactAttempt.client_id == row.id)) or 0
        attempts = self.db.execute(
            select(ContactAttempt, User.display_name)
            .join(User, User.id == ContactAttempt.seller_id)
            .where(ContactAttempt.client_id == row.id)
            .order_by(ContactAttempt.contacted_on.desc(),
                      ContactAttempt.created_at.desc())
            .offset((history_page - 1) * history_size).limit(history_size)
        ).all()
        pending_rows = self.db.execute(
            select(ContactAttempt, User.display_name)
            .join(User, User.id == ContactAttempt.seller_id)
            .where(ContactAttempt.client_id == row.id,
                   ContactAttempt.next_on.is_not(None),
                   ContactAttempt.followup_done_at.is_(None))
            .order_by(ContactAttempt.next_on)
        ).all()
        today = date.today()
        return {**self._client(row, days),
                "inactivity_days": days,
                "days_since_purchase": (
                    (today - row.last_purchase_on.date()).days
                    if row.last_purchase_on else None),
                "history": {"items": [self._call(attempt, row.name, seller)
                                      for attempt, seller in attempts],
                            "total": hist_total,
                            "page": history_page,
                            "page_size": history_size},
                "pending_followups": [
                    self._call(attempt, row.name, seller)
                    for attempt, seller in pending_rows]}

    def _client_warnings(self, store: str, *, name: str, phone: str | None,
                         cellphone: str | None, city: str | None,
                         contact_person: str | None, tag: str | None,
                         last_purchase_on: date | None,
                         last_contact_on: date | None,
                         exclude_id: UUID | None = None) -> list[dict]:
        """Inconsistencias avisadas, nunca bloqueadas silenciosamente."""
        warnings: list[dict] = []
        scope = [ContactClient.store_code == store]
        if exclude_id:
            scope.append(ContactClient.id != exclude_id)
        twin = self.db.scalar(select(ContactClient).where(
            *scope, ContactClient.name_key == normalize(name)).limit(1))
        if twin:
            warnings.append({
                "code": "nome_duplicado",
                "message": f"Já existe um cliente com este nome na carteira: {twin.name}.",
            })
        wanted = {digits for digits in
                  (phone_digits(phone), phone_digits(cellphone)) if len(digits) >= 8}
        if wanted:
            rows = self.db.scalars(select(ContactClient).where(
                *scope,
                or_(ContactClient.phone_norm.in_(wanted),
                    ContactClient.cellphone_norm.in_(wanted)))).all()
            for other in rows:
                known = {phone_digits(other.phone), phone_digits(other.cellphone)} - {""}
                if known & wanted:
                    warnings.append({
                        "code": "telefone_duplicado",
                        "message": ("Este telefone já está associado a outro cliente: "
                                    f"{other.name}."),
                    })
                    break
        if not (tag or "").strip():
            warnings.append({
                "code": "sem_tag",
                "message": ("Este cliente está sendo cadastrado sem classificação "
                            "comercial (tag)."),
            })
        missing = []
        if not (phone_digits(phone) or phone_digits(cellphone)):
            missing.append("telefone/celular")
        if not (city or "").strip():
            missing.append("cidade")
        if not (contact_person or "").strip():
            missing.append("pessoa de contato")
        if missing:
            warnings.append({
                "code": "dados_incompletos",
                "message": ("Existem informações não preenchidas neste cadastro: "
                            + ", ".join(missing) + "."),
            })
        today = date.today()
        odd = []
        if last_purchase_on and last_purchase_on > today:
            odd.append("última compra no futuro")
        if last_purchase_on and last_purchase_on.year < 1990:
            odd.append("última compra muito antiga")
        if last_contact_on and last_contact_on > today:
            odd.append("último contato no futuro")
        if odd:
            warnings.append({
                "code": "data_inconsistente",
                "message": ("A data informada parece estar fora do período esperado: "
                            + ", ".join(odd) + "."),
            })
        return warnings

    def _register_tag(self, tag: str | None) -> str | None:
        clean = " ".join((tag or "").split())
        if not clean:
            return None
        key = normalize(clean)
        if not self.db.scalar(select(ContactTag.id).where(ContactTag.name_key == key)):
            self.db.add(ContactTag(id=uuid4(), name=clean, name_key=key,
                                   created_by=self.actor.id))
        return clean

    def tags(self, store: str) -> list[str]:
        self.require(store, "telemarketing.view")
        catalog = self.db.scalars(select(ContactTag.name).order_by(ContactTag.name)).all()
        in_use = self.db.scalars(
            select(ContactClient.tag).where(
                ContactClient.store_code == store, ContactClient.tag.is_not(None))
            .distinct()).all()
        return sorted({*catalog, *in_use}, key=str.casefold)

    def add_client(self, store: str, *, name: str, phone: str | None,
                   cellphone: str | None = None, erp_code: str | None = None,
                   origin: str, city: str | None = None,
                   contact_person: str | None = None,
                   birthday_day: int | None = None,
                   birthday_month: int | None = None,
                   status: str | None = None, tag: str | None = None,
                   last_contact_on: date | None = None,
                   notes: str | None = None,
                   last_purchase_on: date | None = None,
                   confirm: bool = False) -> dict:
        self.require(store, "telemarketing.edit")
        clean = name.strip()
        if not clean:
            raise OperationError(422, "Informe o nome do cliente")
        if status and status not in CLIENT_STATUSES:
            raise OperationError(422, "Status comercial inválido")
        warnings = self._client_warnings(
            store, name=clean, phone=phone, cellphone=cellphone, city=city,
            contact_person=contact_person, tag=tag,
            last_purchase_on=last_purchase_on, last_contact_on=last_contact_on)
        if warnings and not confirm:
            return {"result": "review", "warnings": warnings}
        row = ContactClient(
            id=uuid4(), store_code=store, name=clean, name_key=normalize(clean),
            phone=phone, phone_norm=phone_digits(phone) or None,
            cellphone=cellphone, cellphone_norm=phone_digits(cellphone) or None,
            city=(city or "").strip() or None,
            contact_person=(contact_person or "").strip() or None,
            birthday_day=birthday_day, birthday_month=birthday_month,
            status=status, tag=self._register_tag(tag),
            last_contact_on=date_time(last_contact_on), notes=notes,
            erp_code=erp_code, origin=origin,
            last_purchase_on=date_time(last_purchase_on),
            revision=1, created_by=self.actor.id,
        )
        self.db.add(row)
        self.db.flush()
        self.audit("telemarketing.client.created", "contact_client", str(row.id),
                   {"store": store, "origin": origin,
                    "confirmed_warnings": [w["code"] for w in warnings]})
        self.commit()
        return {"result": "saved", "client": self._client(row),
                "warnings": warnings}

    def update_client(self, store: str, client_id: UUID, *, expected: int,
                      confirm: bool = False, **fields) -> dict:
        self.require(store, "telemarketing.edit")
        row = self.db.scalar(select(ContactClient).where(
            ContactClient.id == client_id, ContactClient.store_code == store
        ).with_for_update())
        if not row:
            raise OperationError(404, "Cliente não encontrado nesta loja")
        self.revision(row, expected)
        clean = (fields.get("name") or "").strip() or row.name
        status = fields.get("status", row.status)
        if status and status not in CLIENT_STATUSES:
            raise OperationError(422, "Status comercial inválido")
        warnings = self._client_warnings(
            store, name=clean, phone=fields.get("phone", row.phone),
            cellphone=fields.get("cellphone", row.cellphone),
            city=fields.get("city", row.city),
            contact_person=fields.get("contact_person", row.contact_person),
            tag=fields.get("tag", row.tag),
            last_purchase_on=fields.get("last_purchase_on",
                                      row.last_purchase_on.date() if row.last_purchase_on else None),
            last_contact_on=fields.get("last_contact_on",
                                     row.last_contact_on.date() if row.last_contact_on else None),
            exclude_id=row.id)
        if warnings and not confirm:
            return {"result": "review", "warnings": warnings,
                    "revision": row.revision}
        before = self._client(row)
        row.name = clean
        row.name_key = normalize(clean)
        for column in ("phone", "cellphone", "city", "contact_person", "tag",
                       "status", "erp_code", "notes", "origin"):
            if column in fields:
                value = fields[column]
                setattr(row, column,
                        " ".join(value.split()) if isinstance(value, str) and value else value)
        if "tag" in fields:
            row.tag = self._register_tag(fields["tag"])
        if "phone" in fields:
            row.phone_norm = phone_digits(row.phone) or None
        if "cellphone" in fields:
            row.cellphone_norm = phone_digits(row.cellphone) or None
        for column in ("birthday_day", "birthday_month"):
            if column in fields:
                setattr(row, column, fields[column])
        for column in ("last_purchase_on", "last_contact_on"):
            if column in fields:
                setattr(row, column, date_time(fields[column]))
        row.revision += 1
        row.updated_by = self.actor.id
        self.audit("telemarketing.client.updated", "contact_client", str(row.id),
                   {"store": store, "before": before, "after": self._client(row),
                    "confirmed_warnings": [w["code"] for w in warnings]})
        self.commit()
        return {"result": "saved", "client": self._client(row),
                "warnings": warnings}

    def contact_settings(self, store: str) -> dict:
        self.require(store, "telemarketing.view")
        row = self._settings()
        return {"inactivity_days": row.inactivity_days}

    def save_settings(self, store: str, inactivity_days: int) -> dict:
        self.require(store, "telemarketing.admin")
        if not 1 <= inactivity_days <= 365:
            raise OperationError(422, "Informe um prazo entre 1 e 365 dias")
        row = self._settings()
        before = row.inactivity_days
        row.inactivity_days = inactivity_days
        row.updated_by = self.actor.id
        self.audit("telemarketing.settings.updated", "contact_settings", "global",
                   {"before": before, "after": inactivity_days, "store": store})
        self.commit()
        return {"inactivity_days": row.inactivity_days}

    def followups(self, store: str, *, state: str = "abertos",
                  page: int = 1, page_size: int = 100) -> dict:
        self.require(store, "telemarketing.view")
        conditions = [ContactAttempt.store_code == store,
                      ContactAttempt.next_on.is_not(None)]
        today = date.today()
        if state == "abertos":
            conditions.append(ContactAttempt.followup_done_at.is_(None))
        elif state == "atrasados":
            conditions.append(ContactAttempt.followup_done_at.is_(None))
            conditions.append(ContactAttempt.next_on < date_time(today))
        elif state == "realizados":
            conditions.append(ContactAttempt.followup_done_at.is_not(None))
        elif state != "todos":
            raise OperationError(422, "Filtro de retornos inválido")
        total = self.db.scalar(
            select(func.count()).select_from(ContactAttempt).where(*conditions))
        rows = self.db.execute(
            select(ContactAttempt, ContactClient.name, User.display_name)
            .join(ContactClient, ContactClient.id == ContactAttempt.client_id)
            .join(User, User.id == ContactAttempt.seller_id)
            .where(*conditions)
            .order_by(ContactAttempt.followup_done_at.is_not(None),
                      ContactAttempt.next_on)
            .offset((page - 1) * page_size).limit(page_size)
        ).all()
        return {"store_code": store, "total": total or 0, "page": page,
                "page_size": page_size,
                "items": [{**self._call(attempt, client, seller),
                           "overdue": (attempt.next_on.date() < today
                                       and attempt.followup_done_at is None)}
                          for attempt, client, seller in rows]}

    def complete_followup(self, store: str, call_id: UUID, expected: int) -> dict:
        self.require(store, "telemarketing.edit")
        row = self.db.scalar(select(ContactAttempt).where(
            ContactAttempt.id == call_id, ContactAttempt.store_code == store
        ).with_for_update())
        if not row or row.next_on is None:
            raise OperationError(404, "Retorno não encontrado")
        self.revision(row, expected)
        if row.followup_done_at is not None:
            raise OperationError(409, "Este retorno já foi marcado como realizado")
        row.followup_done_at = datetime.now()
        row.revision += 1
        row.updated_by = self.actor.id
        self.audit("telemarketing.followup.done", "contact_attempt", str(row.id),
                   {"store": store, "client_id": str(row.client_id),
                    "next_on": day_iso(row.next_on)})
        self.commit()
        client = self.db.get(ContactClient, row.client_id)
        seller = self.db.get(User, row.seller_id)
        return {**self._call(row, client.name, seller.display_name), "overdue": False}

    def reschedule_followup(self, store: str, call_id: UUID, *,
                            next_on: date, expected: int) -> dict:
        self.require(store, "telemarketing.edit")
        row = self.db.scalar(select(ContactAttempt).where(
            ContactAttempt.id == call_id, ContactAttempt.store_code == store
        ).with_for_update())
        if not row or row.next_on is None:
            raise OperationError(404, "Retorno não encontrado")
        self.revision(row, expected)
        before = day_iso(row.next_on)
        row.next_on = date_time(next_on)
        row.followup_done_at = None
        row.revision += 1
        row.updated_by = self.actor.id
        self.audit("telemarketing.followup.rescheduled", "contact_attempt", str(row.id),
                   {"store": store, "before": before, "after": next_on.isoformat()})
        self.commit()
        client = self.db.get(ContactClient, row.client_id)
        seller = self.db.get(User, row.seller_id)
        return {**self._call(row, client.name, seller.display_name),
                "overdue": next_on < date.today()}

    def metrics(self, store: str, year: int, month: int) -> dict:
        self.require(store, "telemarketing.view")
        self.period(year, month)
        days = self._settings().inactivity_days
        today = date.today()
        base = select(ContactClient).where(ContactClient.store_code == store)
        total = self.db.scalar(select(func.count()).select_from(base.subquery()))
        by_status = dict(self.db.execute(
            select(func.coalesce(ContactClient.status, "sem_status"), func.count())
            .where(ContactClient.store_code == store)
            .group_by(ContactClient.status)).all())
        by_city = self.db.execute(
            select(func.coalesce(ContactClient.city, "Sem cidade"), func.count())
            .where(ContactClient.store_code == store)
            .group_by(ContactClient.city)
            .order_by(func.count().desc())).all()
        by_tag = self.db.execute(
            select(func.coalesce(ContactClient.tag, "Sem tag"), func.count())
            .where(ContactClient.store_code == store)
            .group_by(ContactClient.tag)
            .order_by(func.count().desc())).all()
        start = datetime(year, month, 1)
        end = datetime(year + (1 if month == 12 else 0),
                       1 if month == 12 else month + 1, 1)
        contacts = self.db.scalar(select(func.count()).select_from(ContactAttempt).where(
            ContactAttempt.store_code == store,
            ContactAttempt.contacted_on >= start, ContactAttempt.contacted_on < end))
        contacted = self.db.scalar(
            select(func.count(func.distinct(ContactAttempt.client_id))).where(
                ContactAttempt.store_code == store,
                ContactAttempt.contacted_on >= start, ContactAttempt.contacted_on < end))
        pending = self.db.scalar(select(func.count()).select_from(ContactAttempt).where(
            ContactAttempt.store_code == store, ContactAttempt.next_on.is_not(None),
            ContactAttempt.followup_done_at.is_(None)))
        overdue = self.db.scalar(select(func.count()).select_from(ContactAttempt).where(
            ContactAttempt.store_code == store, ContactAttempt.next_on.is_not(None),
            ContactAttempt.followup_done_at.is_(None),
            ContactAttempt.next_on < date_time(today)))
        inactive = self.db.scalar(select(func.count()).select_from(ContactClient).where(
            ContactClient.store_code == store,
            ContactClient.last_purchase_on.is_not(None),
            ContactClient.last_purchase_on < date_time(
                today - timedelta(days=days))))
        return {"store_code": store, "year": year, "month": month,
                "inactivity_days": days,
                "clients_total": total or 0,
                "by_status": by_status,
                "by_city": [{"city": city, "total": count} for city, count in by_city],
                "by_tag": [{"tag": tag, "total": count} for tag, count in by_tag],
                "contacts_in_period": contacts or 0,
                "clients_contacted": contacted or 0,
                "followups_pending": pending or 0,
                "followups_overdue": overdue or 0,
                "inactive_by_purchases": inactive or 0}

    # ---- Importacao de carteira ----

    def _import_matches(self, store: str, record: dict,
                        clients: list[ContactClient]) -> list[dict]:
        wanted = {digits for digits in
                  (phone_digits(record.get("phone")),
                   phone_digits(record.get("cellphone"))) if len(digits) >= 8}
        matches = []
        key = normalize(record["name"])
        for client in clients:
            kinds = []
            if client.name_key == key:
                kinds.append("nome")
            known = {phone_digits(client.phone), phone_digits(client.cellphone)} - {""}
            if wanted & known:
                kinds.append("telefone")
            if client.erp_code and record.get("erp_code") \
                    and client.erp_code == record["erp_code"]:
                kinds.append("erp")
            if kinds:
                matches.append({"id": str(client.id), "name": client.name,
                                "city": client.city, "kinds": kinds})
        return matches

    def import_preview(self, store: str, *, filename: str, data: bytes,
                       default_city: str | None) -> dict:
        self.require(store, "telemarketing.admin")
        from app.televendas_import import parse_file
        try:
            records = parse_file(filename, data, default_city)
        except ValueError as error:
            raise OperationError(422, str(error)) from error
        if not records:
            raise OperationError(422, "Nenhum cliente encontrado no arquivo")
        clients = self.db.scalars(select(ContactClient).where(
            ContactClient.store_code == store)).all()
        cities: dict[str, int] = {}
        warnings_total = 0
        duplicated = 0
        for record in records:
            city = record.get("city") or "Sem cidade"
            cities[city] = cities.get(city, 0) + 1
            matches = self._import_matches(store, record, clients)
            record["matches"] = matches
            record["suggested"] = "update" if any(
                {"telefone", "erp"} & set(m["kinds"]) for m in matches
            ) else "import"
            if record["warnings"]:
                warnings_total += 1
            if matches:
                duplicated += 1
        session = ClientImportSession(
            id=uuid4(), store_code=store, filename=filename[:160],
            payload={"rows": records}, created_by=self.actor.id)
        self.db.add(session)
        self.audit("telemarketing.import.preview", "client_import_session",
                   str(session.id),
                   {"store": store, "filename": filename, "rows": len(records)})
        self.commit()
        return {"session_id": str(session.id), "filename": filename,
                "rows_total": len(records),
                "expires_at": (session.created_at
                               + IMPORT_PREVIEW_TTL).isoformat(),
                "cities": [{"city": c, "total": n}
                           for c, n in sorted(cities.items())],
                "rows": records,
                "summary": {"with_warnings": warnings_total,
                            "possible_duplicates": duplicated}}

    def _expire_preview(self, session: ClientImportSession) -> None:
        """Descarta previa vencida, purgando dados brutos da planilha."""
        if session.state == "preview" and (
                session.created_at + IMPORT_PREVIEW_TTL < datetime.now()):
            session.state = "discarded"
            session.payload = {}
            self.audit("telemarketing.import.expired", "client_import_session",
                       str(session.id),
                       {"store": session.store_code,
                        "filename": session.filename})
            self.commit()

    def import_commit(self, store: str, session_id: UUID, *,
                      decisions: dict[str, dict], confirm: bool) -> dict:
        self.require(store, "telemarketing.admin")
        session = self.db.scalar(select(ClientImportSession).where(
            ClientImportSession.id == session_id,
            ClientImportSession.store_code == store).with_for_update())
        if not session:
            raise OperationError(404, "Prévia de importação não encontrada")
        self._expire_preview(session)
        if session.state != "preview":
            raise OperationError(409, "Esta importação já foi concluída, "
                                      "descartada ou expirou")
        rows = session.payload.get("rows", [])
        warned = [r for r in rows
                  if decisions.get(str(r["index"]), {}).get(
                      "action", r.get("suggested", "import")) != "skip"
                  and (r["warnings"] or r["matches"])]
        if warned and not confirm:
            return {"result": "review",
                    "message": ("Existem registros com avisos ou possíveis "
                                "duplicidades. Confirme para continuar."),
                    "flagged": len(warned)}
        clients = self.db.scalars(select(ContactClient).where(
            ContactClient.store_code == store)).all()
        by_id = {str(c.id): c for c in clients}
        report = {"imported": 0, "updated": 0, "skipped": 0, "warnings": 0,
                  "details": []}
        for record in rows:
            index = str(record["index"])
            decision = decisions.get(index, {})
            action = decision.get("action", record.get("suggested", "import"))
            if decision.get("city"):
                record["city"] = " ".join(decision["city"].split())[:60]
            if action == "skip":
                report["skipped"] += 1
                continue
            if action == "update":
                wanted_id = decision.get("client_id")
                target = by_id.get(str(wanted_id)) if wanted_id else None
                if target is None:
                    raise OperationError(422, (
                        f"Linha {index}: 'Atualizar existente' exige a seleção "
                        "explícita de um cadastro válido desta loja."))
                else:
                    before = self._client(target)
                    self._apply_import(target, record)
                    target.revision += 1
                    target.updated_by = self.actor.id
                    self.audit("telemarketing.import.updated", "contact_client",
                               str(target.id),
                               {"store": store, "before": before,
                                "after": self._client(target)})
                    report["updated"] += 1
                    report["warnings"] += bool(record["warnings"])
                    report["details"].append(
                        {"index": record["index"], "action": "updated",
                         "client": target.name})
                    continue
            row = ContactClient(
                id=uuid4(), store_code=store,
                name=record["name"][:100], name_key=normalize(record["name"]),
                phone=record.get("phone"),
                phone_norm=phone_digits(record.get("phone")) or None,
                cellphone=record.get("cellphone"),
                cellphone_norm=phone_digits(record.get("cellphone")) or None,
                city=record.get("city"),
                contact_person=record.get("contact_person"),
                birthday_day=record.get("birthday_day"),
                birthday_month=record.get("birthday_month"),
                status=record.get("status"), tag=self._register_tag(record.get("tag")),
                last_contact_on=date_time(
                    date.fromisoformat(record["last_contact_on"]))
                if record.get("last_contact_on") else None,
                notes=record.get("notes"),
                erp_code=record.get("erp_code"), origin="planilha",
                revision=1, created_by=self.actor.id)
            self.db.add(row)
            self.db.flush()
            by_id[str(row.id)] = row
            report["imported"] += 1
            report["warnings"] += bool(record["warnings"])
            report["details"].append({"index": record["index"],
                                      "action": "imported",
                                      "client": row.name})
        for entry in report["details"]:
            record = next(r for r in rows if r["index"] == entry["index"])
            raws = {key: record[key] for key in
                    ("birthday_raw", "last_contact_raw", "status_raw")
                    if record.get(key) is not None}
            if record.get("warnings"):
                entry["warnings"] = list(record["warnings"])
            if raws:
                entry["raw_values"] = raws
        session.state = "applied"
        session.applied_at = datetime.now()
        session.report = report
        session.payload = {}
        self.audit("telemarketing.import.applied", "client_import_session",
                   str(session.id),
                   {"store": store, "filename": session.filename,
                    **{k: v for k, v in report.items() if k != "details"}})
        self.commit()
        return {"result": "saved", "report": {k: v for k, v in report.items()
                                              if k != "details"},
                "details": report["details"][:50]}

    def import_discard(self, store: str, session_id: UUID) -> dict:
        self.require(store, "telemarketing.admin")
        session = self.db.scalar(select(ClientImportSession).where(
            ClientImportSession.id == session_id,
            ClientImportSession.store_code == store).with_for_update())
        if not session:
            raise OperationError(404, "Prévia de importação não encontrada")
        self._expire_preview(session)
        if session.state != "preview":
            raise OperationError(409, "Esta importação já foi concluída, "
                                      "descartada ou expirou")
        session.state = "discarded"
        session.payload = {}
        self.audit("telemarketing.import.discarded", "client_import_session",
                   str(session.id),
                   {"store": store, "filename": session.filename})
        self.commit()
        return {"result": "discarded"}

    @staticmethod
    def _apply_import(client: ContactClient, record: dict) -> None:
        """Atualiza cadastro existente apenas com valores presentes no arquivo."""
        mapping = {"phone": "phone", "cellphone": "cellphone", "city": "city",
                   "contact_person": "contact_person", "status": "status",
                   "tag": "tag", "notes": "notes"}
        for source, column in mapping.items():
            value = record.get(source)
            if value:
                setattr(client, column, value)
        client.phone_norm = phone_digits(client.phone) or client.phone_norm
        client.cellphone_norm = (phone_digits(client.cellphone)
                                 or client.cellphone_norm)
        for column in ("birthday_day", "birthday_month"):
            if record.get(column):
                setattr(client, column, record[column])
        if record.get("last_contact_on"):
            client.last_contact_on = date_time(
                date.fromisoformat(record["last_contact_on"]))

    @staticmethod
    def _seller_store_filter(store: str):
        """Colaboradores com funcao de vendedor autorizados na loja pelo grupo.

        O escopo individual (user_store_scopes) restringe a abrangencia do
        grupo: vazio herda todas as lojas do grupo; preenchido, a loja
        precisa constar no escopo do usuario."""
        covered = (
            select(AccessGroupStore.group_id)
            .where(AccessGroupStore.store_code == store)
        )
        any_scope = select(UserStoreScope.user_id).where(
            UserStoreScope.user_id == User.id
        ).exists()
        store_scoped = select(UserStoreScope.user_id).where(
            UserStoreScope.user_id == User.id,
            UserStoreScope.store_code == store,
        ).exists()
        return (
            User.profile == "seller",
            User.active.is_(True),
            AccessGroup.active.is_(True),
            GroupMembership.group_id.in_(covered),
            or_(~any_scope, store_scoped),
        )

    def sellers(self, store: str) -> list[dict]:
        if not (can_access(self.principal, "telemarketing.view", store)
                or can_access(self.principal, "training.edit", store)):
            raise OperationError(403, "Acesso negado")
        rows = self.db.execute(
            select(User.id, User.display_name)
            .join(GroupMembership, GroupMembership.user_id == User.id)
            .join(AccessGroup, AccessGroup.id == GroupMembership.group_id)
            .where(*self._seller_store_filter(store))
            .distinct().order_by(User.display_name)
        ).all()
        return [{"id": str(id), "name": name} for id, name in rows]

    def _seller_in_store(self, store: str, seller_id: UUID) -> bool:
        return self.db.scalar(
            select(User.id).join(GroupMembership, GroupMembership.user_id == User.id)
            .join(AccessGroup, AccessGroup.id == GroupMembership.group_id)
            .where(User.id == seller_id, *self._seller_store_filter(store))
        ) is not None

    def calls(self, store: str, year: int, month: int, *,
              page: int = 1, page_size: int = 100) -> dict:
        self.require(store, "telemarketing.view")
        self.period(year, month)
        scope = [ContactAttempt.store_code == store,
                 ContactAttempt.contacted_on >= datetime(year, month, 1),
                 ContactAttempt.contacted_on < datetime(
                     year + (1 if month == 12 else 0),
                     1 if month == 12 else month + 1, 1)]
        total = self.db.scalar(select(func.count()).select_from(
            ContactAttempt).where(*scope)) or 0
        rows = self.db.execute(
            select(ContactAttempt, ContactClient.name, User.display_name)
            .join(ContactClient, ContactClient.id == ContactAttempt.client_id)
            .join(User, User.id == ContactAttempt.seller_id)
            .where(*scope)
            .order_by(ContactAttempt.contacted_on.desc(), ContactAttempt.created_at.desc())
            .offset((page - 1) * page_size).limit(page_size)
        ).all()
        return {"store_code": store, "year": year, "month": month,
                "total": total, "page": page, "page_size": page_size,
                "items": [self._call(row, name, seller)
                          for row, name, seller in rows]}

    @staticmethod
    def _call(row: ContactAttempt, client_name: str, seller_name: str) -> dict:
        return {"id": str(row.id), "store_code": row.store_code,
                "client_id": str(row.client_id), "client": client_name,
                "seller_id": str(row.seller_id), "seller": seller_name,
                "date": day_iso(row.contacted_on), "outcome": row.outcome,
                "channel": row.channel,
                "next_on": day_iso(row.next_on),
                "followup_done_at": row.followup_done_at.isoformat()
                    if row.followup_done_at else None,
                "note": row.note,
                "revision": row.revision}

    def add_call(self, store: str, *, client_id: UUID, seller_id: UUID,
                 contacted_on: date, outcome: str, next_on: date | None, note: str,
                 channel: str = "ligacao") -> dict:
        self.require(store, "telemarketing.edit")
        client = self.db.get(ContactClient, client_id)
        if not client or client.store_code != store:
            raise OperationError(422, "Cliente não pertence a esta loja")
        if not self._seller_in_store(store, seller_id):
            raise OperationError(422, "Vendedor não pertence à loja ou está inativo")
        row = ContactAttempt(
            id=uuid4(), store_code=store, client_id=client_id,
            seller_id=seller_id, contacted_on=date_time(contacted_on),
            channel=channel, outcome=outcome, next_on=date_time(next_on), note=note,
            revision=1, created_by=self.actor.id, updated_by=self.actor.id,
        )
        self.db.add(row)
        if (client.last_contact_on is None
                or row.contacted_on > client.last_contact_on):
            client.last_contact_on = row.contacted_on
            client.revision += 1
            client.updated_by = self.actor.id
        self.audit("telemarketing.call.created", "contact_attempt", str(row.id),
                   {"store": store, "date": contacted_on.isoformat(),
                    "client_id": str(client_id), "seller_id": str(seller_id),
                    "outcome": outcome})
        self.commit()
        seller=self.db.get(User, seller_id)
        return self._call(row, client.name, seller.display_name)

    def update_call(self, store: str, call_id: UUID, *, contacted_on: date,
                    outcome: str, next_on: date | None, note: str, expected: int,
                    channel: str = "ligacao") -> dict:
        self.require(store, "telemarketing.edit")
        row = self.db.scalar(select(ContactAttempt).where(
            ContactAttempt.id == call_id, ContactAttempt.store_code == store
        ).with_for_update())
        if not row:
            raise OperationError(404, "Ligação não encontrada")
        self.revision(row, expected)
        before = {"date": day_iso(row.contacted_on), "outcome": row.outcome,
                  "channel": row.channel,
                  "next_on": day_iso(row.next_on), "note": row.note}
        previous_on = row.contacted_on
        row.contacted_on = date_time(contacted_on)
        row.outcome = outcome
        row.channel = channel
        row.next_on = date_time(next_on)
        row.note = note
        row.revision += 1
        row.updated_by = self.actor.id
        self.db.flush()
        client = self.db.get(ContactClient, row.client_id)
        if client:
            if client.last_contact_on is not None and (
                    client.last_contact_on == previous_on):
                client.last_contact_on = self.db.scalar(
                    select(func.max(ContactAttempt.contacted_on)).where(
                        ContactAttempt.client_id == client.id))
                client.revision += 1
                client.updated_by = self.actor.id
            elif client.last_contact_on is None or (
                    row.contacted_on > client.last_contact_on):
                client.last_contact_on = row.contacted_on
                client.revision += 1
                client.updated_by = self.actor.id
        self.audit("telemarketing.call.corrected", "contact_attempt", str(row.id),
                   {"before": before,
                    "after": {"date": contacted_on.isoformat(), "outcome": outcome,
                              "channel": channel,
                              "next_on": next_on.isoformat() if next_on else None, "note": note},
                    "store": store})
        self.commit()
        client=self.db.get(ContactClient, row.client_id)
        seller=self.db.get(User, row.seller_id)
        return self._call(row, client.name, seller.display_name)
