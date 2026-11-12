"""Agendador da sincronizacao ERP: executa a aquisicao em segundo plano.

Intervalo configuravel por ERP_SYNC_INTERVAL_SECONDS (padrao 600 = 10 min).
So inicia quando ERP_SYNC_ENABLED=true; falhas ficam registradas em
erp_source_files e nunca derrubam a API.
"""
import asyncio
import logging

from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_engine

logger = logging.getLogger("portal_uma.erp_sync")


def run_sync_once() -> list[dict]:
    """Executa um ciclo de sincronizacao com sessao propria."""
    from app.erp_sales_service import run_drive_sync

    with Session(get_engine()) as db:
        return run_drive_sync(db)


def start() -> asyncio.Task | None:
    settings = get_settings()
    if not settings.erp_sync_enabled or not settings.google_drive_folder_id:
        logger.info("Sincronizacao ERP do Drive desabilitada.")
        return None
    interval = max(60, settings.erp_sync_interval_seconds)

    async def loop() -> None:
        # Primeira execucao rapida para refletir o estado atual dos arquivos.
        await asyncio.sleep(10)
        while True:
            try:
                results = await asyncio.to_thread(run_sync_once)
                for item in results:
                    if item.get("status") == "FAILED":
                        logger.warning(
                            "Sincronizacao ERP falhou para %s: %s",
                            item.get("file_key"), item.get("last_error"),
                        )
            except Exception:  # noqa: BLE001 - agendador nunca derruba a API
                logger.exception("Ciclo de sincronizacao ERP falhou.")
            await asyncio.sleep(interval)

    logger.info("Sincronizacao ERP do Drive ativa a cada %s segundos.", interval)
    return asyncio.create_task(loop())
