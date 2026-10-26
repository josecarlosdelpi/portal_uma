"""Politica de autorizacao pura: nenhuma regra de acesso depende do frontend.

Perfis:
- superadministrador: controle total (continua exigindo identidade autenticada);
- administrator: leitura/escrita operacional nas tres lojas, sem governanca;
- seller: apenas leitura, na unica loja autorizada, filtrada por permissao.
"""
from dataclasses import dataclass, field
from typing import Mapping

STORE_CODES = frozenset({"JOINVILLE", "ITAJAI", "TUBARAO"})

# Permissoes de indicadores sao distintas das permissoes do modulo.
READ_PERMISSIONS = frozenset({
    "overview.view",
    "sales.view",
    "sales.revenue.view",
    "sales.target.view",
    "sales.attainment.view",
    "sales.previous_month.view",
    "sales.previous_year.view",
    "targets.view",
    "telemarketing.view",
    "reviews.view",
    "supplies.view",
    "checklist.view",
    "training.view",
    "whatsapp_status.view",
    "instagram.view",
})

# Esta permissao divulga dados consolidados das tres lojas e nao pode ser herdada por vendedores.
MANAGEMENT_READ_PERMISSIONS = frozenset({"monthly_closing.view"})

WRITE_PERMISSIONS = frozenset({
    "sales.import",
    "targets.edit",
    "monthly_closing.edit",
    "monthly_closing.archive",
    "telemarketing.edit",
    "reviews.edit",
    "supplies.edit",
    "checklist.edit",
    "training.edit",
    "whatsapp_status.edit",
    "instagram.edit",
})

GOVERNANCE_PERMISSIONS = frozenset({
    "users.manage",
    "permissions.manage",
    "audit.view",
    "security.manage",
})
OPERATIONAL_PERMISSIONS = READ_PERMISSIONS | MANAGEMENT_READ_PERMISSIONS | WRITE_PERMISSIONS
KNOWN_PERMISSIONS = OPERATIONAL_PERMISSIONS | GOVERNANCE_PERMISSIONS


@dataclass(frozen=True)
class Principal:
    user_id: str
    profile: str
    active: bool = True
    is_superadmin: bool = False
    store_codes: frozenset[str] = frozenset()
    group_grants: frozenset[str] = frozenset()
    overrides: Mapping[str, bool] = field(default_factory=dict)


def can_access(principal: Principal, permission: str, store_code: str | None = None) -> bool:
    """Negar por padrao; a permissao nunca ignora o limite de loja do vendedor."""
    if not principal.active or permission not in KNOWN_PERMISSIONS:
        return False
    if store_code is not None and store_code not in STORE_CODES:
        return False

    if principal.is_superadmin:
        return True

    if principal.profile == "administrator":
        return permission in OPERATIONAL_PERMISSIONS

    if principal.profile != "seller":
        return False

    # Vendedor somente leitura e vinculado a EXATAMENTE uma loja.
    if len(principal.store_codes) != 1 or store_code not in principal.store_codes:
        return False
    if permission not in READ_PERMISSIONS:
        return False

    # Ausencia de override = herdar. True concede, False retira.
    inherited = permission in principal.group_grants
    return principal.overrides.get(permission, inherited)


def visible_stores(principal: Principal) -> frozenset[str]:
    if not principal.active:
        return frozenset()
    if principal.is_superadmin or principal.profile == "administrator":
        return STORE_CODES
    if principal.profile == "seller" and len(principal.store_codes) == 1:
        return principal.store_codes & STORE_CODES
    return frozenset()
