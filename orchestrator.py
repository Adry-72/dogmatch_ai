import asyncio
import json
import logging
from openai import AsyncOpenAI
from config import settings
from database import get_db
from models import ChatRequest
from tools.definitions import TOOLS
from tools.executor import execute_tool
from tools.memory import load_user_memory

logger = logging.getLogger(__name__)

_client = AsyncOpenAI(api_key=settings.openai_api_key)

BOT_IDENTITY = (
    "Il tuo nome è SnoutBot, l'assistente AI di DogMatch. "
    "Presentati sempre come SnoutBot quando ti viene chiesto chi sei."
)


async def _fetch_user_name(user_id: str) -> str:
    async with get_db() as cur:
        await cur.execute("SELECT nome FROM utenti WHERE id = %s", (user_id,))
        row = await cur.fetchone()
    return row["nome"] if row and row.get("nome") else ""


async def get_ai_response(request: ChatRequest) -> str:
    user_name, memory = await asyncio.gather(
        _fetch_user_name(request.user_id),
        load_user_memory(request.user_id),
    )

    parts = [request.context, BOT_IDENTITY]
    if user_name:
        parts.append(f"Stai parlando con {user_name}. Usane il nome nelle risposte.")
    if memory:
        parts.append(memory)

    messages = [{"role": "system", "content": "\n\n".join(parts)}]
    for h in request.history:
        messages.append({"role": h.role, "content": h.content})
    messages.append({"role": "user", "content": request.message})

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
                result = await execute_tool(
                    tool_call.function.name, tool_input, request.user_id
                )
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": result,
                    }
                )

        elif choice.finish_reason == "length":
            return message.content or "Risposta troncata per lunghezza. Riprova con una domanda più specifica."
        else:
            logger.warning("finish_reason inatteso: %s", choice.finish_reason)
            break

    return "Mi dispiace, non sono riuscito a elaborare la risposta in questo momento. Riprova."
