import aiomysql
from contextlib import asynccontextmanager
from typing import Optional
from config import settings

_pool: Optional[aiomysql.Pool] = None


async def create_pool() -> None:
    global _pool
    _pool = await aiomysql.create_pool(
        host=settings.db_host,
        port=settings.db_port,
        user=settings.db_user,
        password=settings.db_password,
        db=settings.db_name,
        charset="utf8mb4",
        autocommit=True,
        minsize=2,
        maxsize=10,
    )


async def close_pool() -> None:
    global _pool
    if _pool:
        _pool.close()
        await _pool.wait_closed()


@asynccontextmanager
async def get_db():
    if _pool is None:
        raise RuntimeError("Database pool not initialized.")
    async with _pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cursor:
            yield cursor


async def ensure_memory_table() -> None:
    async with get_db() as cur:
        await cur.execute("""
            CREATE TABLE IF NOT EXISTS ai_memoria (
                user_id       VARCHAR(36)  NOT NULL,
                chiave        VARCHAR(100) NOT NULL,
                valore        TEXT         NOT NULL,
                aggiornato_at DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
                                           ON UPDATE CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, chiave)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
