from collections import defaultdict
from datetime import datetime, timedelta, UTC
from fastapi import HTTPException

_WINDOW = 60   # secondi
_MAX = 10      # richieste per finestra per utente

_buckets: defaultdict[str, list] = defaultdict(list)


def check_rate_limit(user_id: str) -> None:
    now = datetime.now(UTC)
    cutoff = now - timedelta(seconds=_WINDOW)
    _buckets[user_id] = [t for t in _buckets[user_id] if t > cutoff]
    if len(_buckets[user_id]) >= _MAX:
        raise HTTPException(
            status_code=429,
            detail=f"Troppe richieste. Massimo {_MAX} al minuto per utente.",
        )
    _buckets[user_id].append(now)
