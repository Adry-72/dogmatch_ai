import logging
from database import get_db

logger = logging.getLogger(__name__)


async def load_user_memory(user_id: str) -> str:
    async with get_db() as cur:
        await cur.execute(
            "SELECT chiave, valore FROM ai_memoria WHERE user_id = %s ORDER BY aggiornato_at DESC",
            (user_id,),
        )
        rows = await cur.fetchall()
    if not rows:
        return ""

    facts = [(r["chiave"], r["valore"]) for r in rows if not r["chiave"].startswith("todo_")]
    todos = [(r["chiave"].removeprefix("todo_"), r["valore"]) for r in rows if r["chiave"].startswith("todo_")]

    parts = []
    if facts:
        lines = "\n".join(f"- {k}: {v}" for k, v in facts)
        parts.append(f"Ricordi su questo utente:\n{lines}")
    if todos:
        lines = "\n".join(f"- [{id}] {testo}" for id, testo in todos)
        parts.append(f"Promemoria in sospeso (ricordali proattivamente all'utente):\n{lines}")

    return "\n\n".join(parts)


async def save_memory(user_id: str, chiave: str, valore: str) -> str:
    async with get_db() as cur:
        await cur.execute(
            """INSERT INTO ai_memoria (user_id, chiave, valore, aggiornato_at)
               VALUES (%s, %s, %s, NOW())
               ON DUPLICATE KEY UPDATE valore = VALUES(valore), aggiornato_at = NOW()""",
            (user_id, chiave, valore),
        )
    logger.info("Memoria salvata [%s]: %s = %s", user_id, chiave, valore)
    return f"Ricordato: {chiave} → {valore}"


async def save_reminder(user_id: str, id: str, testo: str) -> str:
    async with get_db() as cur:
        await cur.execute(
            """INSERT INTO ai_memoria (user_id, chiave, valore, aggiornato_at)
               VALUES (%s, %s, %s, NOW())
               ON DUPLICATE KEY UPDATE valore = VALUES(valore), aggiornato_at = NOW()""",
            (user_id, f"todo_{id}", testo),
        )
    logger.info("Promemoria salvato [%s]: %s = %s", user_id, id, testo)
    return f"Promemoria salvato: ricorderò a {user_id} di {testo}"


async def clear_reminder(user_id: str, id: str) -> str:
    async with get_db() as cur:
        await cur.execute(
            "DELETE FROM ai_memoria WHERE user_id = %s AND chiave = %s",
            (user_id, f"todo_{id}"),
        )
    logger.info("Promemoria rimosso [%s]: %s", user_id, id)
    return f"Promemoria '{id}' completato e rimosso."
