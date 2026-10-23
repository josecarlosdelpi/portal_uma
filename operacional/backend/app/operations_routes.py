"""Strictly typed HTTP routes for reviews, supply controls and telephone log."""
from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.auth import current_user
from app.db import get_db
from app.models import User
from app.operations_service import OperationError, OperationsService

router = APIRouter(prefix="/api/v1/operations", tags=["operations"])


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ReviewInput(Strict):
    count: int = Field(ge=0, le=9999)
    checked_on: date
    delivered_on: date | None = None
    note: str = Field(default="", max_length=200)
    expected_revision: int = Field(ge=0)


class MaterialInput(Strict):
    name: str = Field(min_length=1, max_length=80)
    unit: str = Field(min_length=1, max_length=30)
    minima: dict[str, int] = Field(min_length=3, max_length=3)


class MinimumInput(Strict):
    minimum: int = Field(ge=0, le=9999)
    expected_revision: int = Field(ge=1)


class MovementInput(Strict):
    store_code: str
    material_id: UUID
    kind: str = Field(pattern=r"^(entrada|retirada)$")
    quantity: int = Field(ge=1, le=9999)
    note: str = Field(default="", max_length=180)
    expected_revision: int = Field(ge=1)


class ClientInput(Strict):
    name: str = Field(min_length=1, max_length=100)
    phone: str | None = Field(default=None, max_length=40)
    erp_code: str | None = Field(default=None, max_length=50)
    origin: str = Field(pattern=r"^(google|inativo60|inativo90|carteira)$")
    last_purchase_on: date | None = None


class CallInput(Strict):
    client_id: UUID
    seller_id: UUID
    date: date
    outcome: str = Field(pattern=r"^(apresentacao|sem_resposta|whatsapp|outro)$")
    next_on: date | None = None
    note: str = Field(default="", max_length=240)


class CallCorrection(Strict):
    date: date
    outcome: str = Field(pattern=r"^(apresentacao|sem_resposta|whatsapp|outro)$")
    next_on: date | None = None
    note: str = Field(default="", max_length=240)
    expected_revision: int = Field(ge=1)


def service(user: User = Depends(current_user), db: Session = Depends(get_db)) -> OperationsService:
    return OperationsService(db, user)


def checked(fn):
    try:
        return fn()
    except OperationError as error:
        raise HTTPException(status_code=error.status_code, detail=error.message) from error


@router.get("/reviews/{year}/{month}")
def reviews(year: int = Path(ge=2020, le=2100), month: int = Path(ge=1, le=12),
            svc: OperationsService = Depends(service)) -> dict:
    return checked(lambda: svc.review_list(year, month))


@router.put("/reviews/{store_code}/{year}/{month}")
def update_reviews(
    store_code: str, body: ReviewInput, year: int = Path(ge=2020, le=2100),
    month: int = Path(ge=1, le=12), svc: OperationsService = Depends(service),
) -> dict:
    return checked(lambda: svc.save_review(
        store_code, year, month, count=body.count, checked_on=body.checked_on,
        delivered_on=body.delivered_on, note=body.note, expected=body.expected_revision
    ))


@router.get("/supplies/{store_code}")
def supplies(store_code: str, svc: OperationsService = Depends(service)) -> dict:
    return checked(lambda: svc.materials(store_code))


@router.post("/supplies/materials", status_code=201)
def create_material(body: MaterialInput, svc: OperationsService = Depends(service)) -> dict:
    if any(value < 0 or value > 9999 for value in body.minima.values()):
        raise HTTPException(status_code=422, detail="Mínimos inválidos")
    return checked(lambda: svc.create_material(body.name, body.unit, body.minima))


@router.put("/supplies/{store_code}/{material_id}/minimum")
def update_minimum(
    store_code: str, material_id: UUID, body: MinimumInput,
    svc: OperationsService = Depends(service),
) -> dict:
    return checked(lambda: svc.set_minimum(
        store_code, material_id, body.minimum, body.expected_revision
    ))


@router.post("/supplies/movements", status_code=201)
def record_movement(body: MovementInput, svc: OperationsService = Depends(service)) -> dict:
    return checked(lambda: svc.movement(
        body.store_code, body.material_id, body.kind, body.quantity, body.note, body.expected_revision
    ))


@router.get("/supplies/{store_code}/movements")
def movements(store_code: str, limit: int = Query(100, ge=1, le=500),
              svc: OperationsService = Depends(service)) -> list[dict]:
    return checked(lambda: svc.movements(store_code, limit))


@router.get("/contacts/{store_code}/clients")
def clients(store_code: str, svc: OperationsService = Depends(service)) -> list[dict]:
    return checked(lambda: svc.clients(store_code))


@router.post("/contacts/{store_code}/clients", status_code=201)
def add_client(store_code: str, body: ClientInput,
               svc: OperationsService = Depends(service)) -> dict:
    return checked(lambda: svc.add_client(
        store_code, name=body.name, phone=body.phone, erp_code=body.erp_code,
        origin=body.origin, last_purchase_on=body.last_purchase_on
    ))


@router.get("/contacts/{store_code}/team")
def seller_team(store_code: str, svc: OperationsService = Depends(service)) -> list[dict]:
    return checked(lambda: svc.sellers(store_code))


@router.get("/contacts/{store_code}/{year}/{month}/calls")
def calls(store_code: str, year: int = Path(ge=2020, le=2100),
          month: int = Path(ge=1, le=12),
          svc: OperationsService = Depends(service)) -> dict:
    return checked(lambda: svc.calls(store_code, year, month))


@router.post("/contacts/{store_code}/calls", status_code=201)
def create_call(store_code: str, body: CallInput,
                svc: OperationsService = Depends(service)) -> dict:
    return checked(lambda: svc.add_call(
        store_code, client_id=body.client_id, seller_id=body.seller_id,
        contacted_on=body.date, outcome=body.outcome,
        next_on=body.next_on, note=body.note
    ))


@router.put("/contacts/{store_code}/calls/{call_id}")
def correct_call(store_code: str, call_id: UUID, body: CallCorrection,
                 svc: OperationsService = Depends(service)) -> dict:
    return checked(lambda: svc.update_call(
        store_code, call_id, contacted_on=body.date,
        outcome=body.outcome, next_on=body.next_on, note=body.note,
        expected=body.expected_revision
    ))
