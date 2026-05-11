import logging
from contextlib import asynccontextmanager
from typing import Optional

import jwt
from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from models import ChatRequest, ChatResponse
from orchestrator import get_ai_response
from database import create_pool, close_pool, ensure_memory_table

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
    logger.info("Database pool inizializzato.")
    yield
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
    try:
        risposta = await get_ai_response(request)
        return ChatResponse(risposta=risposta)
    except Exception as e:
        logger.error("Errore generazione risposta AI: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Errore interno del servizio AI.")
