"""7-slide meeting data, typed narrative and archive endpoints."""
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Path
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.auth import current_user
from app.closing_schema import ClosingContent
from app.closing_service import ClosingError, ClosingService
from app.db import get_db
from app.models import User

router = APIRouter(prefix="/api/v1/monthly-closing", tags=["monthly-closing"])


class SaveClosing(BaseModel):
    model_config = ConfigDict(extra="forbid")
    draft: ClosingContent
    expected_revision: int = Field(ge=0)


class ArchiveClosing(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=1)


def service(user: User = Depends(current_user), db: Session = Depends(get_db)) -> ClosingService:
    return ClosingService(db, user)


def guarded(callback):
    try:
        return callback()
    except ClosingError as error:
        raise HTTPException(status_code=error.status_code, detail=error.message) from error


@router.get("/{year}/{month}")
def get_closing(
    year: int = Path(ge=2020, le=2100),
    month: int = Path(ge=1, le=12),
    svc: ClosingService = Depends(service),
) -> dict:
    return guarded(lambda: svc.get(year, month))


@router.put("/{year}/{month}")
def save_closing(
    payload: SaveClosing,
    year: int = Path(ge=2020, le=2100),
    month: int = Path(ge=1, le=12),
    svc: ClosingService = Depends(service),
) -> dict:
    return guarded(lambda: svc.save(year, month, payload.draft, payload.expected_revision))


@router.post("/{year}/{month}/archives", status_code=201)
def archive_closing(
    payload: ArchiveClosing,
    year: int = Path(ge=2020, le=2100),
    month: int = Path(ge=1, le=12),
    svc: ClosingService = Depends(service),
) -> dict:
    return guarded(lambda: svc.archive(year, month, payload.expected_revision))


@router.get("/{year}/{month}/archives")
def list_closing_archives(
    year: int = Path(ge=2020, le=2100),
    month: int = Path(ge=1, le=12),
    svc: ClosingService = Depends(service),
) -> list[dict]:
    return guarded(lambda: svc.archive_list(year, month))


@router.get("/{year}/{month}/archives/{archive_id}")
def get_closing_archive(
    archive_id: UUID,
    year: int = Path(ge=2020, le=2100),
    month: int = Path(ge=1, le=12),
    svc: ClosingService = Depends(service),
) -> dict:
    return guarded(lambda: svc.archived(year, month, archive_id))
