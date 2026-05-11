import numpy as np
import pytest
from tools.search_dogs import _build_dog_text, _text_hash, _get_cached, _emb_cache, _MAX_CACHE


# ── _build_dog_text ───────────────────────────────────────────────────────────

def test_build_dog_text_maschio():
    dog = {"razza": "Labrador", "taglia": "Grande", "sesso": "M", "eta": 3, "descrizione": "Molto energico"}
    text = _build_dog_text(dog)
    assert "labrador" in text
    assert "maschio" in text
    assert "grande" in text
    assert "molto energico" in text


def test_build_dog_text_femmina():
    dog = {"razza": "Beagle", "sesso": "F", "eta": 2, "taglia": "Media", "descrizione": ""}
    text = _build_dog_text(dog)
    assert "femmina" in text
    assert "beagle" in text


def test_build_dog_text_campi_mancanti():
    text = _build_dog_text({})
    assert isinstance(text, str)


# ── _text_hash ────────────────────────────────────────────────────────────────

def test_text_hash_deterministico():
    assert _text_hash("cane labrador") == _text_hash("cane labrador")


def test_text_hash_diverso():
    assert _text_hash("cane A") != _text_hash("cane B")


def test_text_hash_lunghezza():
    assert len(_text_hash("qualsiasi testo")) == 64


# ── LRU cache ─────────────────────────────────────────────────────────────────

def test_cache_hit_stesso_hash():
    _emb_cache.clear()
    emb = np.array([1.0, 2.0, 3.0], dtype=np.float32)
    blob = emb.tobytes()
    h = "hash_abc"

    r1 = _get_cached(1, h, blob)
    r2 = _get_cached(1, h, blob)
    assert np.array_equal(r1, r2)
    assert _emb_cache[1][0] == h


def test_cache_miss_hash_cambiato():
    _emb_cache.clear()
    emb_old = np.array([1.0, 2.0], dtype=np.float32)
    emb_new = np.array([9.0, 8.0], dtype=np.float32)

    _get_cached(1, "hash_old", emb_old.tobytes())
    result = _get_cached(1, "hash_new", emb_new.tobytes())

    assert np.allclose(result, emb_new)
    assert _emb_cache[1][0] == "hash_new"


def test_cache_eviction_lru():
    _emb_cache.clear()
    blob = np.array([1.0], dtype=np.float32).tobytes()

    for i in range(_MAX_CACHE + 10):
        _get_cached(i, f"h{i}", blob)

    assert len(_emb_cache) == _MAX_CACHE


def test_cache_utenti_indipendenti():
    _emb_cache.clear()
    blob_a = np.array([1.0], dtype=np.float32).tobytes()
    blob_b = np.array([2.0], dtype=np.float32).tobytes()

    _get_cached(10, "ha", blob_a)
    _get_cached(20, "hb", blob_b)

    assert 10 in _emb_cache
    assert 20 in _emb_cache
