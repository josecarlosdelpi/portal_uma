"""Resumo gerencial restrito a identidade e lojas aprovadas pelo servidor."""
from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy.orm import Session
from app.auth import current_user
from app.db import get_db
from app.models import User
from app.overview_service import OverviewError, overview_for_user

router = APIRouter(prefix="/api/v1/overview", tags=["overview"])


@router.get("/{year}/{month}")
def get_overview(
    year: int = Path(ge=2020, le=2100),
    month: int = Path(ge=1, le=12),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    try:
        return overview_for_user(db, user, year, month)
    except OverviewError as error:
        raise HTTPException(status_code=error.status_code, detail=error.message) from error
