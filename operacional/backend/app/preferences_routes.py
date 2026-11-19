"""Preferencias de navegacao do proprio usuario autenticado."""
import re
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import current_user
from app.db import get_db
from app.models import User, UserPreference
from app.policy import STORE_CODES, can_access, visible_stores
from app.repositories import load_principal

router = APIRouter(prefix="/api/v1/me", tags=["preferences"])

# Identificadores estaveis dos modulos do menu lateral.
MODULE_PERMISSION = {
    "overview": "overview.view",
    "contacts": "telemarketing.view",
    "reviews": "reviews.view",
    "supplies": "supplies.view",
    "checklist": "checklist.view",
    "daily": "daily_tasks.view",
    "targets": "targets.view",
    "sales": "sales.view",
    "whatsapp": None,  # regra especial: whatsapp_status OU instagram
    "training": "training.view",
    "closing": "monthly_closing.view",
    "access": None,  # somente SuperAdmin
}


STORE_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


class PreferencesBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sidebar_pinned: bool = True
    favorites: list[str] = Field(default_factory=list, max_length=15)
    # None = nao alterar; dict vazio = limpar cores personalizadas.
    store_colors: dict[str, str] | None = None


def _allowed_modules(db: Session, user: User) -> set[str]:
    principal = load_principal(db, user)
    stores = visible_stores(principal)
    allowed = {
        key for key, permission in MODULE_PERMISSION.items()
        if permission and any(can_access(principal, permission, store) for store in stores)
    }
    if any(can_access(principal, "whatsapp_status.view", store)
           or can_access(principal, "instagram.view", store) for store in stores):
        allowed.add("whatsapp")
    if principal.is_superadmin:
        allowed.add("access")
    if can_access(principal, "monthly_closing.view") and (
        principal.is_superadmin or principal.profile == "administrator"
    ):
        allowed.add("closing")
    return allowed


def _get_row(db: Session, user: User) -> UserPreference:
    row = db.get(UserPreference, user.id)
    if row is None:
        row = UserPreference(user_id=user.id, sidebar_pinned=True, favorites=[])
        db.add(row)
        db.flush()
    return row


@router.get("/preferences")
def get_preferences(user: User = Depends(current_user),
                    db: Session = Depends(get_db)) -> dict:
    row = db.get(UserPreference, user.id)
    allowed = _allowed_modules(db, user)
    stored = row.favorites if row else []
    favorites = [key for key in stored if key in allowed]
    prefs = row.ui_prefs if row else {}
    return {"sidebar_pinned": row.sidebar_pinned if row else True,
            "favorites": favorites,
            "store_colors": dict((prefs or {}).get("store_colors") or {})}


@router.put("/preferences")
def save_preferences(body: PreferencesBody, user: User = Depends(current_user),
                     db: Session = Depends(get_db)) -> dict:
    unknown = [key for key in body.favorites if key not in MODULE_PERMISSION]
    if unknown:
        raise HTTPException(422, f"Módulo desconhecido: {unknown[0]}")
    allowed = _allowed_modules(db, user)
    row = _get_row(db, user)
    # deduplicado, na ordem enviada, somente modulos autorizados
    favorites = [key for key in dict.fromkeys(body.favorites) if key in allowed]
    # Favoritos sem permissao no momento: preservados na posicao original,
    # para reaparecerem no lugar certo se o acesso voltar.
    for index, key in enumerate(row.favorites):
        if key in MODULE_PERMISSION and key not in allowed and key not in favorites:
            favorites.insert(min(index, len(favorites)), key)
    row.sidebar_pinned = body.sidebar_pinned
    row.favorites = favorites
    if body.store_colors is not None:
        for code, color in body.store_colors.items():
            if code not in STORE_CODES:
                raise HTTPException(422, f"Loja desconhecida para cor: {code}")
            if not STORE_COLOR_RE.match(color):
                raise HTTPException(422, "Cor invalida: use o formato #RRGGBB.")
        prefs = dict(row.ui_prefs or {})
        prefs["store_colors"] = dict(body.store_colors)
        row.ui_prefs = prefs
    db.commit()
    # resposta alinhada ao GET: somente modulos autorizados agora;
    # os ocultos ficam preservados apenas no banco.
    return {"sidebar_pinned": row.sidebar_pinned,
            "favorites": [k for k in favorites if k in allowed],
            "store_colors": dict((row.ui_prefs or {}).get("store_colors") or {})}
