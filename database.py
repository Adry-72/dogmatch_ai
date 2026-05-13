import logging
import aiomysql
from contextlib import asynccontextmanager
from typing import Optional
from config import settings

logger = logging.getLogger(__name__)

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


async def ensure_cani_created_at() -> None:
    async with get_db() as cur:
        await cur.execute("""
            SELECT COUNT(*) AS cnt
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME   = 'cani'
              AND COLUMN_NAME  = 'creato_at'
        """)
        row = await cur.fetchone()
        if row["cnt"] == 0:
            await cur.execute(
                "ALTER TABLE cani ADD COLUMN creato_at DATETIME DEFAULT CURRENT_TIMESTAMP"
            )
            logger.info("Colonna creato_at aggiunta alla tabella cani.")


async def ensure_notifications_table() -> None:
    async with get_db() as cur:
        await cur.execute("""
            CREATE TABLE IF NOT EXISTS notifiche (
                id        INT AUTO_INCREMENT PRIMARY KEY,
                user_id   VARCHAR(36) NOT NULL,
                cane_id   INT         NOT NULL,
                messaggio TEXT        NOT NULL,
                letta     TINYINT(1)  NOT NULL DEFAULT 0,
                creata_at DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE KEY uq_user_cane (user_id, cane_id),
                INDEX idx_user_letta (user_id, letta)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)


async def ensure_embeddings_column() -> None:
    async with get_db() as cur:
        await cur.execute("""
            SELECT COUNT(*) AS cnt
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME   = 'cani'
              AND COLUMN_NAME  = 'embedding'
        """)
        row = await cur.fetchone()
        if row["cnt"] == 0:
            await cur.execute(
                "ALTER TABLE cani ADD COLUMN embedding MEDIUMBLOB NULL"
            )
            await cur.execute(
                "ALTER TABLE cani ADD COLUMN embedding_hash VARCHAR(64) NULL"
            )
            logger.info("Colonne embedding e embedding_hash aggiunte alla tabella cani.")


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
