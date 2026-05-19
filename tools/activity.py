"""Tool statistiche attività e match dell'utente su DogMatch."""
import logging
from database import get_db

logger = logging.getLogger(__name__)


async def get_activity_stats(user_id: str) -> str:
    """Restituisce statistiche aggregate di match, like e messaggi dell'utente."""
    async with get_db() as cur:
        # Recupera i cani dell'utente
        await cur.execute(
            "SELECT id, nome, razza FROM cani WHERE utente_id = %s",
            (user_id,),
        )
        cani = await cur.fetchall()

    if not cani:
        return (
            "Non hai ancora registrato un cane su DogMatch. "
            "Crea il profilo del tuo cane per iniziare a fare match!"
        )

    dog_ids = tuple(c["id"] for c in cani)
    dog_map = {c["id"]: f"{c['nome']} ({c['razza']})" for c in cani}
    placeholders = ",".join(["%s"] * len(dog_ids))

    async with get_db() as cur:
        # Match attivi
        await cur.execute(
            f"""
            SELECT
                i.id, i.intento, i.created_at,
                cm.id AS m_id, cm.nome AS m_nome, cm.razza AS m_razza,
                cd.id AS d_id, cd.nome AS d_nome, cd.razza AS d_razza,
                (SELECT contenuto FROM messaggi
                 WHERE interazione_id = i.id
                 ORDER BY created_at DESC LIMIT 1) AS ultimo_msg,
                (SELECT COUNT(*) FROM messaggi
                 WHERE interazione_id = i.id
                   AND mittente_utente_id != %s
                   AND is_letto = 0) AS non_letti
            FROM interazioni i
            JOIN cani cm ON cm.id = i.mittente_cane_id
            JOIN cani cd ON cd.id = i.destinatario_cane_id
            WHERE i.is_match = 1
              AND i.tipo = 'like'
              AND (i.mittente_cane_id IN ({placeholders})
                   OR i.destinatario_cane_id IN ({placeholders}))
            ORDER BY i.created_at DESC
            LIMIT 10
            """,
            (user_id, *dog_ids, *dog_ids),
        )
        matches = await cur.fetchall()

        # Like ricevuti in attesa (nessun match ancora)
        await cur.execute(
            f"""
            SELECT COUNT(*) AS cnt
            FROM interazioni
            WHERE destinatario_cane_id IN ({placeholders})
              AND tipo = 'like'
              AND is_match = 0
            """,
            dog_ids,
        )
        pending = (await cur.fetchone())["cnt"]

        # Like inviati totali
        await cur.execute(
            f"""
            SELECT COUNT(*) AS cnt
            FROM interazioni
            WHERE mittente_cane_id IN ({placeholders})
              AND tipo = 'like'
            """,
            dog_ids,
        )
        likes_sent = (await cur.fetchone())["cnt"]

    total_non_letti = sum(m["non_letti"] for m in matches)

    righe = [
        "📊 La tua attività su DogMatch:\n",
        f"🤝 Match attivi: {len(matches)}",
        f"💬 Messaggi non letti: {total_non_letti}",
        f"❤️ Like ricevuti in attesa di risposta: {pending}",
        f"👍 Like inviati: {likes_sent}",
    ]

    if matches:
        righe.append("\n📋 Match recenti:")
        for m in matches:
            # Determina quale cane è dell'utente e quale è l'altro
            if m["m_id"] in dog_map:
                mio_cane = dog_map[m["m_id"]]
                altro = f"{m['d_nome']} ({m['d_razza']})"
            else:
                mio_cane = dog_map.get(m["d_id"], "il tuo cane")
                altro = f"{m['m_nome']} ({m['m_razza']})"

            intento_label = "accoppiamento 🐾" if m["intento"] == "accoppiamento" else "gioco 🌳"
            non_letti_label = f" | ⚠️ {m['non_letti']} non letti" if m["non_letti"] else ""
            ultimo = f' | Ultimo msg: "{m["ultimo_msg"][:60]}"' if m["ultimo_msg"] else " | Nessun messaggio ancora"

            righe.append(
                f"• {mio_cane} ↔ {altro} [{intento_label}]{ultimo}{non_letti_label}"
            )

    if pending > 0:
        righe.append(
            f"\n💡 Hai {pending} richiesta/e di match in attesa! "
            "Vai nella sezione Richieste per rispondere."
        )

    return "\n".join(righe)
