import asyncio
import logging
from typing import Optional

from database import get_db

logger = logging.getLogger(__name__)

# Try sentence-transformers for true multilingual semantic search;
# fall back to TF-IDF if not installed.
try:
    from sentence_transformers import SentenceTransformer
    import numpy as np

    _st_model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
    _USE_EMBEDDINGS = True
    logger.info("Sentence-transformers caricato: ricerca semantica attiva.")
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


def _similarity_embeddings(query: str, texts: list) -> list:
    all_texts = [query] + texts
    embeddings = _st_model.encode(all_texts, convert_to_numpy=True)
    q = embeddings[0:1]
    docs = embeddings[1:]
    norms = np.linalg.norm(docs, axis=1, keepdims=True)
    norms = np.where(norms == 0, 1e-8, norms)
    q_norm = q / (np.linalg.norm(q) or 1e-8)
    return (docs / norms @ q_norm.T).flatten().tolist()


def _similarity_tfidf(query: str, texts: list) -> list:
    if not texts:
        return []
    vectorizer = TfidfVectorizer(analyzer="word", ngram_range=(1, 2))
    try:
        matrix = vectorizer.fit_transform([query] + texts)
        return cosine_similarity(matrix[0:1], matrix[1:]).flatten().tolist()
    except Exception:
        return [0.0] * len(texts)


async def search_dogs_semantic(query: str, filters: Optional[dict] = None) -> str:
    filters = filters or {}

    sql = """
        SELECT c.id, c.nome, c.razza, c.sesso, c.eta, c.taglia,
               c.descrizione, c.info_sanitarie, c.is_verificato,
               c.disponibilita_riproduttiva,
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

    sql += " LIMIT 100"

    async with get_db() as cursor:
        await cursor.execute(sql, params)
        dogs = await cursor.fetchall()

    if not dogs:
        return "Nessun cane trovato nel database con i criteri specificati. Prova a rimuovere alcuni filtri."

    texts = [_build_dog_text(d) for d in dogs]

    if _USE_EMBEDDINGS:
        scores = await asyncio.to_thread(_similarity_embeddings, query.lower(), texts)
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
