"""Business use cases for permissions and user administration.

Every mutation is restricted to the only system superadmin, is atomic with
its audit event, and never grants non-delegable permissions (governance,
ERP financial import) to groups or users.
"""
from uuid import UUID
import re

from sqlalchemy.exc import IntegrityError

from app.admin_repository import AdminRepository
from app.models import AccessInvitation, AccessGroup, User
from app.policy import (
    FULL_SCOPE_PERMISSIONS, GRANTABLE_PERMISSIONS, STORE_CODES, USER_PROFILES,
    Principal, can_access,
)
from app.repositories import load_principal


class AdminError(Exception):
    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.message = message


def require_superadmin(user: User) -> None:
    if not user.active or not user.is_superadmin:
        raise AdminError(403, "Access denied")


# Catalogo de permissoes delegaveis, organizado por modulo, com metadados
# usados pela administracao. A autoridade continua sendo app.policy.
PERMISSION_CATALOG: list[dict] = [
    {"module": "overview", "permissions": [
        {"code": "overview.view", "kind": "view"},
    ]},
    {"module": "sales", "permissions": [
        {"code": "sales.view", "kind": "view"},
        {"code": "sales.revenue.view", "kind": "view"},
        {"code": "sales.target.view", "kind": "view"},
        {"code": "sales.attainment.view", "kind": "view"},
        {"code": "sales.previous_month.view", "kind": "view"},
        {"code": "sales.previous_year.view", "kind": "view"},
        {"code": "sales.import", "kind": "action", "requires_all_stores": True},
    ]},
    {"module": "targets", "permissions": [
        {"code": "targets.view", "kind": "view"},
        {"code": "targets.edit", "kind": "edit"},
    ]},
    {"module": "telemarketing", "permissions": [
        {"code": "telemarketing.view", "kind": "view"},
        {"code": "telemarketing.edit", "kind": "edit"},
    ]},
    {"module": "monthly_closing", "permissions": [
        {"code": "monthly_closing.view", "kind": "view", "requires_all_stores": True},
        {"code": "monthly_closing.edit", "kind": "edit", "requires_all_stores": True},
        {"code": "monthly_closing.archive", "kind": "action", "requires_all_stores": True},
    ]},
    {"module": "daily_tasks", "permissions": [
        {"code": "daily_tasks.view", "kind": "view"},
        {"code": "daily_tasks.edit", "kind": "edit"},
    ]},
    {"module": "checklist", "permissions": [
        {"code": "checklist.view", "kind": "view"},
        {"code": "checklist.edit", "kind": "edit"},
    ]},
    {"module": "supplies", "permissions": [
        {"code": "supplies.view", "kind": "view"},
        {"code": "supplies.edit", "kind": "edit"},
    ]},
    {"module": "reviews", "permissions": [
        {"code": "reviews.view", "kind": "view"},
        {"code": "reviews.edit", "kind": "edit"},
    ]},
    {"module": "whatsapp_status", "permissions": [
        {"code": "whatsapp_status.view", "kind": "view"},
        {"code": "whatsapp_status.edit", "kind": "edit"},
    ]},
    {"module": "instagram", "permissions": [
        {"code": "instagram.view", "kind": "view"},
        {"code": "instagram.edit", "kind": "edit"},
    ]},
    {"module": "training", "permissions": [
        {"code": "training.view", "kind": "view"},
        {"code": "training.edit", "kind": "edit"},
    ]},
    {"module": "finance", "permissions": [
        {"code": "finance.view", "kind": "view"},
    ]},
]

# Permissoes que um vendedor podia ter sob o modelo legado (um grupo por
# loja): apenas consulta, nunca financeiro. Usado para aceitar a resolucao
# implicita por store_code somente quando a associacao e comprovadamente
# segura — no pior caso, um cadastro legado recebe leitura na propria loja.
_LEGACY_SAFE_GRANTS = {
    entry["code"]
    for module in PERMISSION_CATALOG
    if module["module"] != "finance"
    for entry in module["permissions"]
    if entry["kind"] == "view"
}


class AdminService:
    def __init__(self, repo: AdminRepository, actor: User):
        require_superadmin(actor)
        self.repo = repo
        self.actor = actor

    def _save(self) -> None:
        try:
            self.repo.commit()
        except IntegrityError as exc:
            self.repo.rollback()
            raise AdminError(409, "Conflicting record") from exc

    # ---------- consultas ----------

    def list_users(self) -> list[dict]:
        result = []
        for user in self.repo.users():
            cred = self.repo.local_credential(user.id)
            group = self.repo.group_of(user.id)
            result.append({
                "id": str(user.id),
                "display_name": user.display_name,
                "profile": "superadmin" if user.is_superadmin else user.profile,
                "active": user.active,
                "username": cred.username_key if cred is not None else None,
                "must_change_password": cred.must_change_password if cred is not None else False,
                "group": ({"id": str(group.id), "name": group.name}
                          if group is not None and group.active else None),
                "stores": self.repo.user_stores(user.id),
                "store_scope": self.repo.user_scope(user.id),
                "overrides": self.repo.overrides(user.id),
            })
        return result

    def list_groups(self) -> list[dict]:
        return [
            {
                "id": str(group.id),
                "name": group.name,
                "description": group.description,
                "active": group.active,
                "stores": self.repo.group_stores(group.id),
                "permissions": self.repo.grants(group.id),
                "member_count": self.repo.member_count(group.id),
            }
            for group in self.repo.groups()
        ]

    def group_detail(self, group_id: UUID) -> dict:
        group = self.repo.group(group_id)
        if group is None:
            raise AdminError(404, "Grupo nao encontrado")
        return {
            "id": str(group.id), "name": group.name,
            "description": group.description, "active": group.active,
            "stores": self.repo.group_stores(group.id),
            "permissions": self.repo.grants(group.id),
            "members": [
                {"id": str(member.id), "display_name": member.display_name,
                 "active": member.active}
                for member in self.repo.members(group.id)
            ],
        }

    def permission_catalog(self) -> dict:
        return {
            "modules": PERMISSION_CATALOG,
            "stores": sorted(STORE_CODES),
            "profiles": sorted(USER_PROFILES),
            "non_delegable": [
                "users.manage", "permissions.manage", "audit.view",
                "security.manage", "finance.import",
            ],
        }

    def effective_permissions(self, user_id: UUID) -> dict:
        user = self.repo.user(user_id)
        if user is None or getattr(user, "deleted_at", None) is not None:
            raise AdminError(404, "Usuario nao encontrado")
        principal = load_principal(self.repo.db, user)
        group = self.repo.group_of(user_id)
        stores = sorted(principal.store_codes & STORE_CODES)
        items = []
        for module in PERMISSION_CATALOG:
            for entry in module["permissions"]:
                code = entry["code"]
                allowed_stores = [
                    code_store for code_store in sorted(STORE_CODES)
                    if can_access(principal, code, code_store)
                ]
                items.append({
                    "module": module["module"],
                    "code": code,
                    "kind": entry["kind"],
                    "requires_all_stores": bool(entry.get("requires_all_stores")),
                    "group_default": code in principal.group_grants,
                    "override": principal.overrides.get(code),
                    "stores": allowed_stores,
                    "effective": bool(allowed_stores),
                })
        return {
            "user_id": str(user_id),
            "display_name": user.display_name,
            "is_superadmin": user.is_superadmin,
            "profile": "superadmin" if user.is_superadmin else user.profile,
            "group": ({"id": str(group.id), "name": group.name}
                      if group is not None and group.active else None),
            "stores": stores if not user.is_superadmin else sorted(STORE_CODES),
            "items": items,
        }

    # ---------- previa de acesso efetivo ----------

    @staticmethod
    def _permission_map(principal) -> dict[str, list[str]]:
        """Permissoes efetivas: codigo -> lojas onde vale."""
        result = {}
        for module in PERMISSION_CATALOG:
            for entry in module["permissions"]:
                code = entry["code"]
                stores = [
                    store for store in sorted(STORE_CODES)
                    if can_access(principal, code, store)
                ]
                if stores:
                    result[code] = stores
        return result

    @staticmethod
    def _access_diff(before: dict[str, list[str]],
                     after: dict[str, list[str]]) -> tuple[list[dict], list[dict]]:
        """Diferenca por permissao E loja: sales.view que passa de uma loja
        para as tres aparece como concessao nas lojas acrescentadas."""
        granted, revoked = [], []
        for code in sorted(set(before) | set(after)):
            gained = sorted(set(after.get(code, ())) - set(before.get(code, ())))
            lost = sorted(set(before.get(code, ())) - set(after.get(code, ())))
            if gained:
                granted.append({"code": code, "stores": gained})
            if lost:
                revoked.append({"code": code, "stores": lost})
        return granted, revoked

    def _simulated(self, user, *, stores: set[str], grants: set[str],
                   scope_rows: set[str]) -> tuple[Principal, list[str]]:
        """Principal hipotetico: abrangencia + concessoes + escopo individual."""
        effective = stores & scope_rows if scope_rows else stores
        principal = Principal(
            user_id=str(user.id), profile=user.profile,
            active=user.active, is_superadmin=user.is_superadmin,
            store_codes=frozenset(effective & STORE_CODES),
            group_grants=frozenset(grants),
            overrides=self.repo.overrides(user.id),
        )
        return principal, sorted(effective & STORE_CODES)

    def _simulated_group(self, user, group: AccessGroup,
                         scope_rows: set[str]) -> tuple[Principal, list[str]]:
        return self._simulated(
            user,
            stores=set(self.repo.group_stores(group.id)),
            grants=set(self.repo.grants(group.id)),
            scope_rows=scope_rows,
        )

    def preview_user_access(self, user_id: UUID, *, group_id: UUID,
                            store_codes: list[str] | None = None) -> dict:
        """Simula acesso efetivo antes de transferir o usuario de grupo."""
        user = self.repo.user(user_id)
        if user is None or getattr(user, "deleted_at", None) is not None:
            raise AdminError(404, "User not found")
        if user.is_superadmin:
            raise AdminError(403, "A conta SuperAdmin nao pode ser alterada aqui")
        group = self._valid_group(group_id)
        scope = (self._valid_scope(group, store_codes)
                 if store_codes is not None
                 else set(self.repo.user_scope(user_id)))
        before = self._permission_map(load_principal(self.repo.db, user))
        simulated, stores = self._simulated_group(user, group, scope)
        after = self._permission_map(simulated)
        granted, revoked = self._access_diff(before, after)
        return {
            "user_id": str(user_id),
            "group": {"id": str(group.id), "name": group.name},
            "stores": stores, "store_scope": sorted(scope),
            "before": before, "after": after,
            "granted": granted, "revoked": revoked,
        }

    def preview_reassignment(self, group_id: UUID, reassign_to: UUID) -> dict:
        """Impacto de mover os membros do grupo para outro grupo."""
        group = self.repo.group(group_id)
        if group is None:
            raise AdminError(404, "Grupo nao encontrado")
        target = self.repo.group(reassign_to)
        if target is None or not target.active or target.id == group_id:
            raise AdminError(422, "Grupo de reatribuicao invalido ou inativo")
        members = []
        for member in self.repo.members(group_id):
            # O escopo individual e preservado na transferencia: como ele so
            # restringe, o acesso efetivo nunca e ampliado pela mudanca.
            scope = set(self.repo.user_scope(member.id))
            before = self._permission_map(load_principal(self.repo.db, member))
            simulated, stores = self._simulated_group(member, target, scope)
            after = self._permission_map(simulated)
            granted, revoked = self._access_diff(before, after)
            members.append({
                "user_id": str(member.id),
                "display_name": member.display_name,
                "stores_before": self.repo.user_stores(member.id),
                "stores_after": stores,
                "granted": granted, "revoked": revoked,
            })
        return {
            "group": {"id": str(group.id), "name": group.name},
            "target": {"id": str(target.id), "name": target.name},
            "member_count": len(members), "members": members,
        }

    def preview_group_update(self, group_id: UUID, *, name: str,
                             description: str, store_codes: list[str],
                             permissions: list[str]) -> dict:
        """Impacto de mudar abrangencia/permissoes de um grupo COM membros:
        concessoes e revogacoes por usuario e loja, antes de salvar."""
        group = self.repo.group(group_id)
        if group is None:
            raise AdminError(404, "Grupo nao encontrado")
        _, _, stores, grants = self._validate_group_payload(
            name, description, store_codes, permissions)
        members = []
        widens = False
        for member in self.repo.members(group_id):
            scope = set(self.repo.user_scope(member.id))
            before = self._permission_map(load_principal(self.repo.db, member))
            simulated, stores_after = self._simulated(
                member, stores=stores, grants=grants, scope_rows=scope)
            after = self._permission_map(simulated)
            granted, revoked = self._access_diff(before, after)
            if granted:
                widens = True
            members.append({
                "user_id": str(member.id),
                "display_name": member.display_name,
                "stores_before": self.repo.user_stores(member.id),
                "stores_after": stores_after,
                "granted": granted, "revoked": revoked,
            })
        return {
            "group": {"id": str(group.id), "name": group.name},
            "proposed": {"stores": sorted(stores),
                         "permissions": sorted(grants)},
            "member_count": len(members),
            "widens": widens,
            "members": members,
        }

    # ---------- grupos de acesso ----------

    @staticmethod
    def _validate_group_payload(name: str, description: str,
                                store_codes: list[str], permissions: list[str]) -> tuple[str, str, set[str], set[str]]:
        name = " ".join((name or "").strip().split())
        description = (description or "").strip()
        if not 2 <= len(name) <= 120:
            raise AdminError(422, "Informe um nome de grupo entre 2 e 120 caracteres")
        if len(description) > 300:
            raise AdminError(422, "Descricao limitada a 300 caracteres")
        stores = set(store_codes or [])
        if not stores or not stores <= STORE_CODES:
            raise AdminError(422, "Selecione ao menos uma loja valida para a abrangencia")
        grants = set(permissions or [])
        unknown = grants - GRANTABLE_PERMISSIONS
        if unknown:
            raise AdminError(422, "Permissao nao delegavel ou desconhecida: " + sorted(unknown)[0])
        if grants & FULL_SCOPE_PERMISSIONS and stores != STORE_CODES:
            raise AdminError(
                422,
                "Permissoes consolidadas (fechamento ou importacao de vendas) "
                "exigem abrangencia das tres lojas",
            )
        return name, description, stores, grants

    def _group_public(self, group: AccessGroup) -> dict:
        return {
            "id": str(group.id), "name": group.name,
            "description": group.description, "active": group.active,
            "stores": self.repo.group_stores(group.id),
            "permissions": self.repo.grants(group.id),
            "member_count": self.repo.member_count(group.id),
        }

    def create_group(self, *, name: str, description: str,
                     store_codes: list[str], permissions: list[str]) -> dict:
        name, description, stores, grants = self._validate_group_payload(
            name, description, store_codes, permissions)
        if self.repo.group_by_name(name.casefold()) is not None:
            raise AdminError(409, "Ja existe um grupo com este nome")
        group = self.repo.create_group(name=name, description=description)
        self.repo.replace_group_stores(group.id, stores)
        self.repo.replace_grants(group.id, grants)
        self.repo.audit(self.actor, "group.created", "access_group", str(group.id),
                        {"name": name, "stores": sorted(stores),
                         "permissions": sorted(grants)})
        self._save()
        return self._group_public(group)

    def update_group(self, group_id: UUID, *, name: str, description: str,
                     store_codes: list[str], permissions: list[str]) -> dict:
        group = self.repo.group(group_id)
        if group is None:
            raise AdminError(404, "Grupo nao encontrado")
        name, description, stores, grants = self._validate_group_payload(
            name, description, store_codes, permissions)
        existing = self.repo.group_by_name(name.casefold())
        if existing is not None and existing.id != group.id:
            raise AdminError(409, "Ja existe um grupo com este nome")
        previous = {
            "name": group.name, "description": group.description,
            "stores": self.repo.group_stores(group.id),
            "permissions": self.repo.grants(group.id),
        }
        group.name = name
        group.description = description
        self.repo.replace_group_stores(group.id, stores)
        self.repo.replace_grants(group.id, grants)
        affected = self.repo.member_count(group.id)
        self.repo.audit(self.actor, "group.updated", "access_group", str(group.id),
                        {"previous": previous,
                         "current": {"name": name, "description": description,
                                     "stores": sorted(stores),
                                     "permissions": sorted(grants)},
                         "members_affected": affected})
        self._save()
        result = self._group_public(group)
        result["members_affected"] = affected
        return result

    def duplicate_group(self, group_id: UUID, *, name: str) -> dict:
        source = self.repo.group(group_id)
        if source is None:
            raise AdminError(404, "Grupo nao encontrado")
        name = " ".join((name or "").strip().split())
        if not 2 <= len(name) <= 120:
            raise AdminError(422, "Informe um nome de grupo entre 2 e 120 caracteres")
        if self.repo.group_by_name(name.casefold()) is not None:
            raise AdminError(409, "Ja existe um grupo com este nome")
        stores = set(self.repo.group_stores(group_id))
        grants = set(self.repo.grants(group_id))
        group = self.repo.create_group(
            name=name,
            description=source.description if source.description else "Copia de " + source.name,
        )
        self.repo.replace_group_stores(group.id, stores)
        self.repo.replace_grants(group.id, grants)
        self.repo.audit(self.actor, "group.duplicated", "access_group", str(group.id),
                        {"source_group_id": str(group_id), "source_name": source.name,
                         "name": name, "stores": sorted(stores),
                         "permissions": sorted(grants)})
        self._save()
        return self._group_public(group)

    def set_group_active(self, group_id: UUID, active: bool) -> dict:
        group = self.repo.group(group_id)
        if group is None:
            raise AdminError(404, "Grupo nao encontrado")
        members = self.repo.member_count(group_id)
        if not active and members > 0:
            raise AdminError(
                409,
                "Este grupo tem usuarios vinculados. Reatribua-os antes de desativar.",
            )
        previous = group.active
        group.active = active
        self.repo.audit(self.actor, "group.status.changed", "access_group",
                        str(group.id), {"previous": previous, "current": active})
        self._save()
        return self._group_public(group)

    def delete_group(self, group_id: UUID, reassign_to: UUID | None) -> dict:
        group = self.repo.group(group_id)
        if group is None:
            raise AdminError(404, "Grupo nao encontrado")
        members = self.repo.members(group_id)
        target = None
        if members:
            if reassign_to is None or reassign_to == group_id:
                raise AdminError(
                    422,
                    "Grupo em uso: informe o grupo que recebera os usuarios.",
                )
            target = self.repo.group(reassign_to)
            if target is None or not target.active:
                raise AdminError(422, "Grupo de reatribuicao invalido ou inativo")
        previous = self._group_public(group)
        moved = 0
        if members:
            moved = self.repo.move_members(group_id, target.id)
        self.repo.delete_group(group)
        self.repo.audit(self.actor, "group.deleted", "access_group", str(group_id),
                        {"previous": {"name": previous["name"],
                                      "stores": previous["stores"],
                                      "permissions": previous["permissions"]},
                         "members_moved": moved,
                         "reassigned_to": str(target.id) if target else None})
        self._save()
        return {"deleted": True, "members_moved": moved}

    def replace_group_permissions(self, group_id: UUID, permissions: list[str]) -> dict:
        group = self.repo.group(group_id)
        if group is None or not group.active:
            raise AdminError(404, "Grupo nao encontrado")
        grants = set(permissions or [])
        unknown = grants - GRANTABLE_PERMISSIONS
        if unknown:
            raise AdminError(422, "Permissao nao delegavel ou desconhecida: " + sorted(unknown)[0])
        stores = set(self.repo.group_stores(group_id))
        if grants & FULL_SCOPE_PERMISSIONS and stores != STORE_CODES:
            raise AdminError(
                422,
                "Permissoes consolidadas exigem abrangencia das tres lojas",
            )
        previous = self.repo.grants(group_id)
        self.repo.replace_grants(group_id, grants)
        affected = self.repo.member_count(group_id)
        self.repo.audit(self.actor, "group.permissions.updated", "access_group",
                        str(group_id),
                        {"group": group.name, "previous": previous,
                         "current": sorted(grants), "members_affected": affected})
        self._save()
        return {"id": str(group_id), "permissions": sorted(grants),
                "members_affected": affected}

    # ---------- usuarios ----------

    def _valid_group(self, group_id: UUID | None) -> AccessGroup:
        if group_id is None:
            raise AdminError(422, "Selecione um grupo de acesso")
        group = self.repo.group(group_id)
        if group is None or not group.active:
            raise AdminError(422, "Grupo de acesso invalido ou inativo")
        return group

    def _valid_scope(self, group: AccessGroup, store_codes: list[str] | None) -> set[str]:
        group_stores = set(self.repo.group_stores(group.id))
        if store_codes is None:
            return set()
        stores = set(store_codes)
        if not stores <= STORE_CODES:
            raise AdminError(422, "Loja desconhecida no escopo do usuario")
        if not stores <= group_stores:
            raise AdminError(
                422, "As lojas do usuario precisam estar na abrangencia do grupo")
        return stores

    def add_user(self, *, subject: str, name: str, profile: str,
                 store_code: str | None = None, group_id: UUID | None = None,
                 store_codes: list[str] | None = None) -> dict:
        subject = subject.strip()
        name = name.strip()
        if not subject or not name:
            raise AdminError(422, "Identity and display name must be nonempty")
        if profile not in USER_PROFILES:
            raise AdminError(422, "Unsupported profile")
        if self.repo.user_by_subject(subject) is not None:
            raise AdminError(409, "Identity is already registered")
        # Compatibilidade: chamadas antigas informam apenas store_code e
        # assumem o grupo legado da loja; o cadastro novo envia group_id.
        group = self._resolve_group(group_id, store_code)
        scope = self._valid_scope(group, store_codes)

        user = self.repo.create_user(subject=subject, name=name, profile=profile)
        self.repo.set_membership(user.id, group.id)
        if scope:
            self.repo.replace_user_scope(user.id, scope)
        stores = self.repo.user_stores(user.id)
        self.repo.audit(self.actor, "user.created", "user", str(user.id),
                        {"profile": profile, "group": group.name,
                         "stores": stores})
        self._save()
        return {"id": str(user.id), "display_name": user.display_name,
                "profile": profile, "active": True,
                "group": {"id": str(group.id), "name": group.name},
                "stores": stores}

    def _resolve_group(self, group_id: UUID | None,
                       store_code: str | None) -> AccessGroup:
        if group_id is not None:
            return self._valid_group(group_id)
        if store_code in STORE_CODES:
            # Compatibilidade legada so vale quando ha exatamente UM grupo
            # ativo cobrindo a loja E a associacao e comprovadamente segura:
            # o grupo precisa ser exclusivo daquela loja e conter somente
            # permissoes de consulta nao-financeiras (o que um vendedor
            # recebia no modelo antigo). Um grupo amplo como Administradores
            # ou Financeiro — mesmo sendo o unico da loja — exige group_id.
            candidates = self.repo.groups_covering(store_code)
            if len(candidates) > 1:
                raise AdminError(
                    422,
                    "Ha mais de um grupo cobrindo esta loja; informe o "
                    "grupo explicitamente (group_id).",
                )
            if len(candidates) == 1:
                group = candidates[0]
                coverage = set(self.repo.group_stores(group.id))
                grants = set(self.repo.grants(group.id))
                if coverage == {store_code} and grants <= _LEGACY_SAFE_GRANTS:
                    return group
                raise AdminError(
                    422,
                    "O unico grupo desta loja nao e um grupo de vendedores "
                    "seguro para resolucao automatica; informe o grupo "
                    "explicitamente (group_id).",
                )
        raise AdminError(422, "Selecione um grupo de acesso")

    def update_user_access(self, user_id: UUID, *, profile: str | None = None,
                           group_id: UUID | None = None,
                           store_codes: list[str] | None = None) -> dict:
        user = self.repo.user(user_id)
        if user is None or getattr(user, "deleted_at", None) is not None:
            raise AdminError(404, "User not found")
        if user.is_superadmin:
            raise AdminError(403, "A conta SuperAdmin nao pode ser alterada aqui")
        if profile is not None and profile not in USER_PROFILES:
            raise AdminError(422, "Funcao invalida")
        group = self._valid_group(group_id) if group_id is not None else self.repo.group_of(user_id)
        if group is None or not group.active:
            raise AdminError(422, "O usuario precisa pertencer a um grupo ativo")
        # store_codes omitido: preserva o escopo individual atual — uma
        # atualizacao parcial nunca amplia o acesso do usuario. Lista vazia
        # enviada explicitamente = herdar toda a abrangencia do grupo.
        scope = self._valid_scope(group, store_codes) if store_codes is not None else None
        if scope is None and group_id is not None:
            # Troca de grupo com restricao individual TOTALMENTE incompativel:
            # preservar as linhas deixaria o usuario sem nenhuma loja, e limpa-
            # las equivaleria a "herdar tudo" sem pedido explicito. Exige-se a
            # definicao consciente do novo escopo (lista, mesmo vazia).
            current = self.repo.group_of(user_id)
            existing_scope = set(self.repo.user_scope(user_id))
            if (current is not None and current.id != group.id and existing_scope
                    and not (existing_scope & set(self.repo.group_stores(group.id)))):
                raise AdminError(
                    422,
                    "A restricao individual do usuario nao existe na abrangencia "
                    "do novo grupo. Defina o escopo explicitamente "
                    "(store_codes, mesmo vazio para herdar toda a abrangencia).",
                )

        previous = {
            "profile": user.profile,
            "group": getattr(self.repo.group_of(user_id), "name", None),
            "stores": self.repo.user_stores(user_id),
            "store_scope": self.repo.user_scope(user_id),
        }
        if profile is not None:
            user.profile = profile
        self.repo.set_membership(user_id, group.id)
        if scope is not None:
            self.repo.replace_user_scope(user_id, scope)
        current_stores = self.repo.user_stores(user_id)
        current_scope = self.repo.user_scope(user_id)
        self.repo.audit(self.actor, "user.access.changed", "user", str(user_id),
                        {"previous": previous,
                         "current": {"profile": user.profile, "group": group.name,
                                     "stores": current_stores,
                                     "store_scope": current_scope}})
        self._save()
        return {"user_id": str(user_id), "profile": user.profile,
                "group": {"id": str(group.id), "name": group.name},
                "stores": current_stores, "store_scope": current_scope}

    def replace_user_overrides(self, user_id: UUID, permissions: dict[str, bool | None]) -> dict:
        user = self.repo.user(user_id)
        if user is None or getattr(user, "deleted_at", None) is not None:
            raise AdminError(404, "User not found")
        if user.is_superadmin:
            raise AdminError(422, "O SuperAdmin nao recebe excecoes")
        unknown = set(permissions) - GRANTABLE_PERMISSIONS
        if unknown:
            raise AdminError(
                422, "Permissao nao delegavel ou desconhecida: " + sorted(unknown)[0])
        previous = self.repo.overrides(user_id)
        self.repo.replace_overrides(user_id, permissions)
        current = {key: value for key, value in permissions.items() if value is not None}
        self.repo.audit(self.actor, "user.permissions.updated", "user", str(user_id),
                        {"previous": previous, "current": current})
        self._save()
        return {"user_id": str(user_id), "overrides": current}

    def assign_user_store(self, user_id: UUID, store_code: str) -> dict:
        """Compatibilidade: restringe o escopo individual a uma unica loja."""
        if store_code not in STORE_CODES:
            raise AdminError(422, "Unknown store")
        return self.update_user_access(user_id, store_codes=[store_code])

    def set_user_active(self, user_id: UUID, active: bool) -> dict:
        user = self.repo.user(user_id)
        if user is None or getattr(user, "deleted_at", None) is not None:
            raise AdminError(404, "User not found")
        if user.is_superadmin or user.id == self.actor.id:
            raise AdminError(403, "The superadministrator cannot be deactivated here")
        previous = user.active
        user.active = active
        self.repo.audit(self.actor, "user.status.changed", "user", str(user_id),
                        {"previous": previous, "current": active})
        self._save()
        return {"user_id": str(user_id), "active": active}

    @staticmethod
    def _public_invitation(invite: AccessInvitation) -> dict:
        return {
            "id": str(invite.id),
            "email": invite.email,
            "display_name": invite.display_name,
            "profile": invite.profile,
            "store_code": invite.store_code,
            "status": invite.status,
            "revision": invite.revision,
            "created_at": invite.created_at.isoformat(),
            "delivery": "not_configured",
        }

    def list_invitations(self) -> list[dict]:
        return [self._public_invitation(invite) for invite in self.repo.invitations()]

    def prepare_invitation(self, *, email: str, name: str, profile: str,
                           store_code: str | None) -> dict:
        """Safe pre-registration only. Does not send email, mint tokens or create passwords."""
        name = " ".join(name.strip().split())
        email = email.strip()
        email_key = email.casefold()
        if not 2 <= len(name) <= 150:
            raise AdminError(422, "Informe o nome do colaborador")
        if (len(email_key) > 254 or not re.fullmatch(
            r"[^@\s]+@[^@\s]+\.[^@\s]+", email_key
        )):
            raise AdminError(422, "Informe um e-mail valido")
        if profile not in {"administrator", "seller"}:
            raise AdminError(422, "Perfil invalido")
        if profile == "seller":
            if store_code not in STORE_CODES:
                raise AdminError(422, "Selecione uma loja valida para o vendedor")
        elif store_code is not None:
            raise AdminError(422, "Administrador tem acesso as tres lojas")

        existing = self.repo.invitation_by_email(email_key)
        if existing is not None and existing.status != "cancelled":
            raise AdminError(409, "Este e-mail ja tem um pre-cadastro")
        if existing is None:
            invite = self.repo.add_invitation(
                email=email_key, email_key=email_key, name=name,
                profile=profile, store_code=store_code, actor_id=self.actor.id,
            )
            action = "access.invitation.prepared"
        else:
            invite = existing
            invite.email = email_key
            invite.display_name = name
            invite.profile = profile
            invite.store_code = store_code
            invite.status = "prepared"
            invite.updated_by = self.actor.id
            invite.revision += 1
            action = "access.invitation.reopened"
        self.repo.audit(self.actor, action, "access_invitation", str(invite.id),
                        {"profile": profile, "store": store_code,
                         "delivery": "not_configured"})
        self._save()
        return self._public_invitation(invite)

    def cancel_invitation(self, invitation_id: UUID, expected_revision: int) -> dict:
        invite = self.repo.invitation(invitation_id)
        if invite is None:
            raise AdminError(404, "Pre-cadastro nao encontrado")
        if invite.revision != expected_revision:
            raise AdminError(409, "O pre-cadastro foi alterado. Atualize a tela")
        if invite.status != "prepared":
            raise AdminError(409, "Somente pre-cadastros nao enviados podem ser cancelados")
        invite.status = "cancelled"
        invite.updated_by = self.actor.id
        invite.revision += 1
        self.repo.audit(self.actor, "access.invitation.cancelled",
                        "access_invitation", str(invite.id),
                        {"previous": "prepared", "current": "cancelled"})
        self._save()
        return self._public_invitation(invite)

    def list_audit(self, *, limit: int, offset: int) -> dict:
        events = self.repo.audit_history(limit=limit, offset=offset)
        return {"items": [
            {
                "id": str(event.id),
                "actor_id": str(event.actor_id) if event.actor_id is not None else None,
                "action": event.action,
                "entity_type": event.entity_type,
                "entity_id": event.entity_id,
                "details": event.details,
                "created_at": event.created_at.isoformat(),
            }
            for event in events
        ], "limit": limit, "offset": offset}
