import pytest
from fastapi import HTTPException
from rate_limit import check_rate_limit, _buckets, _MAX, _WINDOW


def setup_function():
    _buckets.clear()


def test_permette_richieste_sotto_limite():
    for _ in range(_MAX - 1):
        check_rate_limit("utente_1")  # non deve sollevare eccezioni


def test_blocca_al_limite():
    for _ in range(_MAX):
        check_rate_limit("utente_2")
    with pytest.raises(HTTPException) as exc:
        check_rate_limit("utente_2")
    assert exc.value.status_code == 429


def test_utenti_diversi_sono_indipendenti():
    for _ in range(_MAX):
        check_rate_limit("utente_A")
    # utente_B non deve essere bloccato
    check_rate_limit("utente_B")


def test_finestra_scaduta_resetta_contatore():
    from datetime import datetime, timedelta, UTC

    user = "utente_scaduto"
    # Inserisce timestamp vecchi (fuori finestra)
    old_time = datetime.now(UTC) - timedelta(seconds=_WINDOW + 1)
    _buckets[user] = [old_time] * _MAX

    # Deve passare perché i vecchi timestamp sono scaduti
    check_rate_limit(user)
    assert len(_buckets[user]) == 1


def test_messaggio_errore_contiene_limite():
    for _ in range(_MAX):
        check_rate_limit("utente_msg")
    with pytest.raises(HTTPException) as exc:
        check_rate_limit("utente_msg")
    assert str(_MAX) in exc.value.detail
