import json
import logging
from difflib import SequenceMatcher
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_KB: Optional[dict] = None
_KB_PATH = Path(__file__).parent.parent / "knowledge_base.json"


def _load_kb() -> dict:
    global _KB
    if _KB is None:
        with open(_KB_PATH, "r", encoding="utf-8") as f:
            _KB = json.load(f)
    return _KB


def _relevance_score(topic: str, key: str, entry: dict) -> float:
    title = entry.get("title", "").lower()
    tags = " ".join(entry.get("tags", [])).lower()
    combined = f"{key} {title} {tags}"

    if topic in combined:
        return 1.0
    # Check individual words for partial matches
    words = topic.split()
    word_matches = sum(1 for w in words if w in combined and len(w) > 3)
    if word_matches:
        return 0.6 + (word_matches / len(words)) * 0.3

    return SequenceMatcher(None, topic, combined).ratio() * 0.4


async def get_knowledge_base_info(topic: str) -> str:
    try:
        kb = _load_kb()
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
