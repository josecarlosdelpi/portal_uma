"""Aquisicao compartilhada de arquivos na pasta privada DadosUMA do Google Drive.

Contrato unico para as frentes comercial (A) e financeira (B): um so cliente,
uma so tabela de estado (erp_source_files) e um so agendador. Cada frente
registra handlers por file_key; esta frente implementa VENDAS e DEVOLUCOES.

Autenticacao: conta de servico Google com escopo drive.readonly, usando JWT
RS256 assinado com PyJWT (dependencia ja presente). Nenhuma credencial no
repositorio: o JSON da conta de servico vem de variavel de ambiente/arquivo
local ignorado pelo git.
"""
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import jwt
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ErpSourceFile

TOKEN_URL = "https://oauth2.googleapis.com/token"
DRIVE_FILES_URL = "https://www.googleapis.com/drive/v3/files"
DRIVE_SCOPE = "https://www.googleapis.com/auth/drive.readonly"

# Nomes esperados na pasta DadosUMA (case-insensitive). A frente B registra
# sua propria entrada (ex.: "DESPESAS": "despesas.csv") reutilizando o contrato.
EXPECTED_FILES = {
    "VENDAS": "vendas.csv",
    "DEVOLUCOES": "devolucoes.csv",
}


class DriveError(Exception):
    """Falha de aquisicao remota; registrada no estado da fonte."""


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def load_service_account(raw: str) -> dict:
    """Aceita caminho para o JSON ou o proprio conteudo JSON."""
    value = (raw or "").strip()
    if not value:
        raise DriveError("Credencial da conta de servico nao configurada.")
    candidate = Path(value)
    try:
        if candidate.is_file():
            value = candidate.read_text(encoding="utf-8")
    except (OSError, ValueError):
        pass
    try:
        data = json.loads(value)
    except json.JSONDecodeError as exc:
        raise DriveError("JSON da conta de servico invalido.") from exc
    if not data.get("client_email") or not data.get("private_key"):
        raise DriveError("Conta de servico sem client_email/private_key.")
    return data


class DriveClient:
    """Leitura minima do Drive via API v3, sem dependencias novas."""

    def __init__(self, service_account: dict, folder_id: str, timeout: int = 30):
        self._sa = service_account
        self._folder_id = folder_id
        self._timeout = timeout
        self._token = ""
        self._token_exp = 0.0

    def _access_token(self) -> str:
        if self._token and time.time() < self._token_exp - 60:
            return self._token
        now = int(time.time())
        assertion = jwt.encode(
            {
                "iss": self._sa["client_email"],
                "scope": DRIVE_SCOPE,
                "aud": TOKEN_URL,
                "iat": now,
                "exp": now + 3600,
            },
            self._sa["private_key"],
            algorithm="RS256",
        )
        body = urllib.parse.urlencode({
            "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
            "assertion": assertion,
        }).encode()
        try:
            with urllib.request.urlopen(
                urllib.request.Request(TOKEN_URL, data=body,
                                       headers={"Content-Type": "application/x-www-form-urlencoded"}),
                timeout=self._timeout,
            ) as response:
                payload = json.loads(response.read().decode())
        except (urllib.error.URLError, json.JSONDecodeError, OSError) as exc:
            raise DriveError("Falha na autenticacao com o Google.") from exc
        if "access_token" not in payload:
            raise DriveError("Google nao retornou access_token.")
        self._token = payload["access_token"]
        self._token_exp = now + int(payload.get("expires_in", 3600))
        return self._token

    def _get(self, url: str) -> bytes:
        request = urllib.request.Request(
            url, headers={"Authorization": "Bearer " + self._access_token()}
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            raise DriveError(f"Google Drive respondeu HTTP {exc.code}.") from exc
        except (urllib.error.URLError, OSError) as exc:
            raise DriveError("Falha de rede ao consultar o Google Drive.") from exc

    def find_file(self, expected_name: str) -> dict | None:
        """Arquivo mais recente da pasta com o nome exato (case-insensitive)."""
        query = (
            f"'{self._folder_id}' in parents and trashed = false "
            "and mimeType != 'application/vnd.google-apps.folder'"
        )
        params = urllib.parse.urlencode({
            "q": query,
            "fields": "files(id,name,md5Checksum,modifiedTime)",
            "orderBy": "modifiedTime desc",
            "pageSize": "100",
            "supportsAllDrives": "true",
            "includeItemsFromAllDrives": "true",
        })
        try:
            payload = json.loads(self._get(f"{DRIVE_FILES_URL}?{params}").decode())
        except json.JSONDecodeError as exc:
            raise DriveError("Resposta ilegivel do Google Drive.") from exc
        candidates = [
            item for item in payload.get("files", [])
            if item.get("name", "").strip().lower() == expected_name.lower()
        ]
        return candidates[0] if candidates else None

    def download(self, file_id: str) -> bytes:
        return self._get(f"{DRIVE_FILES_URL}/{file_id}?alt=media&supportsAllDrives=true")


def _state(db: Session, file_key: str) -> ErpSourceFile:
    state = db.get(ErpSourceFile, file_key)
    if state is None:
        state = ErpSourceFile(file_key=file_key, last_status="PENDING", consecutive_failures=0)
        db.add(state)
    return state


def _modified_at(remote: dict) -> datetime | None:
    raw = remote.get("modifiedTime")
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def _unchanged(remote: dict, state: ErpSourceFile) -> bool:
    """Conteudo remoto igual ao ultimo ja processado com sucesso.

    Compara md5Checksum quando disponivel; sem ele (exports do Google),
    usa modifiedTime. So evita download se a ultima ingestao desse arquivo
    terminou bem (OK) ou ja foi pulada por ser identica (SKIPPED); uma
    falha anterior sempre dispara nova tentativa de download/ingestao.
    """
    if state.last_status not in ("OK", "SKIPPED"):
        return False
    remote_md5 = remote.get("md5Checksum")
    if remote_md5:
        return remote_md5 == state.drive_md5
    modified = _modified_at(remote)
    return modified is not None and modified == state.remote_modified_at


def sync_sources(
    db: Session,
    *,
    handlers: dict[str, object],
    expected_files: dict[str, str] | None = None,
    client: DriveClient | None = None,
    service_account: dict | None = None,
    folder_id: str | None = None,
) -> list[dict]:
    """Verifica os arquivos esperados e dispara a ingestao dos que mudaram.

    handlers[file_key](content: bytes, file_name: str, drive_file_id: str)
    deve retornar um objeto com .status (APPLIED/DUPLICATE/FAILED) ou dict.
    """
    expected = expected_files or EXPECTED_FILES
    now = _utcnow()
    if client is None:
        if not folder_id or service_account is None:
            return [
                {"file_key": key, "status": "DISABLED",
                 "message": "Sincronizacao do Drive nao configurada."}
                for key in expected
            ]
        client = DriveClient(service_account, folder_id)

    results = []
    for file_key, expected_name in expected.items():
        handler = handlers.get(file_key)
        state = _state(db, file_key)
        state.last_check_at = now
        if handler is None:
            continue
        try:
            remote = client.find_file(expected_name)
            if remote is None:
                state.last_status = "FAILED"
                state.last_error = f"Arquivo '{expected_name}' nao encontrado na pasta DadosUMA."
                state.consecutive_failures += 1
            elif _unchanged(remote, state):
                state.last_status = "SKIPPED"
                state.last_error = None
                state.consecutive_failures = 0
            else:
                content = client.download(remote["id"])
                outcome = handler(content, remote.get("name", expected_name), remote["id"])
                status = getattr(outcome, "status", None) or (
                    outcome.get("status") if isinstance(outcome, dict) else "FAILED"
                )
                state.drive_file_id = remote["id"]
                state.drive_file_name = remote.get("name", expected_name)[:150]
                state.drive_md5 = remote.get("md5Checksum")
                state.remote_modified_at = _modified_at(remote)
                state.last_sync_at = _utcnow()
                state.last_status = "OK" if status in ("APPLIED", "DUPLICATE") else "FAILED"
                if state.last_status == "FAILED":
                    state.last_error = "Arquivo rejeitado na validacao; ver lote de importacao."
                    state.consecutive_failures += 1
                else:
                    state.last_error = None
                    state.consecutive_failures = 0
        except DriveError as exc:
            state.last_status = "FAILED"
            state.last_error = str(exc)[:500]
            state.consecutive_failures += 1
        results.append({
            "file_key": file_key,
            "status": state.last_status,
            "last_error": state.last_error,
            "last_sync_at": state.last_sync_at.isoformat() if state.last_sync_at else None,
        })
    db.commit()
    return results
