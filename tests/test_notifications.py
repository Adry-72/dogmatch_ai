import pytest
import numpy as np
from datetime import datetime, UTC
from unittest.mock import AsyncMock, patch


# ── Matching math ─────────────────────────────────────────────────────────────

def test_soglia_affinita_alta():
    from tools.notifications import _MATCH_THRESHOLD
    assert 0.75 >= _MATCH_THRESHOLD


def test_soglia_affinita_bassa():
    from tools.notifications import _MATCH_THRESHOLD
    assert 0.20 < _MATCH_THRESHOLD


def test_cosine_vettori_identici():
    v = np.array([0.3, 0.7, 0.1], dtype=np.float32)
    norm = v / np.linalg.norm(v)
    assert abs(float(np.dot(norm, norm)) - 1.0) < 1e-5


def test_cosine_vettori_ortogonali():
    a = np.array([1.0, 0.0], dtype=np.float32)
    b = np.array([0.0, 1.0], dtype=np.float32)
    score = float(np.dot(a / np.linalg.norm(a), b / np.linalg.norm(b)))
    assert abs(score) < 1e-5


def test_cosine_vettori_opposti():
    v = np.array([1.0, 0.0], dtype=np.float32)
    score = float(np.dot(v / np.linalg.norm(v), -v / np.linalg.norm(v)))
    assert score < 0


# ── run_notification_scan ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_prima_esecuzione_imposta_baseline():
    """Il primo run imposta _last_scan senza interrogare il DB."""
    from tools import notifications
    notifications._last_scan = None

    with patch("tools.notifications._new_dogs_since", new_callable=AsyncMock) as mock_dogs:
        await notifications.run_notification_scan()
        mock_dogs.assert_not_called()

    assert notifications._last_scan is not None


@pytest.mark.asyncio
async def test_nessun_cane_nuovo_salta_utenti():
    """Se non ci sono nuovi cani, non si caricano le preferenze utenti."""
    from tools import notifications
    notifications._last_scan = datetime.now(UTC)

    with patch("tools.notifications._new_dogs_since", new_callable=AsyncMock, return_value=[]), \
         patch("tools.notifications._users_with_preferences", new_callable=AsyncMock) as mock_users:
        await notifications.run_notification_scan()
        mock_users.assert_not_called()


@pytest.mark.asyncio
async def test_nessun_utente_con_preferenze_salta_save():
    """Se nessun utente ha preferenze, non si salvano notifiche."""
    from tools import notifications
    notifications._last_scan = datetime.now(UTC)

    fake_dog = {"id": 1, "nome": "Rex", "razza": "Labrador", "sesso": "M",
                "eta": 2, "taglia": "Grande", "descrizione": "", "info_sanitarie": "", "provincia": "MI"}

    with patch("tools.notifications._new_dogs_since", new_callable=AsyncMock, return_value=[fake_dog]), \
         patch("tools.notifications._users_with_preferences", new_callable=AsyncMock, return_value=[]), \
         patch("tools.notifications._save_notification", new_callable=AsyncMock) as mock_save:
        await notifications.run_notification_scan()
        mock_save.assert_not_called()


# ── load_unread_notifications ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_load_unread_restituisce_messaggi():
    """Verifica che i messaggi delle notifiche siano restituiti correttamente."""
    fake_rows = [
        {"id": 1, "messaggio": "Rex disponibile — 78%"},
        {"id": 2, "messaggio": "Luna disponibile — 65%"},
    ]

    mock_cursor = AsyncMock()
    mock_cursor.fetchall.return_value = fake_rows
    mock_cursor.execute = AsyncMock()

    from tools.notifications import load_unread_notifications

    with patch("tools.notifications.get_db") as mock_get_db:
        mock_get_db.return_value.__aenter__ = AsyncMock(return_value=mock_cursor)
        mock_get_db.return_value.__aexit__ = AsyncMock(return_value=False)

        risultati = await load_unread_notifications("user-123")

    assert len(risultati) == 2
    assert "Rex disponibile — 78%" in risultati
    assert "Luna disponibile — 65%" in risultati


@pytest.mark.asyncio
async def test_load_unread_nessuna_notifica():
    """Con zero notifiche restituisce lista vuota."""
    mock_cursor = AsyncMock()
    mock_cursor.fetchall.return_value = []
    mock_cursor.execute = AsyncMock()

    from tools.notifications import load_unread_notifications

    with patch("tools.notifications.get_db") as mock_get_db:
        mock_get_db.return_value.__aenter__ = AsyncMock(return_value=mock_cursor)
        mock_get_db.return_value.__aexit__ = AsyncMock(return_value=False)

        risultati = await load_unread_notifications("user-vuoto")

    assert risultati == []
