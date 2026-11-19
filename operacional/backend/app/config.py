"""Configuracao por ambiente: sem segredos no repositorio."""
from functools import lru_cache
from typing import Literal
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    app_env: Literal["development", "production"] = "development"
    cors_origins: str = "http://localhost:5173"
    oidc_issuer: str = ""
    oidc_audience: str = ""
    oidc_jwks_url: str = ""

    # Integracao ERP — pasta privada DadosUMA (Google Drive, somente leitura).
    erp_sync_enabled: bool = False
    erp_sync_interval_seconds: int = 600
    google_drive_folder_id: str = ""
    # Caminho para o JSON da conta de servico (fora do repositorio) ou JSON inline.
    google_service_account_json: str = ""
    erp_drive_vendas_name: str = "vendas.csv"
    erp_drive_devolucoes_name: str = "devolucoes.csv"
    erp_drive_despesas_name: str = "despesas.csv"

    def allowed_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
