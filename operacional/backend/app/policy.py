"""Politica de autorizacao pura: nenhuma regra de acesso depende do frontend.

Modelo de acesso:
- superadministrador: controle total (continua exigindo identidade autenticada);
- demais usuarios: acesso vem exclusivamente do grupo de acesso (permissoes +
  abrangencia de lojas), refinado pelas lojas autorizadas do proprio usuario
  e pelas excecoes individuais (herdar/permitir/bloquear).

O campo users.profile indica apenas a FUNCAO do colaborador (vendedor,
administrador ou equipe interna) e nao concede nenhuma permissao.
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
    "daily_tasks.view",
    "training.view",
    "whatsapp_status.view",
    "instagram.view",
})

# Fechamento mensal consolida as tres lojas: ver FULL_SCOPE_PERMISSIONS.
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
    "daily_tasks.edit",
    "training.edit",
    "whatsapp_status.edit",
    "instagram.edit",
})

# Governanca nunca e delegavel: somente o SuperAdmin administra contas,
# grupos, seguranca e auditoria.
GOVERNANCE_PERMISSIONS = frozenset({
    "users.manage",
    "permissions.manage",
    "audit.view",
    "security.manage",
})
OPERATIONAL_PERMISSIONS = READ_PERMISSIONS | MANAGEMENT_READ_PERMISSIONS | WRITE_PERMISSIONS
# Financeiro nunca e herdado por funcao: somente SuperAdmin ou concessao
# explicita via grupo/excecao. 'finance.import' permanece exclusivo do
# SuperAdmin e nao pode ser concedido a grupos.
FINANCIAL_READ_PERMISSIONS = frozenset({"finance.view"})
FINANCIAL_PERMISSIONS = FINANCIAL_READ_PERMISSIONS | frozenset({"finance.import"})

KNOWN_PERMISSIONS = OPERATIONAL_PERMISSIONS | GOVERNANCE_PERMISSIONS | FINANCIAL_PERMISSIONS

# Permissoes que expoem ou alteram dados consolidados das tres lojas.
# Alem da concessao explicita, exigem abrangencia completa: grupo + usuario
# precisam estar autorizados em TODAS as lojas. Uma excecao individual
# nunca contorna esse limite geografico.
FULL_SCOPE_PERMISSIONS = frozenset({
    "monthly_closing.view",
    "monthly_closing.edit",
    "monthly_closing.archive",
    "sales.import",
})

# Concediveis a grupos/usuarios; governanca e importacao financeira ficam
# restritas ao SuperAdmin independentemente de concessoes.
GRANTABLE_PERMISSIONS = (
    OPERATIONAL_PERMISSIONS | FINANCIAL_READ_PERMISSIONS
)

USER_PROFILES = frozenset({"administrator", "seller", "staff"})


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
    """Negar por padrao; permissao nunca ignora o limite de lojas autorizadas."""
    if not principal.active or permission not in KNOWN_PERMISSIONS:
        return False
    if store_code is not None and store_code not in STORE_CODES:
        return False

    if principal.is_superadmin:
        return True

    if permission in GOVERNANCE_PERMISSIONS or permission == "finance.import":
        return False

    if permission in FULL_SCOPE_PERMISSIONS:
        # Dados/escrita consolidados: exige cobertura das tres lojas.
        if not STORE_CODES <= principal.store_codes:
            return False
    elif store_code is None or store_code not in principal.store_codes:
        return False

    # Ausencia de override = herdar o grupo. True concede, False retira.
    inherited = permission in principal.group_grants
    return principal.overrides.get(permission, inherited)


def visible_stores(principal: Principal) -> frozenset[str]:
    if not principal.active:
        return frozenset()
    if principal.is_superadmin:
        return STORE_CODES
    return principal.store_codes & STORE_CODES
