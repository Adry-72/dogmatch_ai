"""Tool prenotazione aree cani certificate DogMatch."""
import logging
import random
import string
from datetime import datetime, date, timedelta

from database import get_db

logger = logging.getLogger(__name__)

_ORARI_APERTURA = range(8, 20)  # slot dalle 08:00 alle 19:00 (incluso)


def _genera_codice() -> str:
    chars = string.ascii_uppercase + string.digits
    return "DM-" + "".join(random.choices(chars, k=8))


def _fmt_ora(ora: int) -> str:
    return f"{ora:02d}:00"


async def get_available_slots(data: str, area_id: int | None = None) -> str:
    """Mostra slot liberi per una data, opzionalmente filtrati per area."""
    try:
        target = datetime.strptime(data, "%Y-%m-%d").date()
    except ValueError:
        return f"Data non valida '{data}'. Usa il formato YYYY-MM-DD."

    oggi = date.today()
    if target < oggi:
        return "Non puoi prenotare slot in date passate."
    if target > oggi + timedelta(days=30):
        return "Puoi prenotare al massimo 30 giorni in anticipo."

    async with get_db() as cur:
        if area_id:
            await cur.execute(
                "SELECT id, nome, citta, provincia, separazione_taglie "
                "FROM aree_cani WHERE id = %s",
                (area_id,),
            )
        else:
            await cur.execute(
                "SELECT id, nome, citta, provincia, separazione_taglie FROM aree_cani ORDER BY id"
            )
        aree = await cur.fetchall()

        if not aree:
            return "Nessuna area trovata."

        await cur.execute(
            "SELECT area_id, HOUR(data_ora) AS ora "
            "FROM prenotazioni_area "
            "WHERE DATE(data_ora) = %s AND stato = 'attiva'",
            (target.isoformat(),),
        )
        prenotate = {(r["area_id"], r["ora"]) for r in await cur.fetchall()}

    ora_min = datetime.now().hour + 1 if target == oggi else _ORARI_APERTURA.start
    righe = [f"📅 Slot disponibili per {target.strftime('%d/%m/%Y')}:\n"]

    for area in aree:
        liberi = [
            _fmt_ora(h)
            for h in _ORARI_APERTURA
            if h >= ora_min and (area["id"], h) not in prenotate
        ]
        sep = " | Separazione taglie" if area["separazione_taglie"] else ""
        stato = ", ".join(liberi) if liberi else "Nessuno slot disponibile"
        righe.append(
            f"🏷 Area #{area['id']} — {area['nome']} ({area['citta']}, {area['provincia']}){sep}\n"
            f"   Slot liberi: {stato}"
        )

    return "\n\n".join(righe)


async def book_area_slot(user_id: str, area_id: int, data_ora: str) -> str:
    """Prenota uno slot da 1 ora in un'area cani."""
    try:
        dt = datetime.strptime(data_ora, "%Y-%m-%d %H:%M")
    except ValueError:
        return f"Formato data/ora non valido '{data_ora}'. Usa YYYY-MM-DD HH:MM."

    if dt.date() < date.today():
        return "Non puoi prenotare in date passate."
    if dt.hour not in _ORARI_APERTURA:
        return f"Orario non disponibile. Le aree sono aperte dalle 08:00 alle 19:00."
    if dt.minute != 0:
        dt = dt.replace(minute=0, second=0, microsecond=0)

    async with get_db() as cur:
        await cur.execute("SELECT nome, citta FROM aree_cani WHERE id = %s", (area_id,))
        area = await cur.fetchone()
        if not area:
            return f"Area #{area_id} non trovata. Usa get_available_slots per vedere le aree disponibili."

        await cur.execute(
            "SELECT id FROM prenotazioni_area "
            "WHERE area_id = %s AND data_ora = %s AND stato = 'attiva'",
            (area_id, dt),
        )
        if await cur.fetchone():
            return (
                f"Lo slot delle {_fmt_ora(dt.hour)} del {dt.strftime('%d/%m/%Y')} "
                f"a {area['nome']} è già occupato. Scegli un altro orario."
            )

        await cur.execute(
            "SELECT id FROM prenotazioni_area "
            "WHERE user_id = %s AND data_ora = %s AND stato = 'attiva'",
            (user_id, dt),
        )
        if await cur.fetchone():
            return "Hai già una prenotazione attiva per questo orario in un'altra area."

        codice = _genera_codice()
        for _ in range(5):
            try:
                await cur.execute(
                    "INSERT INTO prenotazioni_area (codice, user_id, area_id, data_ora) "
                    "VALUES (%s, %s, %s, %s)",
                    (codice, user_id, area_id, dt),
                )
                break
            except Exception:
                codice = _genera_codice()
        else:
            return "Errore nella generazione del codice. Riprova."

    return (
        f"✅ Prenotazione confermata!\n\n"
        f"📍 {area['nome']} — {area['citta']}\n"
        f"📅 {dt.strftime('%d/%m/%Y')} alle {_fmt_ora(dt.hour)} (1 ora)\n"
        f"🎫 Codice: **{codice}**\n\n"
        f"Conserva il codice: ti servirà per cancellare la prenotazione se necessario."
    )


async def get_user_bookings(user_id: str) -> str:
    """Mostra le prenotazioni attive dell'utente."""
    async with get_db() as cur:
        await cur.execute(
            "SELECT p.codice, a.nome, a.citta, p.data_ora "
            "FROM prenotazioni_area p "
            "JOIN aree_cani a ON a.id = p.area_id "
            "WHERE p.user_id = %s AND p.stato = 'attiva' AND p.data_ora >= NOW() "
            "ORDER BY p.data_ora ASC "
            "LIMIT 10",
            (user_id,),
        )
        prenotazioni = await cur.fetchall()

    if not prenotazioni:
        return "Non hai prenotazioni attive nelle aree cani."

    righe = ["📋 Le tue prenotazioni attive:\n"]
    for p in prenotazioni:
        dt = p["data_ora"]
        righe.append(
            f"• {dt.strftime('%d/%m/%Y')} ore {dt.strftime('%H:%M')} — "
            f"{p['nome']} ({p['citta']})  |  Codice: {p['codice']}"
        )
    return "\n".join(righe)


async def cancel_booking(user_id: str, codice: str) -> str:
    """Cancella una prenotazione tramite codice."""
    codice = codice.strip().upper()
    async with get_db() as cur:
        await cur.execute(
            "SELECT p.id, p.data_ora, a.nome, a.citta "
            "FROM prenotazioni_area p "
            "JOIN aree_cani a ON a.id = p.area_id "
            "WHERE p.codice = %s AND p.user_id = %s AND p.stato = 'attiva'",
            (codice, user_id),
        )
        row = await cur.fetchone()
        if not row:
            return (
                f"Prenotazione con codice {codice} non trovata o non appartiene al tuo account."
            )

        await cur.execute(
            "UPDATE prenotazioni_area SET stato = 'cancellata' WHERE id = %s",
            (row["id"],),
        )

    dt = row["data_ora"]
    return (
        f"✅ Prenotazione {codice} cancellata.\n"
        f"📍 {row['nome']} — {row['citta']}, "
        f"{dt.strftime('%d/%m/%Y')} ore {dt.strftime('%H:%M')}"
    )
