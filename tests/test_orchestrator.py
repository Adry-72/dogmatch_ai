import pytest
from unittest.mock import patch
from models import ChatRequest, HistoryMessage


def _req(**kwargs) -> ChatRequest:
    return ChatRequest(**{"message": "Ciao", "user_id": "u1", "context": "ctx", "history": [], **kwargs})


# ── _build_messages ───────────────────────────────────────────────────────────

def test_build_messages_struttura_base():
    from orchestrator import _build_messages
    msgs = _build_messages(_req(), user_name="", memory="", rag="", notifications=[])
    assert msgs[0]["role"] == "system"
    assert msgs[-1]["role"] == "user"
    assert msgs[-1]["content"] == "Ciao"


def test_build_messages_nome_nel_prompt():
    from orchestrator import _build_messages
    msgs = _build_messages(_req(), user_name="Mario", memory="", rag="", notifications=[])
    assert "Mario" in msgs[0]["content"]


def test_build_messages_notifica_nel_prompt():
    from orchestrator import _build_messages
    msgs = _build_messages(_req(), user_name="", memory="", rag="", notifications=["Rex è arrivato!"])
    assert "Rex è arrivato!" in msgs[0]["content"]


def test_build_messages_piu_notifiche():
    from orchestrator import _build_messages
    notifiche = ["Cane A disponibile", "Cane B disponibile"]
    msgs = _build_messages(_req(), user_name="", memory="", rag="", notifications=notifiche)
    system = msgs[0]["content"]
    assert "Cane A disponibile" in system
    assert "Cane B disponibile" in system


def test_build_messages_history_nel_giusto_ordine():
    from orchestrator import _build_messages
    history = [
        HistoryMessage(role="user", content="prima domanda"),
        HistoryMessage(role="assistant", content="prima risposta"),
    ]
    msgs = _build_messages(_req(history=history), user_name="", memory="", rag="", notifications=[])
    assert len(msgs) == 4  # system + 2 history + user message
    assert msgs[1]["content"] == "prima domanda"
    assert msgs[2]["content"] == "prima risposta"


def test_build_messages_rag_nel_prompt():
    from orchestrator import _build_messages
    msgs = _build_messages(_req(), user_name="", memory="", rag="Rex - Labrador 80%", notifications=[])
    assert "Rex - Labrador 80%" in msgs[0]["content"]


def test_build_messages_notifica_prima_di_rag():
    """Le notifiche devono apparire prima del RAG nel system prompt."""
    from orchestrator import _build_messages
    msgs = _build_messages(
        _req(), user_name="", memory="",
        rag="--- Cani pre-caricati ---",
        notifications=["Nuovo cane!"],
    )
    content = msgs[0]["content"]
    assert content.index("Nuovo cane!") < content.index("Cani pre-caricati")


# ── _is_dog_search (keyword fallback) ────────────────────────────────────────

@pytest.mark.asyncio
async def test_is_dog_search_keyword_cerca():
    with patch("orchestrator._USE_EMBEDDINGS", False):
        from orchestrator import _is_dog_search
        assert await _is_dog_search("cerco un cane compatibile")


@pytest.mark.asyncio
async def test_is_dog_search_keyword_amico():
    with patch("orchestrator._USE_EMBEDDINGS", False):
        from orchestrator import _is_dog_search
        assert await _is_dog_search("il mio cane ha bisogno di un amico")


@pytest.mark.asyncio
async def test_is_dog_search_keyword_tranquillo():
    with patch("orchestrator._USE_EMBEDDINGS", False):
        from orchestrator import _is_dog_search
        assert await _is_dog_search("voglio un cane tranquillo")


@pytest.mark.asyncio
async def test_is_dog_search_no_match():
    with patch("orchestrator._USE_EMBEDDINGS", False):
        from orchestrator import _is_dog_search
        assert not await _is_dog_search("quali sono le norme sul microchip?")


@pytest.mark.asyncio
async def test_is_dog_search_domanda_veterinario():
    with patch("orchestrator._USE_EMBEDDINGS", False):
        from orchestrator import _is_dog_search
        assert not await _is_dog_search("quando devo fare il vaccino antirabbico?")
