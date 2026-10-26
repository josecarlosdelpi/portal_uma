"""Application services for ERP-independent operational routines.

Authorization, store boundaries and audit are checked inside each use case.
Seller accounts remain read-only as approved for operational v1.
"""
from datetime import date, datetime, time
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    AuditEvent, ContactAttempt, ContactClient, GoogleReviewMonth, GroupMembership,
    StoreGroup, SupplyMaterial, SupplyMovement, SupplyStock, User,
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

    def clients(self, store: str) -> list[dict]:
        self.require(store, "telemarketing.view")
        rows = self.db.scalars(
            select(ContactClient).where(ContactClient.store_code == store)
            .order_by(ContactClient.name).limit(500)
        ).all()
        return [self._client(row) for row in rows]

    @staticmethod
    def _client(row: ContactClient) -> dict:
        return {"id": str(row.id), "store_code": row.store_code,
                "name": row.name, "phone": row.phone, "erp_code": row.erp_code,
                "origin": row.origin, "last_purchase_on": day_iso(row.last_purchase_on)}

    def add_client(self, store: str, *, name: str, phone: str | None,
                   erp_code: str | None, origin: str, last_purchase_on: date | None) -> dict:
        self.require(store, "telemarketing.edit")
        clean = name.strip()
        if not clean:
            raise OperationError(422, "Informe o nome do cliente")
        if self.db.scalar(select(ContactClient.id).where(
            ContactClient.store_code == store, ContactClient.name_key == normalize(clean)
        )):
            raise OperationError(409, "Este cliente já está na carteira da loja")
        row = ContactClient(
            id=uuid4(), store_code=store, name=clean, name_key=normalize(clean),
            phone=phone, erp_code=erp_code, origin=origin,
            last_purchase_on=date_time(last_purchase_on), created_by=self.actor.id,
        )
        self.db.add(row)
        self.audit("telemarketing.client.created", "contact_client", str(row.id),
                   {"store": store, "origin": origin})
        self.commit()
        return self._client(row)

    def sellers(self, store: str) -> list[dict]:
        self.require(store, "telemarketing.view")
        rows = self.db.execute(
            select(User.id, User.display_name)
            .join(GroupMembership, GroupMembership.user_id == User.id)
            .join(StoreGroup, StoreGroup.id == GroupMembership.group_id)
            .where(
                StoreGroup.store_code == store,
                StoreGroup.active.is_(True),
                User.active.is_(True),
                User.profile == "seller",
            ).distinct().order_by(User.display_name)
        ).all()
        return [{"id": str(id), "name": name} for id, name in rows]

    def _seller_in_store(self, store: str, seller_id: UUID) -> bool:
        return self.db.scalar(
            select(User.id).join(GroupMembership, GroupMembership.user_id == User.id)
            .join(StoreGroup, StoreGroup.id == GroupMembership.group_id)
            .where(
                User.id == seller_id, User.profile == "seller", User.active.is_(True),
                StoreGroup.store_code == store, StoreGroup.active.is_(True),
            )
        ) is not None

    def calls(self, store: str, year: int, month: int) -> dict:
        self.require(store, "telemarketing.view")
        self.period(year, month)
        rows = self.db.execute(
            select(ContactAttempt, ContactClient.name, User.display_name)
            .join(ContactClient, ContactClient.id == ContactAttempt.client_id)
            .join(User, User.id == ContactAttempt.seller_id)
            .where(ContactAttempt.store_code == store)
            .where(ContactAttempt.contacted_on >= datetime(year, month, 1))
            .where(ContactAttempt.contacted_on < datetime(year + (1 if month == 12 else 0),
                                                         1 if month == 12 else month + 1, 1))
            .order_by(ContactAttempt.contacted_on.desc(), ContactAttempt.created_at.desc())
            .limit(500)
        ).all()
        return {"store_code": store, "year": year, "month": month, "items": [
            self._call(row, name, seller) for row, name, seller in rows
        ]}

    @staticmethod
    def _call(row: ContactAttempt, client_name: str, seller_name: str) -> dict:
        return {"id": str(row.id), "store_code": row.store_code,
                "client_id": str(row.client_id), "client": client_name,
                "seller_id": str(row.seller_id), "seller": seller_name,
                "date": day_iso(row.contacted_on), "outcome": row.outcome,
                "next_on": day_iso(row.next_on), "note": row.note,
                "revision": row.revision}

    def add_call(self, store: str, *, client_id: UUID, seller_id: UUID,
                 contacted_on: date, outcome: str, next_on: date | None, note: str) -> dict:
        self.require(store, "telemarketing.edit")
        client = self.db.get(ContactClient, client_id)
        if not client or client.store_code != store:
            raise OperationError(422, "Cliente não pertence a esta loja")
        if not self._seller_in_store(store, seller_id):
            raise OperationError(422, "Vendedor não pertence à loja ou está inativo")
        row = ContactAttempt(
            id=uuid4(), store_code=store, client_id=client_id,
            seller_id=seller_id, contacted_on=date_time(contacted_on),
            outcome=outcome, next_on=date_time(next_on), note=note,
            revision=1, created_by=self.actor.id, updated_by=self.actor.id,
        )
        self.db.add(row)
        self.audit("telemarketing.call.created", "contact_attempt", str(row.id),
                   {"store": store, "date": contacted_on.isoformat(),
                    "client_id": str(client_id), "seller_id": str(seller_id),
                    "outcome": outcome})
        self.commit()
        seller=self.db.get(User, seller_id)
        return self._call(row, client.name, seller.display_name)

    def update_call(self, store: str, call_id: UUID, *, contacted_on: date,
                    outcome: str, next_on: date | None, note: str, expected: int) -> dict:
        self.require(store, "telemarketing.edit")
        row = self.db.scalar(select(ContactAttempt).where(
            ContactAttempt.id == call_id, ContactAttempt.store_code == store
        ).with_for_update())
        if not row:
            raise OperationError(404, "Ligação não encontrada")
        self.revision(row, expected)
        before = {"date": day_iso(row.contacted_on), "outcome": row.outcome,
                  "next_on": day_iso(row.next_on), "note": row.note}
        row.contacted_on = date_time(contacted_on)
        row.outcome = outcome
        row.next_on = date_time(next_on)
        row.note = note
        row.revision += 1
        row.updated_by = self.actor.id
        self.audit("telemarketing.call.corrected", "contact_attempt", str(row.id),
                   {"before": before,
                    "after": {"date": contacted_on.isoformat(), "outcome": outcome,
                              "next_on": next_on.isoformat() if next_on else None, "note": note},
                    "store": store})
        self.commit()
        client=self.db.get(ContactClient, row.client_id)
        seller=self.db.get(User, row.seller_id)
        return self._call(row, client.name, seller.display_name)
