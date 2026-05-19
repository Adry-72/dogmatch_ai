import json
import logging
from difflib import SequenceMatcher
from pathlib import Path

logger = logging.getLogger(__name__)

_KB_PATH = Path(__file__).parent.parent / "knowledge_base.json"


def _relevance_score(topic: str, key: str, entry: dict) -> float:
    title = entry.get("title", entry.get("titolo", "")).lower()
    tags_raw = entry.get("tags", [])
    if isinstance(tags_raw, str):
        try:
            tags_raw = json.loads(tags_raw)
        except Exception:
            tags_raw = []
    tags = " ".join(tags_raw).lower()

    if topic in key:
        return 1.0
    if topic in title:
        return 0.95
    if topic in tags:
        return 0.85

    combined = f"{key} {title} {tags}"
    words = topic.split()
    word_matches = sum(1 for w in words if w in combined and len(w) > 3)
    if word_matches:
        return 0.6 + (word_matches / len(words)) * 0.3
    return SequenceMatcher(None, topic, combined).ratio() * 0.4


def _load_kb_json() -> dict:
    with open(_KB_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


async def _load_kb_from_db() -> dict | None:
    try:
        from database import get_db
        async with get_db() as cur:
            await cur.execute("SELECT chiave, titolo, contenuto, tags FROM ai_knowledge_base")
            rows = await cur.fetchall()
        if not rows:
            return None
        kb = {}
        for row in rows:
            tags = row["tags"]
            if isinstance(tags, str):
                try:
                    tags = json.loads(tags)
                except Exception:
                    tags = []
            kb[row["chiave"]] = {
                "title": row["titolo"],
                "content": row["contenuto"],
                "tags": tags or [],
            }
        return kb
    except Exception as exc:
        logger.warning("KB DB non disponibile, fallback a JSON: %s", exc)
        return None


async def get_knowledge_base_info(topic: str) -> str:
    kb = await _load_kb_from_db()
    if kb is None:
        try:
            kb = _load_kb_json()
        except FileNotFoundError:
            logger.error("knowledge_base.json non trovato in %s", _KB_PATH)
            return "La knowledge base non è disponibile al momento. Contatta il supporto DogMatch."

    topic_lower = topic.lower().strip()
    scored = [
        (key, entry, _relevance_score(topic_lower, key, entry))
        for key, entry in kb.items()
    ]
    scored.sort(key=lambda x: x[2], reverse=True)
    top = [x for x in scored[:3] if x[2] > 0.15]

    if not top:
        available = ", ".join(kb.keys())
        return (
            f"Non ho trovato informazioni specifiche su '{topic}'. "
            f"Argomenti disponibili: {available}."
        )

    results = [f"## {entry['title']}\n{entry['content']}" for _, entry, _ in top[:2]]
    return "\n\n---\n\n".join(results)
