"""Endpoints de metas com autorizacao no backend e versionamento otimista."""
from datetime import date
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, Path
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.auth import current_user
from app.db import get_db
from app.models import User
from app.targets_service import TargetError, TargetService

router = APIRouter(prefix="/api/v1/targets", tags=["targets"])


class GoalInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    amount: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    expected_revision: int = Field(ge=0)


class MinimumInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    amount: Decimal = Field(ge=0, max_digits=14, decimal_places=2)
    expected_revision: int = Field(ge=0)


class CalendarInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    days_off: list[date] = Field(default_factory=list, max_length=31)
    expected_revision: int = Field(ge=0)


def service(user: User = Depends(current_user), db: Session = Depends(get_db)) -> TargetService:
    return TargetService(db, user)


def guarded(callback):
    try:
        return callback()
    except TargetError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.get("/{store_code}/{year}/{month}")
def get_month(
    store_code: str,
    year: int = Path(ge=2020, le=2100),
    month: int = Path(ge=1, le=12),
    svc: TargetService = Depends(service),
) -> dict:
    return guarded(lambda: svc.get(store_code, year, month))


@router.put("/{store_code}/{year}/{month}/goal")
def save_goal(
    store_code: str, payload: GoalInput,
    year: int = Path(ge=2020, le=2100),
    month: int = Path(ge=1, le=12),
    svc: TargetService = Depends(service),
) -> dict:
    return guarded(lambda: svc.save_goal(
        store_code, year, month, amount=payload.amount, expected_revision=payload.expected_revision
    ))


@router.put("/{store_code}/{year}/{month}/calendar")
def save_calendar(
    store_code: str, payload: CalendarInput,
    year: int = Path(ge=2020, le=2100),
    month: int = Path(ge=1, le=12),
    svc: TargetService = Depends(service),
) -> dict:
    return guarded(lambda: svc.save_closed_days(
        store_code, year, month, dates=payload.days_off,
        expected_revision=payload.expected_revision
    ))


@router.put("/{store_code}/minimum")
def save_minimum(
    store_code: str, payload: MinimumInput,
    svc: TargetService = Depends(service),
) -> dict:
    return guarded(lambda: svc.save_minimum(
        store_code, amount=payload.amount, expected_revision=payload.expected_revision
    ))
