"""Private file persistence for ERP-independent marketing and training routines.

Small validated files are stored in PostgreSQL; they never enter GitHub Pages
or a public static folder. Authentication and permission checks apply to every
download, write and delete. No external object storage is required at v1 scale.
"""
from datetime import date, datetime, timezone
from hashlib import sha256
from uuid import UUID

from sqlalchemy import select

from app.models import (
    TrainingDocument, TrainingRecord, WhatsAppFile, WhatsAppPost,
)
from app.operations_service import OperationError
from app.policy import can_access
from app.routines_service import RoutinesService, start_of

MAX_ART_BYTES = 3 * 1024 * 1024
MAX_TRAINING_BYTES = 10 * 1024 * 1024
IMAGE_EXTENSIONS = {
    "image/png": (".png",),
    "image/jpeg": (".jpg", ".jpeg"),
    "image/webp": (".webp",),
}
OFFICE_MIMES = {
    "wordprocessingml": ("application/vnd.openxmlformats-officedocument"
                        ".wordprocessingml.document", ".docx"),
    "spreadsheetml": ("application/vnd.openxmlformats-officedocument"
                      ".spreadsheetml.sheet", ".xlsx"),
    "presentationml": ("application/vnd.openxmlformats-officedocument"
                       ".presentationml.presentation", ".pptx"),
}
TRAINING_MEDIA = {
    **IMAGE_EXTENSIONS,
    "application/pdf": (".pdf",),
    "text/plain": (".txt",),
    "text/csv": (".csv",),
    "video/mp4": (".mp4",),
    "video/quicktime": (".mov",),
    "video/webm": (".webm",),
    "audio/mpeg": (".mp3",),
    "audio/wav": (".wav",),
    **{mime: (ext,) for mime, ext in OFFICE_MIMES.values()},
}


def _office_media(data: bytes) -> str | None:
    """DOCX/XLSX/PPTX sao conteineres ZIP; o tipo real esta no [Content_Types].xml.

    Leitura limitada do membro (evita descompactacao excessiva) e rejeita
    pacotes com macros (vbaProject.bin).
    """
    if not data.startswith(b"PK\x03\x04"):
        return None
    try:
        import io, zipfile
        with zipfile.ZipFile(io.BytesIO(data)) as pack:
            names = {n.casefold() for n in pack.namelist()}
            if any(n.endswith("vbaproject.bin") for n in names):
                return None
            member = next((n for n in pack.namelist()
                           if n.casefold() == "[content_types].xml"), None)
            if member is None:
                return None
            info = pack.getinfo(member)
            if info.file_size > 4 * 1024 * 1024 or info.compress_size > 1024 * 1024:
                return None
            with pack.open(info) as fh:
                head = fh.read(64 * 1024).decode("utf-8", "ignore")
    except Exception:
        return None
    for marker, (mime, _ext) in OFFICE_MIMES.items():
        if marker in head:
            return mime
    return None


def _text_media(data: bytes, filename: str) -> str | None:
    try:
        data[:8192].decode("utf-8")
    except UnicodeDecodeError:
        return None
    name = filename.casefold()
    if name.endswith(".txt"):
        return "text/plain"
    if name.endswith(".csv"):
        return "text/csv"
    return None


def detect_media(data: bytes) -> str | None:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data.startswith(b"%PDF-"):
        return "application/pdf"
    if data[:4] == b"RIFF" and data[8:12] == b"WAVE":
        return "audio/wav"
    if data[4:8] == b"ftyp":
        brand = data[8:12]
        return "video/quicktime" if brand == b"qt  " else "video/mp4"
    if data.startswith(b"\x1a\x45\xdf\xa3"):
        return "video/webm"
    if data.startswith(b"ID3") or data[:2] in (b"\xff\xfb", b"\xff\xf3", b"\xff\xf2"):
        return "audio/mpeg"
    return None


def detect_training_media(data: bytes, filename: str) -> str | None:
    return detect_media(data) or _office_media(data) or _text_media(data, filename)


def validated_file(content: bytes, filename: str | None,
                   client_type: str | None, media_map: dict,
                   size_limit: int, detector=None) -> tuple[str, str]:
    if not content or len(content) > size_limit:
        raise OperationError(413, "Arquivo vazio ou maior que o limite permitido")
    detected = detector(content, filename or "") if detector else detect_media(content)
    if detected not in media_map:
        raise OperationError(422, "Formato não permitido para este anexo")
    if client_type not in (None, "", "application/octet-stream", detected):
        raise OperationError(422, "O tipo informado não corresponde ao conteúdo do arquivo")
    sanitized = "".join(
        c if c.isalnum() or c in "._- ()" else "_"
        for c in (filename or "")[-120:]
    ).strip(" .")
    if not sanitized:
        raise OperationError(422, "Informe um arquivo com nome válido")
    extensions = media_map[detected]
    if not sanitized.casefold().endswith(extensions):
        raise OperationError(422, "Extensão não corresponde ao formato enviado")
    return sanitized, detected


def info(record: WhatsAppFile | TrainingDocument) -> dict:
    return {
        "name": record.original_name, "media_type": record.media_type,
        "size": record.byte_length, "revision": record.revision,
    }


class AttachmentService(RoutinesService):
    def put_whatsapp(self, when: date, kind: str, raw: bytes,
                     filename: str | None, media_type: str | None,
                     expected: int) -> dict:
        self.require("JOINVILLE", "whatsapp_status.edit")
        if kind not in ("art", "evidence"):
            raise OperationError(422, "Tipo de anexo inválido")
        name, mime = validated_file(
            raw, filename, media_type, IMAGE_EXTENSIONS, MAX_ART_BYTES
        )
        post = self.db.scalar(select(WhatsAppPost).where(
            WhatsAppPost.post_date == start_of(when)
        ).with_for_update())
        if post is None:
            raise OperationError(404, "Cadastre o produto na data antes de anexar a arte")
        record = self.db.scalar(select(WhatsAppFile).where(
            WhatsAppFile.post_date == start_of(when), WhatsAppFile.kind == kind
        ).with_for_update())
        self.revision(record, expected)
        digest = sha256(raw).hexdigest()
        if record is None:
            record = WhatsAppFile(
                post_date=start_of(when), kind=kind, original_name=name,
                media_type=mime, byte_length=len(raw), digest=digest,
                content=raw, revision=1, uploaded_by=self.actor.id,
            )
            self.db.add(record)
        else:
            record.original_name = name
            record.media_type = mime
            record.byte_length = len(raw)
            record.digest = digest
            record.content = raw
            record.revision += 1
            record.uploaded_by = self.actor.id
            record.updated_at = datetime.now(timezone.utc)
        self.audit("whatsapp.file.saved", "whatsapp_file", f"{when}|{kind}",
                   {"kind":kind, "date":when.isoformat(), "size":len(raw),
                    "sha256":digest, "revision":record.revision})
        self.commit()
        return info(record)

    def get_whatsapp(self, when: date, kind: str) -> tuple[dict, bytes]:
        if not self.allowed("whatsapp_status.view"):
            raise OperationError(403, "Acesso negado")
        if kind not in ("art", "evidence"):
            raise OperationError(404, "Anexo não encontrado")
        item = self.db.get(WhatsAppFile, (start_of(when), kind))
        if item is None:
            raise OperationError(404, "Anexo não encontrado")
        return info(item), item.content

    def delete_whatsapp(self, when: date, kind: str, expected: int) -> dict:
        self.require("JOINVILLE", "whatsapp_status.edit")
        if kind not in ("art", "evidence"):
            raise OperationError(404, "Anexo não encontrado")
        post = self.db.scalar(select(WhatsAppPost).where(
            WhatsAppPost.post_date == start_of(when)
        ).with_for_update())
        if post is None:
            raise OperationError(404, "Planejamento não encontrado")
        item = self.db.scalar(select(WhatsAppFile).where(
            WhatsAppFile.post_date == start_of(when),
            WhatsAppFile.kind == kind
        ).with_for_update())
        if item is None:
            raise OperationError(404, "Anexo não encontrado")
        self.revision(item, expected)
        metadata = info(item)
        self.db.delete(item)
        self.audit("whatsapp.file.deleted", "whatsapp_file", f"{when}|{kind}",
                   {"date":when.isoformat(), "kind":kind, "previous":metadata})
        self.commit()
        return {"deleted":True, "date":when.isoformat(), "kind":kind}

    def _training_row(self, store: str, record_id: UUID, permission: str,
                      lock: bool = False) -> TrainingRecord:
        self.require(store, permission)
        query = select(TrainingRecord).where(
            TrainingRecord.store_code == store, TrainingRecord.id == record_id,
            TrainingRecord.deleted_at.is_(None),
        )
        record = self.db.scalar(query.with_for_update() if lock else query)
        if record is None:
            raise OperationError(404, "Treinamento não encontrado nesta loja")
        return record

    def put_training(self, store: str, record_id: UUID, raw: bytes,
                     filename: str | None, media_type: str | None,
                     expected: int) -> dict:
        self._training_row(store, record_id, "training.edit", lock=True)
        name, mime = validated_file(
            raw, filename, media_type, TRAINING_MEDIA, MAX_TRAINING_BYTES,
            detector=detect_training_media
        )
        record = self.db.scalar(select(TrainingDocument).where(
            TrainingDocument.training_id == record_id
        ).with_for_update())
        self.revision(record, expected)
        digest = sha256(raw).hexdigest()
        if record is None:
            record = TrainingDocument(
                training_id=record_id, original_name=name,
                media_type=mime, byte_length=len(raw), digest=digest,
                content=raw, revision=1, uploaded_by=self.actor.id,
            )
            self.db.add(record)
        else:
            record.original_name = name
            record.media_type = mime
            record.byte_length = len(raw)
            record.digest = digest
            record.content = raw
            record.revision += 1
            record.uploaded_by = self.actor.id
            record.updated_at = datetime.now(timezone.utc)
        self.audit("training.document.saved", "training_document", str(record_id),
                   {"store":store, "size":len(raw), "sha256":digest,
                    "revision":record.revision, "signed":False})
        self.commit()
        return info(record)

    def get_training(self, store: str, record_id: UUID) -> tuple[dict, bytes]:
        record = self._training_row(store, record_id, "training.view")
        # Somente o proprio colaborador ou quem gerencia treinamentos baixa o PDF.
        if (record.participant_id != self.actor.id
                and not can_access(self.principal, "training.edit", store)):
            raise OperationError(403, "Acesso negado")
        item = self.db.get(TrainingDocument, record_id)
        if item is None:
            raise OperationError(404, "Documento não encontrado")
        return info(item), item.content

    def delete_training(self, store: str, record_id: UUID, expected: int) -> dict:
        self._training_row(store, record_id, "training.edit", lock=True)
        item = self.db.scalar(select(TrainingDocument).where(
            TrainingDocument.training_id == record_id
        ).with_for_update())
        if item is None:
            raise OperationError(404, "Documento não encontrado")
        self.revision(item, expected)
        metadata = info(item)
        self.db.delete(item)
        self.audit("training.document.deleted", "training_document", str(record_id),
                   {"store":store, "previous":metadata, "signed":False})
        self.commit()
        return {"deleted":True, "training_id":str(record_id)}
