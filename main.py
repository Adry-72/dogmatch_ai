import asyncio
import json
import logging
from contextlib import asynccontextmanager
from typing import Optional

import jwt
from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from config import settings
from models import ChatRequest, ChatResponse
from orchestrator import get_ai_response, get_ai_response_stream
from pathlib import Path
from database import (
    create_pool, close_pool,
    ensure_memory_table, ensure_embeddings_column,
    ensure_cani_created_at, ensure_notifications_table,
    ensure_knowledge_table, seed_knowledge_from_json,
    ensure_booking_tables, seed_aree_cani,
)
from rate_limit import check_rate_limit
from background import notification_loop

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not settings.jwt_secret:
        logger.warning("JWT_SECRET non configurato — autenticazione disabilitata (solo sviluppo).")
    await create_pool()
    await ensure_memory_table()
    await ensure_embeddings_column()
    await ensure_cani_created_at()
    await ensure_notifications_table()
    await ensure_knowledge_table()
    await seed_knowledge_from_json(Path(__file__).parent / "knowledge_base.json")
    await ensure_booking_tables()
    await seed_aree_cani()
    bg_task = asyncio.create_task(notification_loop())
    logger.info("Database pool e notification scanner inizializzati.")
    yield
    bg_task.cancel()
    try:
        await bg_task
    except asyncio.CancelledError:
        pass
    await close_pool()
    logger.info("Database pool chiuso.")


app = FastAPI(
    title="DogMatch AI Service",
    description="SnoutBot — Assistente AI per la piattaforma DogMatch",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


def _verify_jwt(authorization: Optional[str]) -> None:
    if not settings.jwt_secret:
        return
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Token di autenticazione mancante.")
    token = authorization.removeprefix("Bearer ").strip()
    try:
        jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token scaduto.")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=403, detail="Token non valido.")


@app.get("/health")
async def health():
    return {"status": "ok", "service": "DogMatch AI", "model": settings.model}


@app.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    authorization: Optional[str] = Header(default=None),
):
    _verify_jwt(authorization)
    check_rate_limit(request.user_id)
    try:
        risposta = await get_ai_response(request)
        return ChatResponse(risposta=risposta)
    except Exception as e:
        logger.error("Errore generazione risposta AI: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Errore interno del servizio AI.")


from pydantic import BaseModel as _BaseModel


class KnowledgeEntry(_BaseModel):
    chiave: str
    titolo: str
    contenuto: str
    tags: list[str] = []


@app.post("/admin/knowledge", status_code=201)
async def upsert_knowledge(
    entry: KnowledgeEntry,
    authorization: Optional[str] = Header(default=None),
):
    _verify_jwt(authorization)
    import json as _json
    from database import get_db
    async with get_db() as cur:
        await cur.execute(
            """INSERT INTO ai_knowledge_base (chiave, titolo, contenuto, tags)
               VALUES (%s, %s, %s, %s)
               ON DUPLICATE KEY UPDATE
                 titolo=VALUES(titolo), contenuto=VALUES(contenuto), tags=VALUES(tags)""",
            (entry.chiave, entry.titolo, entry.contenuto, _json.dumps(entry.tags)),
        )
    logger.info("Knowledge base: voce '%s' aggiornata.", entry.chiave)
    return {"status": "ok", "chiave": entry.chiave}


@app.post("/chat/stream")
async def chat_stream(
    request: ChatRequest,
    authorization: Optional[str] = Header(default=None),
):
    _verify_jwt(authorization)
    check_rate_limit(request.user_id)

    async def event_generator():
        try:
            async for chunk in get_ai_response_stream(request):
                yield chunk
        except Exception as e:
            logger.error("Errore streaming AI: %s", e, exc_info=True)
            yield f"data: {json.dumps({'error': 'Errore interno del servizio AI.'})}\n\n"
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
