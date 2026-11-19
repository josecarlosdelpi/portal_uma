"""Procedimentos internos editados no portal, com versoes e imagens privadas.

Permissoes: training.edit gerencia o documento apenas quando a concessao
cobre TODAS as lojas as quais ele se aplica (documento global exige as
tres); training.view le apenas publicados vigentes dentro da abrangencia
efetiva do usuario.
"""
import re
from datetime import datetime, timezone
from hashlib import sha256
from uuid import UUID, uuid4

import nh3
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.attachments_service import validated_file, IMAGE_EXTENSIONS
from app.models import (
    Procedure, ProcedureFile, ProcedureStore, ProcedureVersion, TrainingRecord, User,
)
from app.operations_service import OperationError, OperationsService
from app.policy import can_access, STORE_CODES

MAX_IMAGE_BYTES = 3 * 1024 * 1024

ALLOWED_TAGS = {
    "p", "br", "h1", "h2", "h3", "h4", "strong", "b", "em", "i", "u", "s",
    "ul", "ol", "li", "blockquote", "hr", "span",
    "table", "thead", "tbody", "tr", "th", "td", "colgroup", "col",
    "img", "a",
}
ALLOWED_ATTRS = {
    "img": {"src", "alt", "width", "style"},
    "a": {"href"},
    "td": {"colspan", "rowspan"},
    "th": {"colspan", "rowspan"},
    "col": {"span"},
    "span": {"style"},
    "p": {"style"},
}


def sanitize_html(raw: str) -> str:
    """HTML do editor, confinado a subconjunto seguro. Imagens so internas."""
    cleaned = nh3.clean(
        raw or "",
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRS,
        link_rel=None,
        strip_comments=True,
        url_schemes={"http", "https", "mailto"},
    )
    # Imagem externa ou de origem desconhecida e descartada; apenas anexos internos.
    return _EXTERNAL_IMG.sub("", cleaned)


INTERNAL_FILE_PREFIX = "/api/v1/procedures/files/"
_EXTERNAL_IMG = re.compile(
    r'<img\b(?:(?!src=)[^>])*?\bsrc="(?!' + re.escape(INTERNAL_FILE_PREFIX) + r')[^"]*"[^>]*>',
    re.IGNORECASE | re.DOTALL,
)


def _version_dict(row: ProcedureVersion, include_html: bool = True) -> dict:
    out = {
        "id": str(row.id), "version_label": row.version_label,
        "status": row.status, "revision": row.revision,
        "created_at": row.created_at.isoformat(),
        "published_at": row.published_at.isoformat() if row.published_at else None,
    }
    if include_html:
        out["content_html"] = row.content_html
    return out


class ProceduresService(OperationsService):
    """Operacoes do modulo Padrões/Treinamentos."""

    def _edit_stores(self) -> set[str]:
        """Lojas onde o usuario tem training.edit efetivo (grupo+excecoes)."""
        return {store for store in STORE_CODES
                if can_access(self.principal, "training.edit", store)}

    @staticmethod
    def _required_scope(applies_to_all: bool, stores: list[str]) -> set[str]:
        return set(STORE_CODES) if applies_to_all else set(stores)

    def _can_manage(self, row: Procedure, stores: list[str]) -> bool:
        """Edicao exige cobertura de TODAS as lojas do documento.

        Um training.edit valido apenas em Joinville nao autoriza mexer em
        procedimento aplicavel a Tubarao; documentos globais exigem a
        abrangencia completa. Documento sem nenhuma loja associada nao pode
        ser gerenciado por um escopo parcial."""
        if self.principal.is_superadmin:
            return True
        required = self._required_scope(row.applies_to_all, stores)
        return bool(required) and required <= self._edit_stores()

    def _can_view(self, row: Procedure, stores: list[str]) -> bool:
        """Leitura respeita a abrangencia efetiva de view e edit."""
        if self.principal.is_superadmin or self._can_manage(row, stores):
            return True
        if row.obsolete_at is not None:
            return False
        reachable = set(self.allowed("training.view")) | self._edit_stores()
        if not reachable:
            return False
        return row.applies_to_all or bool(reachable & set(stores))

    def _applicable_stores(self, procedure_id: UUID) -> list[str]:
        return [row[0] for row in self.db.execute(
            select(ProcedureStore.store_code).where(ProcedureStore.procedure_id == procedure_id)
        )]

    def _proc_dict(self, row: Procedure, stores: list[str]) -> dict:
        draft = self.db.scalar(select(ProcedureVersion).where(
            ProcedureVersion.procedure_id == row.id, ProcedureVersion.status == "rascunho"))
        published = self.db.scalars(select(ProcedureVersion).where(
            ProcedureVersion.procedure_id == row.id, ProcedureVersion.status == "publicado"
        ).order_by(ProcedureVersion.published_at.desc())).first()
        return {
            "id": str(row.id), "code": row.code, "title": row.title,
            "summary": row.summary, "applies_to_all": row.applies_to_all,
            "stores": stores,
            "status": ("obsoleto" if row.obsolete_at else
                       "publicado" if published else "rascunho"),
            "obsolete_at": row.obsolete_at.isoformat() if row.obsolete_at else None,
            "current_version": _version_dict(published, include_html=False) if published else None,
            "draft_version": _version_dict(draft, include_html=False) if draft else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else row.created_at.isoformat(),
        }

    def list_procedures(self, status: str | None, store: str | None, q: str | None) -> list[dict]:
        if not self.allowed("training.view") and not self._edit_stores():
            raise OperationError(403, "Acesso negado")
        rows = self.db.scalars(
            select(Procedure).where(Procedure.deleted_at.is_(None)).order_by(Procedure.code)
        ).all()
        result = []
        for row in rows:
            stores = self._applicable_stores(row.id)
            info = self._proc_dict(row, stores)
            # Gestor do documento ve tudo (incl. rascunhos); demais usuarios
            # somente o publicado vigente dentro da sua abrangencia.
            if not self._can_manage(row, stores):
                if not self._can_view(row, stores) or info["current_version"] is None:
                    continue
            if status and info["status"] != status:
                continue
            if store and not (row.applies_to_all or store in stores):
                continue
            if q:
                needle = q.strip().casefold()
                if needle not in row.title.casefold() and needle not in row.code.casefold():
                    continue
            result.append(info)
        return result

    def _load(self, procedure_id: UUID) -> Procedure:
        row = self.db.scalar(select(Procedure).where(
            Procedure.id == procedure_id, Procedure.deleted_at.is_(None)
        ).with_for_update())
        if row is None:
            raise OperationError(404, "Procedimento não encontrado")
        return row

    def _current(self, procedure_id: UUID) -> ProcedureVersion | None:
        return self.db.scalars(select(ProcedureVersion).where(
            ProcedureVersion.procedure_id == procedure_id,
            ProcedureVersion.status == "publicado",
        ).order_by(ProcedureVersion.published_at.desc())).first()

    def _draft(self, procedure_id: UUID) -> ProcedureVersion | None:
        return self.db.scalar(select(ProcedureVersion).where(
            ProcedureVersion.procedure_id == procedure_id,
            ProcedureVersion.status == "rascunho"))

    def _next_label(self, procedure_id: UUID) -> str:
        count = self.db.scalar(select(func.count(ProcedureVersion.id)).where(
            ProcedureVersion.procedure_id == procedure_id)) or 0
        return str(count + 1)

    def get(self, procedure_id: UUID) -> dict:
        row = self._load(procedure_id)
        stores = self._applicable_stores(row.id)
        if not self._can_view(row, stores):
            raise OperationError(404, "Documento não está mais disponível para consulta")
        info = self._proc_dict(row, stores)
        if self._can_manage(row, stores):
            version = self._draft(row.id) or self._current(row.id)
        else:
            version = self._current(row.id)
            if version is None:
                raise OperationError(404, "Procedimento ainda não publicado")
        info["content_html"] = version.content_html if version else ""
        info["version"] = _version_dict(version) if version else None
        return info

    def create(self, title: str, summary: str, applies_to_all: bool,
               store_codes: list[str], content_html: str) -> dict:
        required = self._required_scope(applies_to_all, store_codes)
        if not required or not required <= self._edit_stores():
            raise OperationError(
                403, "Edição exige autorização em todas as lojas do documento")
        title = title.strip()
        if not 3 <= len(title) <= 140:
            raise OperationError(422, "Título inválido")
        if not applies_to_all:
            if not store_codes or any(s not in STORE_CODES for s in store_codes):
                raise OperationError(422, "Selecione ao menos uma loja válida")
        seq = self.db.scalar(select(func.count(Procedure.id))) or 0
        code = f"POP-{seq + 1:04d}"
        while self.db.scalar(select(Procedure.id).where(Procedure.code == code)):
            seq += 1
            code = f"POP-{seq + 1:04d}"
        row = Procedure(id=uuid4(), code=code, title=title, summary=summary.strip(),
                        applies_to_all=applies_to_all, created_by=self.actor.id,
                        updated_by=self.actor.id)
        self.db.add(row)
        self.db.flush()
        if not applies_to_all:
            for store in dict.fromkeys(store_codes):
                self.db.add(ProcedureStore(procedure_id=row.id, store_code=store))
        version = ProcedureVersion(
            id=uuid4(), procedure_id=row.id, version_label="1", status="rascunho",
            content_html=sanitize_html(content_html), revision=1,
            created_by=self.actor.id)
        self.db.add(version)
        self.audit("procedure.created", "procedure", str(row.id),
                   {"code": code, "title": title,
                    "stores": "all" if applies_to_all else store_codes})
        self.commit()
        return self.get(row.id)

    def save(self, procedure_id: UUID, title: str, summary: str,
             applies_to_all: bool, store_codes: list[str],
             content_html: str, expected: int) -> dict:
        row = self._load(procedure_id)
        current_stores = self._applicable_stores(row.id)
        if (not self._can_manage(row, current_stores)
                or not self._required_scope(applies_to_all, store_codes) <= self._edit_stores()):
            raise OperationError(
                403, "Edição exige autorização em todas as lojas do documento")
        if row.obsolete_at is not None:
            raise OperationError(409, "Procedimento obsoleto não pode ser editado")
        title = title.strip()
        if not 3 <= len(title) <= 140:
            raise OperationError(422, "Título inválido")
        if not applies_to_all and (not store_codes or any(s not in STORE_CODES for s in store_codes)):
            raise OperationError(422, "Selecione ao menos uma loja válida")
        draft = self._draft(row.id)
        if draft is None:
            draft = ProcedureVersion(
                id=uuid4(), procedure_id=row.id,
                version_label=self._next_label(row.id), status="rascunho",
                content_html="", revision=1, created_by=self.actor.id)
            self.db.add(draft)
            self.db.flush()
        self.revision(draft, expected)
        now = datetime.now(timezone.utc)
        row.title = title
        row.summary = summary.strip()
        row.applies_to_all = applies_to_all
        row.updated_by = self.actor.id
        row.updated_at = now
        self.db.execute(ProcedureStore.__table__.delete().where(
            ProcedureStore.procedure_id == row.id))
        if not applies_to_all:
            for store in dict.fromkeys(store_codes):
                self.db.add(ProcedureStore(procedure_id=row.id, store_code=store))
        draft.content_html = sanitize_html(content_html)
        draft.revision += 1
        self.audit("procedure.draft.saved", "procedure_version", str(draft.id),
                   {"procedure": row.code, "version": draft.version_label})
        self.commit()
        return self.get(row.id)

    def publish(self, procedure_id: UUID, expected: int) -> dict:
        row = self._load(procedure_id)
        if not self._can_manage(row, self._applicable_stores(row.id)):
            raise OperationError(
                403, "Edição exige autorização em todas as lojas do documento")
        if row.obsolete_at is not None:
            raise OperationError(409, "Procedimento obsoleto não pode ser publicado")
        draft = self.db.scalar(select(ProcedureVersion).where(
            ProcedureVersion.procedure_id == row.id,
            ProcedureVersion.status == "rascunho").with_for_update())
        if draft is None:
            raise OperationError(409, "Não há rascunho para publicar")
        self.revision(draft, expected)
        if not draft.content_html.strip():
            raise OperationError(422, "O documento está vazio")
        draft.status = "publicado"
        draft.published_at = datetime.now(timezone.utc)
        draft.published_by = self.actor.id
        draft.revision += 1
        self.audit("procedure.published", "procedure_version", str(draft.id),
                   {"procedure": row.code, "version": draft.version_label})
        self.commit()
        return self.get(row.id)

    def versions(self, procedure_id: UUID) -> list[dict]:
        row = self._load(procedure_id)
        stores = self._applicable_stores(row.id)
        if not self._can_view(row, stores):
            raise OperationError(403, "Acesso negado")
        rows = self.db.scalars(select(ProcedureVersion).where(
            ProcedureVersion.procedure_id == row.id
        ).order_by(ProcedureVersion.created_at.desc())).all()
        if not self._can_manage(row, stores):
            rows = [v for v in rows if v.status == "publicado"]
        return [_version_dict(v, include_html=False) for v in rows]

    def get_version(self, procedure_id: UUID, version_id: UUID) -> dict:
        row = self._load(procedure_id)
        stores = self._applicable_stores(row.id)
        if not self._can_view(row, stores):
            raise OperationError(404, "Documento não está mais disponível para consulta")
        version = self.db.scalar(select(ProcedureVersion).where(
            ProcedureVersion.id == version_id,
            ProcedureVersion.procedure_id == row.id))
        if version is None:
            raise OperationError(404, "Versão não encontrada")
        if version.status != "publicado" and not self._can_manage(row, stores):
            raise OperationError(403, "Acesso negado")
        return _version_dict(version)

    def mark_obsolete(self, procedure_id: UUID) -> dict:
        row = self._load(procedure_id)
        if not self._can_manage(row, self._applicable_stores(row.id)):
            raise OperationError(
                403, "Edição exige autorização em todas as lojas do documento")
        if self._current(row.id) is None:
            raise OperationError(422, "Somente procedimentos publicados podem ser obsoletos")
        if row.obsolete_at is not None:
            raise OperationError(409, "Procedimento já está obsoleto")
        row.obsolete_at = datetime.now(timezone.utc)
        row.obsolete_by = self.actor.id
        self.audit("procedure.obsoleted", "procedure", str(row.id),
                   {"code": row.code, "title": row.title})
        self.commit()
        return self.get(row.id)

    def delete(self, procedure_id: UUID) -> dict:
        row = self._load(procedure_id)
        if not self._can_manage(row, self._applicable_stores(row.id)):
            raise OperationError(
                403, "Edição exige autorização em todas as lojas do documento")
        published = self.db.scalar(select(ProcedureVersion.id).where(
            ProcedureVersion.procedure_id == row.id,
            ProcedureVersion.status == "publicado"))
        # Rascunho nunca publicado: qualquer editor exclui. Ja publicado ou
        # obsoleto: somente o SuperAdmin. A exclusao e sempre logica.
        if published is not None and not self.principal.is_superadmin:
            raise OperationError(403, "Somente o SuperAdmin pode excluir "
                                      "procedimentos já publicados ou obsoletos")
        status_before = ("obsoleto" if row.obsolete_at is not None
                         else "publicado" if published is not None else "rascunho")
        row.deleted_at = datetime.now(timezone.utc)
        self.audit("procedure.deleted", "procedure", str(row.id),
                   {"code": row.code, "title": row.title,
                    "previous_status": status_before})
        self.commit()
        return {"id": str(row.id), "deleted": True}

    # ---------- imagens ----------

    def put_file(self, procedure_id: UUID, raw: bytes, filename: str | None,
                 media_type: str | None) -> dict:
        row = self._load(procedure_id)
        if not self._can_manage(row, self._applicable_stores(row.id)):
            raise OperationError(
                403, "Edição exige autorização em todas as lojas do documento")
        if row.obsolete_at is not None:
            raise OperationError(409, "Procedimento obsoleto não recebe novos arquivos")
        name, mime = validated_file(
            raw, filename, media_type, IMAGE_EXTENSIONS, MAX_IMAGE_BYTES
        )
        record = ProcedureFile(
            id=uuid4(), procedure_id=row.id,
            original_name=name, media_type=mime,
            byte_length=len(raw), digest=sha256(raw).hexdigest(),
            content=raw, uploaded_by=self.actor.id)
        self.db.add(record)
        self.audit("procedure.file.saved", "procedure_file", str(record.id),
                   {"procedure": row.code, "size": len(raw), "sha256": record.digest})
        self.commit()
        return {"id": str(record.id), "url": f"/api/v1/procedures/files/{record.id}",
                "media_type": mime, "size": len(raw)}

    def get_file(self, file_id: UUID) -> tuple[dict, bytes]:
        record = self.db.get(ProcedureFile, file_id)
        if record is None:
            raise OperationError(404, "Imagem não encontrada")
        row = self._load(record.procedure_id)
        stores = self._applicable_stores(row.id)
        if not self._can_view(row, stores):
            raise OperationError(404, "Imagem não disponível")
        if not self._can_manage(row, stores) and self._current(row.id) is None:
            raise OperationError(404, "Procedimento ainda não publicado")
        return {"name": record.original_name, "media_type": record.media_type,
                "size": record.byte_length}, record.content
