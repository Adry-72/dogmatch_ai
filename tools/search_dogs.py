import asyncio
import hashlib
import logging
from collections import OrderedDict
from typing import Optional

from database import get_db

# LRU cache in-memory: {dog_id: (hash, ndarray)}
_MAX_CACHE = 500
_emb_cache: OrderedDict = OrderedDict()

logger = logging.getLogger(__name__)

try:
    from sentence_transformers import SentenceTransformer
    import numpy as np

    _st_model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
    _USE_EMBEDDINGS = True
    logger.info("Sentence-transformers caricato: ricerca semantica con persistenza attiva.")
except ImportError:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
    import numpy as np

    _st_model = None
    _USE_EMBEDDINGS = False
    logger.info("sentence-transformers non installato: uso TF-IDF come fallback.")


def _build_dog_text(dog: dict) -> str:
    sesso = "maschio" if dog.get("sesso") == "M" else "femmina"
    parts = [
        dog.get("razza", ""),
        dog.get("taglia", ""),
        sesso,
        str(dog.get("eta", "")),
        dog.get("descrizione", ""),
        dog.get("info_sanitarie", ""),
    ]
    return " ".join(p for p in parts if p).lower()


def _text_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _get_cached(dog_id: int, h: str, blob: bytes) -> "np.ndarray":
    entry = _emb_cache.get(dog_id)
    if entry and entry[0] == h:
        _emb_cache.move_to_end(dog_id)
        return entry[1]
    emb = np.frombuffer(blob, dtype=np.float32).copy()
    _emb_cache[dog_id] = (h, emb)
    if len(_emb_cache) > _MAX_CACHE:
        _emb_cache.popitem(last=False)
    return emb


def _encode(texts: list) -> "np.ndarray":
    return _st_model.encode(texts, convert_to_numpy=True)


def _cosine_scores(query_emb: "np.ndarray", dog_matrix: "np.ndarray") -> list:
    q = query_emb / (np.linalg.norm(query_emb) or 1e-8)
    norms = np.linalg.norm(dog_matrix, axis=1, keepdims=True)
    norms = np.where(norms == 0, 1e-8, norms)
    return (dog_matrix / norms @ q).tolist()


def _similarity_tfidf(query: str, texts: list) -> list:
    if not texts:
        return []
    vectorizer = TfidfVectorizer(analyzer="word", ngram_range=(1, 2))
    try:
        matrix = vectorizer.fit_transform([query] + texts)
        return cosine_similarity(matrix[0:1], matrix[1:]).flatten().tolist()
    except Exception:
        return [0.0] * len(texts)


async def _save_embeddings_batch(items: list) -> None:
    """Persist computed embeddings to DB. items = [(dog_id, hash, embedding)]"""
    try:
        async with get_db() as cur:
            for dog_id, h, emb in items:
                blob = emb.astype(np.float32).tobytes()
                await cur.execute(
                    "UPDATE cani SET embedding = %s, embedding_hash = %s WHERE id = %s",
                    (blob, h, dog_id),
                )
        logger.info("Salvati %d embedding nel database.", len(items))
    except Exception as exc:
        logger.warning("Errore salvataggio embedding: %s", exc)


async def search_dogs_semantic(query: str, filters: Optional[dict] = None) -> str:
    filters = filters or {}

    sql = """
        SELECT c.id, c.nome, c.razza, c.sesso, c.eta, c.taglia,
               c.descrizione, c.info_sanitarie, c.is_verificato,
               c.disponibilita_riproduttiva, c.embedding, c.embedding_hash,
               u.nome AS proprietario_nome, u.provincia
        FROM cani c
        JOIN utenti u ON c.utente_id = u.id
        WHERE 1=1
    """
    params = []

    if filters.get("taglia"):
        sql += " AND c.taglia = %s"
        params.append(filters["taglia"])
    if filters.get("sesso"):
        sql += " AND c.sesso = %s"
        params.append(filters["sesso"])
    if filters.get("razza"):
        sql += " AND c.razza LIKE %s"
        params.append(f"%{filters['razza']}%")
    if filters.get("eta_max") is not None:
        sql += " AND c.eta <= %s"
        params.append(int(filters["eta_max"]))
    if filters.get("disponibile_riproduzione") is not None:
        sql += " AND c.disponibilita_riproduttiva = %s"
        params.append(1 if filters["disponibile_riproduzione"] else 0)

    sql += " LIMIT 200"

    async with get_db() as cursor:
        await cursor.execute(sql, params)
        dogs = await cursor.fetchall()

    if not dogs:
        return "Nessun cane trovato nel database con i criteri specificati. Prova a rimuovere alcuni filtri."

    texts = [_build_dog_text(d) for d in dogs]

    if _USE_EMBEDDINGS:
        # Compute query embedding
        query_emb = await asyncio.to_thread(_encode, [query.lower()])
        query_emb = query_emb[0]

        # Separate dogs with valid cached embeddings from those needing computation
        cached, to_compute = [], []
        for dog, text in zip(dogs, texts):
            h = _text_hash(text)
            blob = dog.get("embedding")
            if blob and dog.get("embedding_hash") == h:
                emb = _get_cached(dog["id"], h, blob)
                cached.append((dog, emb))
            else:
                to_compute.append((dog, text, h))

        # Batch-encode only the dogs that need it
        new_embeddings = []
        if to_compute:
            new_texts = [t for _, t, _ in to_compute]
            computed = await asyncio.to_thread(_encode, new_texts)
            to_save = []
            for (dog, _, h), emb in zip(to_compute, computed):
                new_embeddings.append((dog, emb))
                to_save.append((dog["id"], h, emb))
            asyncio.create_task(_save_embeddings_batch(to_save))

        # Rebuild ordered list matching original `dogs` order
        dog_emb_map = {d["id"]: emb for d, emb in cached}
        dog_emb_map.update({d["id"]: emb for d, emb in new_embeddings})
        dog_embeddings = [dog_emb_map[d["id"]] for d in dogs]

        dog_matrix = np.stack(dog_embeddings)
        scores = _cosine_scores(query_emb, dog_matrix)
    else:
        scores = await asyncio.to_thread(_similarity_tfidf, query.lower(), texts)

    ranked = sorted(zip(dogs, scores), key=lambda x: x[1], reverse=True)[:5]

    lines = [f"Trovati i cani più compatibili con '{query}':\n"]
    for i, (dog, score) in enumerate(ranked, 1):
        verified = "✓ Verificato" if dog.get("is_verificato") else ""
        riprod = "| Disponibile accoppiamento" if dog.get("disponibilita_riproduttiva") else ""
        desc = (dog.get("descrizione") or "Nessuna descrizione")[:120]
        sesso_str = "M" if dog.get("sesso") == "M" else "F"
        lines.append(
            f"{i}. **{dog['nome']}** ({dog['razza']}, {sesso_str}, {dog['eta']} anni, {dog['taglia']}) "
            f"— {dog.get('provincia') or 'n/d'} "
            f"[Proprietario: {dog.get('proprietario_nome') or 'n/d'}] {verified} {riprod}\n"
            f"   \"{desc}\"\n"
            f"   Affinità: {int(score * 100)}%"
        )

    return "\n".join(lines)
