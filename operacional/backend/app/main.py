"""Minimal API: sem dados reais ou rotas desprotegidas."""
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from app.admin_routes import router as admin_router
from app.operations_routes import router as operations_router
from app.routines_routes import router as routines_router
from app.local_routes import router as local_router
from app.attachments_routes import router as attachments_router
from app.overview_routes import router as overview_router
from app.closing_routes import router as closing_router
from app.targets_routes import router as targets_router
from app.auth import current_user
from app.config import get_settings
from app.db import get_db
from app.models import User
from app.policy import can_access, visible_stores
from app.repositories import load_principal

app = FastAPI(title="Portal UMA - API operacional", version="0.1.0")
app.include_router(admin_router)
app.include_router(targets_router)
app.include_router(overview_router)
app.include_router(closing_router)
app.include_router(operations_router)
app.include_router(routines_router)
app.include_router(local_router)
app.include_router(attachments_router)
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().allowed_origins(),
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
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
        "features": {
            "targets": any(can_access(principal, "targets.view", store) for store in visible_stores(principal)),
            "overview": any(can_access(principal, "overview.view", store) for store in visible_stores(principal)),
            "reviews": any(can_access(principal, "reviews.view", store) for store in visible_stores(principal)),
            "supplies": any(can_access(principal, "supplies.view", store) for store in visible_stores(principal)),
            "telemarketing": any(can_access(principal, "telemarketing.view", store) for store in visible_stores(principal)),
            "checklist": any(can_access(principal, "checklist.view", s) for s in visible_stores(principal)),
            "whatsapp_status": any(can_access(principal, "whatsapp_status.view", s) for s in visible_stores(principal)),
            "instagram": any(can_access(principal, "instagram.view", s) for s in visible_stores(principal)),
            "training": any(can_access(principal, "training.view", s) for s in visible_stores(principal)),
            "monthly_closing": (
                (principal.is_superadmin or principal.profile == "administrator")
                and can_access(principal, "monthly_closing.view")
            ),
        },
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
