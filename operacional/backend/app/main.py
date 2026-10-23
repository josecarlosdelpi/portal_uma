"""Minimal API: sem dados reais ou rotas desprotegidas."""
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from app.auth import current_user
from app.config import get_settings
from app.db import get_db
from app.models import User
from app.policy import can_access, visible_stores
from app.repositories import load_principal

app = FastAPI(title="Portal UMA - API operacional", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().allowed_origins(),
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.get("/health", tags=["system"])
def health() -> dict[str, str]:
    """Liveness only; nao revela contas, banco ou dados comerciais."""
    return {"status": "ok"}


@app.get("/api/v1/me", tags=["identity"])
def me(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    principal = load_principal(db, user)
    return {
        "id": str(user.id),
        "display_name": user.display_name,
        "profile": "superadmin" if principal.is_superadmin else principal.profile,
        "stores": sorted(visible_stores(principal)),
    }


@app.get("/api/v1/stores", tags=["stores"])
def stores(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    principal = load_principal(db, user)
    codes = sorted(visible_stores(principal))
    if not codes:
        raise HTTPException(status_code=403, detail="Access denied")
    return {"stores": codes}


@app.get("/api/v1/access/{store_code}/{permission:path}", tags=["access"])
def access_check(
    store_code: str,
    permission: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Diagnostic authorization decision; does not expose business data."""
    principal = load_principal(db, user)
    if not can_access(principal, permission, store_code):
        raise HTTPException(status_code=403, detail="Access denied")
    return {"allowed": True, "store": store_code, "permission": permission}
