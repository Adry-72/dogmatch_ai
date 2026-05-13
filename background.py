import asyncio
import logging
from tools.notifications import run_notification_scan

logger = logging.getLogger(__name__)

_SCAN_INTERVAL = 300  # secondi (5 minuti)


async def notification_loop() -> None:
    """Esegue run_notification_scan ogni _SCAN_INTERVAL secondi."""
    while True:
        try:
            await run_notification_scan()
        except Exception as exc:
            logger.error("Errore nel notification scanner: %s", exc, exc_info=True)
        await asyncio.sleep(_SCAN_INTERVAL)
