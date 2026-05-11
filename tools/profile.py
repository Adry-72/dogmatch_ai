import logging
from database import get_db

logger = logging.getLogger(__name__)

_ALLOWED_FIELDS = {"bio", "provincia", "regione", "telefono"}


async def analyze_user_profile(user_id: str) -> str:
    async with get_db() as cursor:
        await cursor.execute(
            """
            SELECT u.id, u.nome, u.cognome, u.ruolo, u.bio, u.foto_url,
                   u.provincia, u.regione, u.telefono, u.is_verificato,
                   COUNT(c.id) AS num_cani,
                   SUM(CASE WHEN c.is_verificato = 1 THEN 1 ELSE 0 END) AS cani_verificati,
                   SUM(CASE WHEN c.descrizione IS NOT NULL AND LENGTH(c.descrizione) > 50 THEN 1 ELSE 0 END) AS cani_con_desc,
                   SUM(CASE WHEN c.foto_url IS NOT NULL THEN 1 ELSE 0 END) AS cani_con_foto
            FROM utenti u
            LEFT JOIN cani c ON c.utente_id = u.id
            WHERE u.id = %s
            GROUP BY u.id
            """,
            (user_id,),
        )
        row = await cursor.fetchone()

    if not row:
        return f"Utente con ID {user_id} non trovato nel database."

    profile_fields = ["bio", "foto_url", "provincia", "regione", "telefono"]
    filled = sum(1 for f in profile_fields if row.get(f))
    completeness = round((filled / len(profile_fields)) * 100)

    missing = [f.replace("_", " ") for f in profile_fields if not row.get(f)]

    suggestions = []
    if not row.get("bio"):
        suggestions.append("• Aggiungi una bio: descrivi te stesso come proprietario (aumenta i match del 35%)")
    if not row.get("foto_url"):
        suggestions.append("• Aggiungi una foto profilo — fondamentale per la fiducia degli altri utenti")
    if not row.get("provincia"):
        suggestions.append("• Imposta la tua provincia — senza posizione non ricevi match locali")
    if (row.get("num_cani") or 0) == 0:
        suggestions.append("• Registra almeno un cane — senza profilo cane non puoi fare match")
    elif (row.get("cani_con_foto") or 0) == 0:
        suggestions.append("• Aggiungi foto al tuo cane — i profili con foto ricevono 3x più match")
    if (row.get("num_cani") or 0) > 0 and (row.get("cani_con_desc") or 0) == 0:
        suggestions.append("• Descrivi il carattere del tuo cane (almeno 50 caratteri) — aiuta a trovare compagni compatibili")
    if (row.get("cani_verificati") or 0) == 0 and (row.get("num_cani") or 0) > 0:
        suggestions.append("• Ottieni il badge Verificato per il tuo cane — aumenta la fiducia del 80%")

    lines = [
        f"Analisi Profilo: {row['nome']} {row['cognome']}",
        f"• Completezza: {completeness}%",
        f"• Ruolo: {row['ruolo']}",
        f"• Cani registrati: {row.get('num_cani') or 0} ({row.get('cani_verificati') or 0} verificati)",
        f"• Provincia: {row.get('provincia') or '⚠️ NON IMPOSTATA'}",
    ]
    if missing:
        lines.append(f"• Campi mancanti: {', '.join(missing)}")
    if suggestions:
        lines.append("\nSuggerimenti per migliorare i match:")
        lines.extend(suggestions)
    else:
        lines.append("\n✅ Profilo ottimale! Nessun miglioramento necessario.")

    return "\n".join(lines)


async def update_user_profile(user_id: str, field: str, value: str) -> str:
    if field not in _ALLOWED_FIELDS:
        return (
            f"Campo '{field}' non modificabile tramite SnoutBot. "
            f"Campi consentiti: {', '.join(sorted(_ALLOWED_FIELDS))}."
        )
    if len(value) > 500:
        return "Valore troppo lungo (massimo 500 caratteri)."

    try:
        async with get_db() as cursor:
            await cursor.execute(
                f"UPDATE utenti SET `{field}` = %s WHERE id = %s",
                (value, user_id),
            )
            if cursor.rowcount == 0:
                return "Utente non trovato o il valore è già quello attuale."

        return f"✅ Campo '{field}' aggiornato con successo."
    except Exception as e:
        logger.error("Errore aggiornamento profilo utente %s campo %s: %s", user_id, field, e)
        return "Errore durante l'aggiornamento del profilo. Riprova più tardi."
