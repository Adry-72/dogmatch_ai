"""
Notifiche proattive: scansiona i nuovi cani e avvisa gli utenti compatibili
in base alle preferenze salvate in ai_memoria.
"""
import asyncio
import logging
from datetime import datetime, UTC
from typing import Optional

import numpy as np

from database import get_db
from tools.search_dogs import _build_dog_text, _encode, _USE_EMBEDDINGS

logger = logging.getLogger(__name__)

_MATCH_THRESHOLD = 0.45   # soglia di affinità per generare la notifica
_last_scan: Optional[datetime] = None


# ── DB helpers ────────────────────────────────────────────────────────────────

async def _new_dogs_since(since: datetime) -> list[dict]:
    async with get_db() as cur:
        await cur.execute("""
            SELECT c.id, c.nome, c.razza, c.sesso, c.eta, c.taglia,
                   c.descrizione, c.info_sanitarie, u.provincia
            FROM cani c
            JOIN utenti u ON c.utente_id = u.id
            WHERE c.creato_at > %s AND c.creato_at IS NOT NULL
        """, (since,))
        return await cur.fetchall()


async def _users_with_preferences() -> list[str]:
    async with get_db() as cur:
        await cur.execute(
            "SELECT DISTINCT user_id FROM ai_memoria WHERE chiave NOT LIKE 'todo_%'"
        )
        rows = await cur.fetchall()
    return [r["user_id"] for r in rows]


async def _user_preference_text(user_id: str) -> str:
    async with get_db() as cur:
        await cur.execute(
            "SELECT valore FROM ai_memoria WHERE user_id = %s AND chiave NOT LIKE 'todo_%%'",
            (user_id,),
        )
        rows = await cur.fetchall()
    return " ".join(r["valore"] for r in rows)


async def _save_notification(user_id: str, cane_id: int, messaggio: str) -> None:
    async with get_db() as cur:
        await cur.execute(
            "INSERT IGNORE INTO notifiche (user_id, cane_id, messaggio) VALUES (%s, %s, %s)",
            (user_id, cane_id, messaggio),
        )


# ── Public API ────────────────────────────────────────────────────────────────

async def load_unread_notifications(user_id: str) -> list[str]:
    """Carica le notifiche non lette e le marca subito come lette."""
    async with get_db() as cur:
        await cur.execute(
            "SELECT id, messaggio FROM notifiche WHERE user_id = %s AND letta = 0",
            (user_id,),
        )
        rows = await cur.fetchall()
        if rows:
            ids = [r["id"] for r in rows]
            placeholders = ",".join(["%s"] * len(ids))
            await cur.execute(
                f"UPDATE notifiche SET letta = 1 WHERE id IN ({placeholders})", ids
            )
    return [r["messaggio"] for r in rows]


async def run_notification_scan() -> None:
    """Scansiona i nuovi cani e genera notifiche per gli utenti compatibili."""
    global _last_scan

    now = datetime.now(UTC)

    if _last_scan is None:
        _last_scan = now
        logger.info("Notification scanner inizializzato (baseline: %s).", now.isoformat())
        return

    since = _last_scan
    _last_scan = now

    if not _USE_EMBEDDINGS:
        logger.debug("sentence-transformers non disponibile: scan saltato.")
        return

    new_dogs = await _new_dogs_since(since)
    if not new_dogs:
        logger.debug("Nessun nuovo cane dal %s.", since.isoformat())
        return

    logger.info("Notification scan: %d nuovi cani trovati.", len(new_dogs))

    user_ids = await _users_with_preferences()
    if not user_ids:
        return

    # Carica preferenze di tutti gli utenti con memoria
    user_prefs: list[tuple[str, str]] = []
    for uid in user_ids:
        pref = await _user_preference_text(uid)
        if pref.strip():
            user_prefs.append((uid, pref))

    if not user_prefs:
        return

    for dog in new_dogs:
        dog_text = _build_dog_text(dog)

        # Batch encode: [dog, pref_utente_1, pref_utente_2, ...]
        all_texts = [dog_text] + [p for _, p in user_prefs]
        embeddings = await asyncio.to_thread(_encode, all_texts)

        dog_emb = embeddings[0]
        dog_norm = dog_emb / (np.linalg.norm(dog_emb) or 1e-8)

        for (uid, _), pref_emb in zip(user_prefs, embeddings[1:]):
            pref_norm = pref_emb / (np.linalg.norm(pref_emb) or 1e-8)
            score = float(np.dot(dog_norm, pref_norm))

            if score >= _MATCH_THRESHOLD:
                sesso_str = "M" if dog.get("sesso") == "M" else "F"
                msg = (
                    f"Nuovo cane compatibile con le tue preferenze: "
                    f"**{dog['nome']}** ({dog['razza']}, {sesso_str}, "
                    f"{dog.get('eta', '?')} anni, {dog.get('taglia', '?')}) "
                    f"— {dog.get('provincia') or 'n/d'} | Affinità: {int(score * 100)}%"
                )
                await _save_notification(uid, dog["id"], msg)
                logger.info(
                    "Notifica creata → user=%s, cane=%s (%.0f%%)",
                    uid, dog["id"], score * 100,
                )
