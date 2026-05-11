import asyncio
import json
import logging
import numpy as np
from typing import AsyncGenerator
from openai import AsyncOpenAI
from config import settings
from database import get_db
from models import ChatRequest
from tools.definitions import TOOLS
from tools.executor import execute_tool
from tools.memory import load_user_memory
from tools.notifications import load_unread_notifications
from tools.search_dogs import search_dogs_semantic, _USE_EMBEDDINGS, _encode

logger = logging.getLogger(__name__)

_client = AsyncOpenAI(api_key=settings.openai_api_key)

BOT_IDENTITY = (
    "Il tuo nome è SnoutBot, l'assistente AI di DogMatch. "
    "Presentati sempre come SnoutBot quando ti viene chiesto chi sei."
)

# ── Intent detection ──────────────────────────────────────────────────────────
# Frasi prototipo che rappresentano l'intenzione "cerco un cane compatibile".
# Il centroide dei loro embedding diventa il riferimento per la similarity.
_INTENT_EXAMPLES = [
    "cerco un cane compatibile con il mio",
    "trova cani adatti per il mio cane",
    "suggerisci cani simili al mio",
    "raccomanda un compagno per il mio cane",
    "quali cani si abbinano bene",
    "ho bisogno di un match per il mio cane",
    "il mio cane ha bisogno di un amico",
    "cerca un partner per l'accoppiamento",
    "vorrei trovare un compagno per il mio cane",
    "mi serve un cane con cui giocare",
]

_INTENT_THRESHOLD = 0.35
_intent_centroid = None

if _USE_EMBEDDINGS:
    try:
        _vecs = _encode(_INTENT_EXAMPLES)
        _intent_centroid = _vecs.mean(axis=0)
        _intent_centroid /= (np.linalg.norm(_intent_centroid) or 1e-8)
        logger.info("Intent centroid calcolato su %d esempi.", len(_INTENT_EXAMPLES))
    except Exception as _e:
        logger.warning("Impossibile calcolare intent centroid: %s", _e)

# Keyword fallback per quando sentence-transformers non è disponibile
_SEARCH_STEMS = (
    "cerc", "trov", "match", "accoppi", "compagn", "compatibil",
    "sugger", "consigl", "propon", "raccomand", "amico", "amica",
    "tranquill", "calm", "energic", "vivac", "giocoso", "giocosa",
    "mite", "attiv", "pigr", "sociabil", "timid", "curioso", "curiosa",
    "dolce", "fedel", "affettu",
)


async def _is_dog_search(message: str) -> bool:
    """Rileva se il messaggio è una ricerca/match cani.
    Usa embedding similarity se disponibile, keyword matching come fallback.
    """
    if _USE_EMBEDDINGS and _intent_centroid is not None:
        emb = await asyncio.to_thread(_encode, [message.lower()])
        emb_norm = emb[0] / (np.linalg.norm(emb[0]) or 1e-8)
        score = float(np.dot(emb_norm, _intent_centroid))
        logger.debug("Intent score: %.3f — '%s'", score, message[:60])
        return score >= _INTENT_THRESHOLD
    msg = message.lower()
    return any(stem in msg for stem in _SEARCH_STEMS)


async def _fetch_user_name(user_id: str) -> str:
    async with get_db() as cur:
        await cur.execute("SELECT nome FROM utenti WHERE id = %s", (user_id,))
        row = await cur.fetchone()
    return row["nome"] if row and row.get("nome") else ""


async def _fetch_user_dog_profile(user_id: str) -> str:
    """Restituisce una stringa descrittiva del cane dell'utente, usata per arricchire la query RAG."""
    async with get_db() as cur:
        await cur.execute(
            "SELECT razza, sesso, eta, taglia, descrizione FROM cani WHERE utente_id = %s LIMIT 1",
            (user_id,),
        )
        dog = await cur.fetchone()
    if not dog:
        return ""
    sesso = "maschio" if dog.get("sesso") == "M" else "femmina"
    parts = [
        dog.get("razza", ""),
        sesso,
        f"{dog['eta']} anni" if dog.get("eta") else "",
        dog.get("taglia", ""),
        dog.get("descrizione", ""),
    ]
    return " ".join(p for p in parts if p)


async def _rag_context(message: str, user_id: str) -> str:
    """Pre-fetcha i cani più rilevanti arricchendo la query con il profilo dell'utente."""
    if not await _is_dog_search(message):
        return ""

    profile = await _fetch_user_dog_profile(user_id)
    # Query arricchita: messaggio + profilo del cane dell'utente → re-ranking implicito
    enriched_query = f"{message} {profile}".strip() if profile else message

    try:
        result = await search_dogs_semantic(query=enriched_query)
        if result.startswith("Nessun cane"):
            return ""
        return (
            "--- Cani pre-caricati in base alla richiesta ---\n"
            + result
            + "\n---\n"
            "Questi risultati sono già disponibili nel contesto. "
            "Usali per rispondere direttamente spiegando perché ogni cane potrebbe "
            "essere un buon match, senza chiamare search_dogs_semantic — a meno che "
            "l'utente non richieda filtri specifici (razza, taglia, sesso, età, ecc.)."
        )
    except Exception as exc:
        logger.warning("RAG pre-fetch fallito: %s", exc)
        return ""


def _build_messages(
    request: ChatRequest, user_name: str, memory: str, rag: str, notifications: list[str]
) -> list:
    parts = [request.context, BOT_IDENTITY]
    if user_name:
        parts.append(f"Stai parlando con {user_name}. Usane il nome nelle risposte.")
    if memory:
        parts.append(memory)
    if notifications:
        notif_lines = "\n".join(f"• {n}" for n in notifications)
        parts.append(
            f"--- {len(notifications)} nuova/e notifica/he per questo utente ---\n"
            f"{notif_lines}\n"
            "---\n"
            "Menziona queste notifiche in modo naturale all'inizio della risposta, "
            "prima di rispondere alla domanda dell'utente."
        )
    if rag:
        parts.append(rag)
    messages = [{"role": "system", "content": "\n\n".join(parts)}]
    for h in request.history:
        messages.append({"role": h.role, "content": h.content})
    messages.append({"role": "user", "content": request.message})
    return messages


async def get_ai_response(request: ChatRequest) -> str:
    user_name, memory, rag, notifications = await asyncio.gather(
        _fetch_user_name(request.user_id),
        load_user_memory(request.user_id),
        _rag_context(request.message, request.user_id),
        load_unread_notifications(request.user_id),
    )
    messages = _build_messages(request, user_name, memory, rag, notifications)

    for iteration in range(settings.max_tool_iterations):
        response = await _client.chat.completions.create(
            model=settings.model,
            max_tokens=settings.max_tokens,
            messages=messages,
            tools=TOOLS,
            tool_choice="auto",
        )

        choice = response.choices[0]
        message = choice.message

        logger.debug(
            "Iterazione %d/%d — finish_reason: %s",
            iteration + 1, settings.max_tool_iterations, choice.finish_reason,
        )

        if choice.finish_reason == "stop":
            return message.content or "Non ho informazioni sufficienti per rispondere."

        if choice.finish_reason == "tool_calls":
            messages.append(message)
            for tool_call in message.tool_calls:
                try:
                    tool_input = json.loads(tool_call.function.arguments)
                except json.JSONDecodeError:
                    tool_input = {}
                logger.info("Tool call: %s(%s)", tool_call.function.name, tool_input)
                result = await execute_tool(tool_call.function.name, tool_input, request.user_id)
                messages.append({"role": "tool", "tool_call_id": tool_call.id, "content": result})

        elif choice.finish_reason == "length":
            return message.content or "Risposta troncata per lunghezza. Riprova con una domanda più specifica."
        else:
            logger.warning("finish_reason inatteso: %s", choice.finish_reason)
            break

    return "Mi dispiace, non sono riuscito a elaborare la risposta in questo momento. Riprova."


async def get_ai_response_stream(request: ChatRequest) -> AsyncGenerator[str, None]:
    user_name, memory, rag, notifications = await asyncio.gather(
        _fetch_user_name(request.user_id),
        load_user_memory(request.user_id),
        _rag_context(request.message, request.user_id),
        load_unread_notifications(request.user_id),
    )
    messages = _build_messages(request, user_name, memory, rag, notifications)

    for iteration in range(settings.max_tool_iterations):
        stream = await _client.chat.completions.create(
            model=settings.model,
            max_tokens=settings.max_tokens,
            messages=messages,
            tools=TOOLS,
            tool_choice="auto",
            stream=True,
        )

        full_content = ""
        tool_calls_acc: dict = {}
        finish_reason = None

        async for chunk in stream:
            choice = chunk.choices[0]
            delta = choice.delta
            if choice.finish_reason:
                finish_reason = choice.finish_reason

            if delta.content:
                full_content += delta.content
                yield f"data: {json.dumps({'token': delta.content})}\n\n"

            if delta.tool_calls:
                for tc in delta.tool_calls:
                    idx = tc.index
                    if idx not in tool_calls_acc:
                        tool_calls_acc[idx] = {"id": "", "name": "", "arguments": ""}
                    if tc.id:
                        tool_calls_acc[idx]["id"] = tc.id
                    if tc.function:
                        if tc.function.name:
                            tool_calls_acc[idx]["name"] += tc.function.name
                        if tc.function.arguments:
                            tool_calls_acc[idx]["arguments"] += tc.function.arguments

        if finish_reason == "stop":
            yield "data: [DONE]\n\n"
            return

        if finish_reason == "tool_calls":
            tool_calls = [
                {
                    "id": tool_calls_acc[i]["id"],
                    "type": "function",
                    "function": {
                        "name": tool_calls_acc[i]["name"],
                        "arguments": tool_calls_acc[i]["arguments"],
                    },
                }
                for i in sorted(tool_calls_acc)
            ]
            messages.append({
                "role": "assistant",
                "content": full_content or None,
                "tool_calls": tool_calls,
            })
            for tc in tool_calls:
                try:
                    tool_input = json.loads(tc["function"]["arguments"])
                except json.JSONDecodeError:
                    tool_input = {}
                logger.info("Stream tool call: %s(%s)", tc["function"]["name"], tool_input)
                result = await execute_tool(tc["function"]["name"], tool_input, request.user_id)
                messages.append({"role": "tool", "tool_call_id": tc["id"], "content": result})

        elif finish_reason == "length":
            yield f"data: {json.dumps({'token': ' [risposta troncata]'})}\n\n"
            yield "data: [DONE]\n\n"
            return
        else:
            logger.warning("Stream finish_reason inatteso: %s", finish_reason)
            break

    yield f"data: {json.dumps({'error': 'Numero massimo di iterazioni raggiunto.'})}\n\n"
    yield "data: [DONE]\n\n"
