import json
import logging
import aiomysql
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional
from config import settings

logger = logging.getLogger(__name__)

_pool: Optional[aiomysql.Pool] = None
# ciao

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
            CREATE TABLE IF NOT EXISTS ai_notifiche (
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


async def ensure_knowledge_table() -> None:
    async with get_db() as cur:
        await cur.execute("""
            CREATE TABLE IF NOT EXISTS ai_knowledge_base (
                chiave        VARCHAR(100)  NOT NULL PRIMARY KEY,
                titolo        VARCHAR(255)  NOT NULL,
                contenuto     LONGTEXT      NOT NULL,
                tags          JSON          NULL,
                aggiornato_at DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP
                                            ON UPDATE CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)


async def seed_knowledge_from_json(json_path: Path) -> None:
    async with get_db() as cur:
        await cur.execute("SELECT COUNT(*) AS cnt FROM ai_knowledge_base")
        row = await cur.fetchone()
        if row["cnt"] > 0:
            return
        with open(json_path, "r", encoding="utf-8") as f:
            kb = json.load(f)
        for chiave, entry in kb.items():
            await cur.execute(
                """INSERT INTO ai_knowledge_base (chiave, titolo, contenuto, tags)
                   VALUES (%s, %s, %s, %s)
                   ON DUPLICATE KEY UPDATE
                     titolo=VALUES(titolo), contenuto=VALUES(contenuto), tags=VALUES(tags)""",
                (chiave, entry.get("title", chiave), entry.get("content", ""),
                 json.dumps(entry.get("tags", []))),
            )
        logger.info("Knowledge base: %d voci importate da JSON.", len(kb))


async def ensure_booking_tables() -> None:
    async with get_db() as cur:
        await cur.execute("""
            CREATE TABLE IF NOT EXISTS aree_cani (
                id                  INT AUTO_INCREMENT PRIMARY KEY,
                nome                VARCHAR(150) NOT NULL,
                citta               VARCHAR(100) NOT NULL,
                provincia           VARCHAR(5)   NOT NULL,
                separazione_taglie  TINYINT(1)   NOT NULL DEFAULT 0
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
        await cur.execute("""
            CREATE TABLE IF NOT EXISTS prenotazioni_area (
                id        INT AUTO_INCREMENT PRIMARY KEY,
                codice    VARCHAR(15)  NOT NULL UNIQUE,
                user_id   VARCHAR(36)  NOT NULL,
                area_id   INT          NOT NULL,
                data_ora  DATETIME     NOT NULL,
                stato     ENUM('attiva','cancellata') NOT NULL DEFAULT 'attiva',
                creata_at DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_area_data (area_id, data_ora),
                INDEX idx_user_stato (user_id, stato)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)


async def seed_aree_cani() -> None:
    async with get_db() as cur:
        await cur.execute("SELECT COUNT(*) AS cnt FROM aree_cani")
        row = await cur.fetchone()
        if row["cnt"] > 0:
            return
        aree = [
            ("Area Cani Parco Sempione", "Milano",  "MI", 1),
            ("Dog Park Navigli",         "Milano",  "MI", 0),
            ("Area Cani Villa Borghese", "Roma",    "RM", 1),
            ("Dog Park Valentino",       "Torino",  "TO", 0),
            ("Area Cani Parco Virgiliano","Napoli", "NA", 0),
            ("Dog Area Cascine",         "Firenze", "FI", 1),
        ]
        await cur.executemany(
            "INSERT INTO aree_cani (nome, citta, provincia, separazione_taglie) VALUES (%s, %s, %s, %s)",
            aree,
        )
        logger.info("Aree cani: %d aree certificate inserite.", len(aree))


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
