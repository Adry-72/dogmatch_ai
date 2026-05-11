import logging
from tools.search_dogs import search_dogs_semantic
from tools.profile import analyze_user_profile, update_user_profile
from tools.knowledge import get_knowledge_base_info
from tools.memory import save_memory, save_reminder, clear_reminder
from tools.moderation import moderation_flag

logger = logging.getLogger(__name__)

_TOOL_MAP = {
    "search_dogs_semantic": lambda inp, uid: search_dogs_semantic(
        query=inp["query"],
        filters=inp.get("filters"),
    ),
    "analyze_user_profile": lambda inp, uid: analyze_user_profile(
        user_id=inp["user_id"],
    ),
    "get_knowledge_base_info": lambda inp, uid: get_knowledge_base_info(
        topic=inp["topic"],
    ),
    "update_user_profile": lambda inp, uid: update_user_profile(
        user_id=inp.get("user_id", uid),
        field=inp["field"],
        value=inp["value"],
    ),
    "save_memory": lambda inp, uid: save_memory(
        user_id=uid,
        chiave=inp["chiave"],
        valore=inp["valore"],
    ),
    "save_reminder": lambda inp, uid: save_reminder(
        user_id=uid,
        id=inp["id"],
        testo=inp["testo"],
    ),
    "clear_reminder": lambda inp, uid: clear_reminder(
        user_id=uid,
        id=inp["id"],
    ),
    "moderation_flag": lambda inp, uid: moderation_flag(
        content=inp["content"],
        reason=inp["reason"],
        user_id=uid,
    ),
}


async def execute_tool(name: str, tool_input: dict, user_id: str) -> str:
    handler = _TOOL_MAP.get(name)
    if handler is None:
        logger.warning("Tool '%s' non riconosciuto.", name)
        return f"Strumento '{name}' non disponibile."

    try:
        logger.debug("Esecuzione tool '%s' con input: %s", name, tool_input)
        result = await handler(tool_input, user_id)
        return result
    except KeyError as e:
        logger.error("Parametro mancante nel tool '%s': %s", name, e)
        return f"Parametro mancante per {name}: {e}."
    except Exception as e:
        logger.error("Errore nel tool '%s': %s", name, e, exc_info=True)
        return f"Errore durante l'esecuzione di {name}. Riprova."
