"""
Pre-compute and persist embeddings for all dogs in the database.

Run once (or after bulk dog insertions):
    python scripts/compute_embeddings.py

Skips dogs whose embedding is already up to date.
Requires sentence-transformers to be installed.
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import numpy as np
from sentence_transformers import SentenceTransformer

from database import create_pool, close_pool, get_db, ensure_embeddings_column
from tools.search_dogs import _build_dog_text, _text_hash

BATCH_SIZE = 32


async def main() -> None:
    model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
    await create_pool()
    await ensure_embeddings_column()

    async with get_db() as cur:
        await cur.execute("""
            SELECT id, razza, sesso, eta, taglia, descrizione, info_sanitarie, embedding_hash
            FROM cani
        """)
        dogs = await cur.fetchall()

    print(f"Trovati {len(dogs)} cani nel database.")

    to_process = []
    for dog in dogs:
        text = _build_dog_text(dog)
        h = _text_hash(text)
        if dog.get("embedding_hash") != h:
            to_process.append((dog["id"], text, h))

    if not to_process:
        print("Tutti gli embedding sono già aggiornati.")
        await close_pool()
        return

    print(f"Da aggiornare: {len(to_process)} cani.")

    updated = 0
    for i in range(0, len(to_process), BATCH_SIZE):
        batch = to_process[i : i + BATCH_SIZE]
        texts = [t for _, t, _ in batch]
        embeddings = model.encode(texts, convert_to_numpy=True, show_progress_bar=False)

        async with get_db() as cur:
            for (dog_id, _, h), emb in zip(batch, embeddings):
                blob = emb.astype(np.float32).tobytes()
                await cur.execute(
                    "UPDATE cani SET embedding = %s, embedding_hash = %s WHERE id = %s",
                    (blob, h, dog_id),
                )
                updated += 1

        print(f"  Aggiornati {updated}/{len(to_process)}...")

    await close_pool()
    print(f"\nCompletato! Embedding aggiornati: {updated}.")


if __name__ == "__main__":
    asyncio.run(main())
