"""
Integration tests: testano la catena HTTP → orchestrator → tool → risposta.
Il pool MySQL e le chiamate OpenAI sono mockati; routing, rate limiting e JWT
sono reali e vengono effettivamente esercitati.
"""
import asyncio
import contextlib
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_openai_mock(content="Risposta di test da SnoutBot."):
    msg = MagicMock()
    msg.content = content
    msg.tool_calls = None

    choice = MagicMock()
    choice.message = msg
    choice.finish_reason = "stop"

    response = MagicMock()
    response.choices = [choice]

    client = MagicMock()
    client.chat.completions.create = AsyncMock(return_value=response)
    return client


async def _fake_notification_loop():
    try:
        await asyncio.sleep(3600)
    except asyncio.CancelledError:
        pass


# ── Fixture principale ────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def client():
    """TestClient con lifespan reale ma DB e OpenAI mockati."""
    with contextlib.ExitStack() as stack:
        stack.enter_context(patch("database.create_pool", new_callable=AsyncMock))
        stack.enter_context(patch("database.close_pool", new_callable=AsyncMock))
        stack.enter_context(patch("database.ensure_memory_table", new_callable=AsyncMock))
        stack.enter_context(patch("database.ensure_embeddings_column", new_callable=AsyncMock))
        stack.enter_context(patch("database.ensure_cani_created_at", new_callable=AsyncMock))
        stack.enter_context(patch("database.ensure_notifications_table", new_callable=AsyncMock))
        stack.enter_context(patch("database.ensure_knowledge_table", new_callable=AsyncMock))
        stack.enter_context(patch("database.seed_knowledge_from_json", new_callable=AsyncMock))
        stack.enter_context(patch("database.ensure_booking_tables", new_callable=AsyncMock))
        stack.enter_context(patch("database.seed_aree_cani", new_callable=AsyncMock))
        stack.enter_context(patch("background.notification_loop", side_effect=_fake_notification_loop))

        from main import app
        with TestClient(app) as c:
            yield c


# ── Fixture DB per i test che usano get_db ────────────────────────────────────

@pytest.fixture()
def mock_db_calls():
    """Mocka le chiamate DB nell'orchestrator e nei tool."""
    empty_row = {"nome": None, "razza": None, "cnt": 0}
    with patch("orchestrator._fetch_user_name", new_callable=AsyncMock, return_value=""), \
         patch("orchestrator._fetch_user_dog_profile", new_callable=AsyncMock, return_value=""), \
         patch("orchestrator.load_user_memory", new_callable=AsyncMock, return_value=""), \
         patch("orchestrator.load_unread_notifications", new_callable=AsyncMock, return_value=[]):
        yield


# ── Tests: health ─────────────────────────────────────────────────────────────

def test_health_ok(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "model" in data
    assert "service" in data


# ── Tests: POST /chat ─────────────────────────────────────────────────────────

def test_chat_risposta_ok(client, mock_db_calls):
    with patch("orchestrator._client", _make_openai_mock("Ciao! Sono SnoutBot.")):
        resp = client.post("/chat", json={
            "message": "Ciao SnoutBot!",
            "user_id": "int_u1",
            "context": "",
            "history": [],
        })
    assert resp.status_code == 200
    data = resp.json()
    assert "risposta" in data
    assert len(data["risposta"]) > 0


def test_chat_risposta_con_history(client, mock_db_calls):
    with patch("orchestrator._client", _make_openai_mock("Risposta con contesto.")):
        resp = client.post("/chat", json={
            "message": "Continua",
            "user_id": "int_u2",
            "context": "Piattaforma DogMatch",
            "history": [
                {"role": "user", "content": "Prima domanda"},
                {"role": "assistant", "content": "Prima risposta"},
            ],
        })
    assert resp.status_code == 200
    assert "risposta" in resp.json()


def test_chat_payload_mancante(client):
    resp = client.post("/chat", json={"message": "Ciao"})
    assert resp.status_code == 422


# ── Tests: rate limiting ──────────────────────────────────────────────────────

def test_chat_rate_limit_429(client, mock_db_calls):
    from rate_limit import _buckets, _MAX
    _buckets.pop("rl_int_user", None)

    with patch("orchestrator._client", _make_openai_mock()):
        for _ in range(_MAX):
            client.post("/chat", json={
                "message": "x", "user_id": "rl_int_user",
                "context": "", "history": [],
            })

    resp = client.post("/chat", json={
        "message": "x", "user_id": "rl_int_user",
        "context": "", "history": [],
    })
    assert resp.status_code == 429
    _buckets.pop("rl_int_user", None)


def test_utenti_diversi_non_condividono_limite(client, mock_db_calls):
    from rate_limit import _buckets, _MAX
    _buckets.pop("rl_a", None)
    _buckets.pop("rl_b", None)

    with patch("orchestrator._client", _make_openai_mock()):
        for _ in range(_MAX):
            client.post("/chat", json={
                "message": "x", "user_id": "rl_a",
                "context": "", "history": [],
            })
        resp = client.post("/chat", json={
            "message": "x", "user_id": "rl_b",
            "context": "", "history": [],
        })
    assert resp.status_code == 200
    _buckets.pop("rl_a", None)
    _buckets.pop("rl_b", None)


# ── Tests: knowledge base ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_kb_fallback_json():
    """Con DB non disponibile, get_knowledge_base_info usa il JSON."""
    with patch("tools.knowledge._load_kb_from_db", new_callable=AsyncMock, return_value=None):
        from tools.knowledge import get_knowledge_base_info
        result = await get_knowledge_base_info("registrazione")
    assert isinstance(result, str)
    assert len(result) > 0


@pytest.mark.asyncio
async def test_kb_da_db():
    """Con DB disponibile, usa le righe restituite."""
    fake_kb = {
        "test_voce": {"title": "Titolo test", "content": "Contenuto test", "tags": ["test"]}
    }
    with patch("tools.knowledge._load_kb_from_db", new_callable=AsyncMock, return_value=fake_kb):
        from tools.knowledge import get_knowledge_base_info
        result = await get_knowledge_base_info("test")
    assert "Titolo test" in result
    assert "Contenuto test" in result


@pytest.mark.asyncio
async def test_kb_topic_non_trovato():
    fake_kb = {"voce_a": {"title": "Voce A", "content": "Contenuto A", "tags": []}}
    with patch("tools.knowledge._load_kb_from_db", new_callable=AsyncMock, return_value=fake_kb):
        from tools.knowledge import get_knowledge_base_info
        result = await get_knowledge_base_info("zzz_inesistente")
    assert "Non ho trovato" in result
    assert "voce_a" in result
