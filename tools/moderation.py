import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

_LOG_PATH = Path(__file__).parent.parent / "moderation_log.jsonl"


async def moderation_flag(content: str, reason: str, user_id: str) -> str:
    flag_id = str(uuid.uuid4())[:12].upper()
    timestamp = datetime.now(timezone.utc).isoformat()

    # Structured log to file (append-only audit trail)
    import json
    entry = {
        "flag_id": flag_id,
        "timestamp": timestamp,
        "user_id": user_id,
        "reason": reason,
        "content_preview": content[:200],
    }
    try:
        with open(_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.error("Impossibile scrivere moderation log: %s", e)

    logger.warning(
        "[MODERATION] flag_id=%s user=%s reason=%s content=%r",
        flag_id, user_id, reason, content[:100],
    )

    return (
        f"⚠️ Contenuto segnalato al team DogMatch (ID: {flag_id}).\n"
        "La segnalazione verrà esaminata entro 24 ore.\n"
        "Se hai bisogno di assistenza urgente, usa la sezione 'Supporto' nell'app."
    )
