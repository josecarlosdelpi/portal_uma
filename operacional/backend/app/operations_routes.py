"""Strictly typed HTTP routes for reviews, supply controls and telephone log."""
from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Path, Query, UploadFile
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


ORIGINS = r"^(google|inativo60|inativo90|carteira|planilha|indicacao|outro)$"


class ClientFields(BaseModel):
    name: str | None = Field(default=None, max_length=100)
    phone: str | None = Field(default=None, max_length=40)
    cellphone: str | None = Field(default=None, max_length=40)
    erp_code: str | None = Field(default=None, max_length=50)
    origin: str | None = Field(default=None, pattern=ORIGINS)
    city: str | None = Field(default=None, max_length=60)
    contact_person: str | None = Field(default=None, max_length=100)
    birthday_day: int | None = Field(default=None, ge=1, le=31)
    birthday_month: int | None = Field(default=None, ge=1, le=12)
    status: str | None = Field(default=None,
                               pattern=r"^(ativo|inativo|prospect)$")
    tag: str | None = Field(default=None, max_length=60)
    last_contact_on: date | None = None
    last_purchase_on: date | None = None
    notes: str | None = Field(default=None, max_length=2000)


class ClientInput(ClientFields):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=100)
    origin: str = Field(default="outro", pattern=ORIGINS)
    confirm: bool = False


class ClientUpdate(ClientFields):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=1)
    confirm: bool = False


class SettingsInput(Strict):
    inactivity_days: int = Field(ge=1, le=365)


class CallInput(Strict):
    client_id: UUID
    seller_id: UUID
    date: date
    channel: str = Field(default="ligacao", pattern=r"^(ligacao|whatsapp)$")
    outcome: str = Field(pattern=r"^(apresentacao|sem_resposta|whatsapp|outro)$")
    next_on: date | None = None
    note: str = Field(default="", max_length=240)


class CallCorrection(Strict):
    date: date
    channel: str = Field(default="ligacao", pattern=r"^(ligacao|whatsapp)$")
    outcome: str = Field(pattern=r"^(apresentacao|sem_resposta|whatsapp|outro)$")
    next_on: date | None = None
    note: str = Field(default="", max_length=240)
    expected_revision: int = Field(ge=1)


class FollowupComplete(Strict):
    expected_revision: int = Field(ge=1)


class FollowupReschedule(Strict):
    next_on: date
    expected_revision: int = Field(ge=1)


class ImportDecision(Strict):
    action: str = Field(pattern=r"^(import|update|skip)$")
    client_id: UUID | None = None
    city: str | None = Field(default=None, max_length=60)


class ImportCommit(Strict):
    decisions: dict[str, ImportDecision] = Field(default_factory=dict)
    confirm: bool = False


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
def clients(store_code: str, q: str | None = Query(default=None, max_length=80),
            city: str | None = Query(default=None, max_length=60),
            status: str | None = Query(default=None),
            tag: str | None = Query(default=None, max_length=60),
            phone: str | None = Query(default=None, max_length=40),
            inactive: str | None = Query(default=None, pattern=r"^(sim|nao)$"),
            page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200),
            svc: OperationsService = Depends(service)) -> dict:
    return checked(lambda: svc.clients_page(
        store_code, q=q, city=city, status=status, tag=tag, phone=phone,
        inactive=inactive, page=page, page_size=page_size))


@router.get("/contacts/{store_code}/clients/filters")
def client_filters(store_code: str,
                   svc: OperationsService = Depends(service)) -> dict:
    return checked(lambda: svc.client_filters(store_code))


@router.get("/contacts/{store_code}/clients/{client_id}")
def client_detail(store_code: str, client_id: UUID,
                  svc: OperationsService = Depends(service)) -> dict:
    return checked(lambda: svc.client_detail(store_code, client_id))


@router.post("/contacts/{store_code}/clients", status_code=201)
def add_client(store_code: str, body: ClientInput,
               svc: OperationsService = Depends(service)) -> dict:
    return checked(lambda: svc.add_client(
        store_code, name=body.name, phone=body.phone, cellphone=body.cellphone,
        erp_code=body.erp_code, origin=body.origin, city=body.city,
        contact_person=body.contact_person, birthday_day=body.birthday_day,
        birthday_month=body.birthday_month, status=body.status, tag=body.tag,
        last_contact_on=body.last_contact_on, notes=body.notes,
        last_purchase_on=body.last_purchase_on, confirm=body.confirm
    ))


@router.put("/contacts/{store_code}/clients/{client_id}")
def update_client(store_code: str, client_id: UUID, body: ClientUpdate,
                  svc: OperationsService = Depends(service)) -> dict:
    fields = body.model_dump(exclude_unset=True,
                             exclude={"expected_revision", "confirm"})
    return checked(lambda: svc.update_client(
        store_code, client_id, expected=body.expected_revision,
        confirm=body.confirm, **fields))


@router.get("/contacts/{store_code}/settings")
def get_settings(store_code: str,
                 svc: OperationsService = Depends(service)) -> dict:
    return checked(lambda: svc.contact_settings(store_code))


@router.put("/contacts/{store_code}/settings")
def put_settings(store_code: str, body: SettingsInput,
                 svc: OperationsService = Depends(service)) -> dict:
    return checked(lambda: svc.save_settings(store_code, body.inactivity_days))


@router.get("/contacts/{store_code}/metrics/{year}/{month}")
def contact_metrics(store_code: str, year: int = Path(ge=2020, le=2100),
                    month: int = Path(ge=1, le=12),
                    svc: OperationsService = Depends(service)) -> dict:
    return checked(lambda: svc.metrics(store_code, year, month))


@router.get("/contacts/{store_code}/followups")
def followups(store_code: str,
              state: str = Query("abertos",
                                 pattern=r"^(abertos|atrasados|realizados|todos)$"),
              page: int = Query(1, ge=1), page_size: int = Query(100, ge=1, le=200),
              svc: OperationsService = Depends(service)) -> dict:
    return checked(lambda: svc.followups(store_code, state=state, page=page,
                                         page_size=page_size))


@router.post("/contacts/{store_code}/followups/{call_id}/done")
def followup_done(store_code: str, call_id: UUID, body: FollowupComplete,
                  svc: OperationsService = Depends(service)) -> dict:
    return checked(lambda: svc.complete_followup(
        store_code, call_id, body.expected_revision))


@router.post("/contacts/{store_code}/followups/{call_id}/reschedule")
def followup_reschedule(store_code: str, call_id: UUID, body: FollowupReschedule,
                        svc: OperationsService = Depends(service)) -> dict:
    return checked(lambda: svc.reschedule_followup(
        store_code, call_id, next_on=body.next_on,
        expected=body.expected_revision))


@router.post("/contacts/{store_code}/import/preview", status_code=201)
def import_preview(store_code: str, file: UploadFile = File(...),
                   default_city: str | None = Query(default=None, max_length=60),
                   svc: OperationsService = Depends(service)) -> dict:
    data = file.file.read()
    if len(data) > 10 * 1024 * 1024:
        raise HTTPException(status_code=422, detail="Arquivo maior que 10 MB")
    return checked(lambda: svc.import_preview(
        store_code, filename=file.filename or "carteira",
        data=data, default_city=default_city))


@router.post("/contacts/{store_code}/import/{session_id}/commit")
def import_commit(store_code: str, session_id: UUID, body: ImportCommit,
                  svc: OperationsService = Depends(service)) -> dict:
    return checked(lambda: svc.import_commit(
        store_code, session_id,
        decisions={key: value.model_dump() for key, value in body.decisions.items()},
        confirm=body.confirm))


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
        contacted_on=body.date, outcome=body.outcome, channel=body.channel,
        next_on=body.next_on, note=body.note
    ))


@router.put("/contacts/{store_code}/calls/{call_id}")
def correct_call(store_code: str, call_id: UUID, body: CallCorrection,
                 svc: OperationsService = Depends(service)) -> dict:
    return checked(lambda: svc.update_call(
        store_code, call_id, contacted_on=body.date,
        outcome=body.outcome, channel=body.channel,
        next_on=body.next_on, note=body.note,
        expected=body.expected_revision
    ))
