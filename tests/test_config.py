from config import settings


def test_settings_carica_campi_richiesti():
    assert settings.openai_api_key
    assert settings.db_host
    assert settings.model


def test_cors_origins_e_una_lista():
    assert isinstance(settings.cors_origins, list)
    assert len(settings.cors_origins) >= 1


def test_cors_origins_senza_spazi():
    for origin in settings.cors_origins:
        assert origin == origin.strip()


def test_cors_origins_multipli():
    from config import Settings
    from pydantic_settings import SettingsConfigDict

    class TestSettings(Settings):
        model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    s = TestSettings(
        openai_api_key="test",
        allowed_origins="http://localhost:3000,https://example.com",
    )
    assert len(s.cors_origins) == 2
    assert "https://example.com" in s.cors_origins


def test_max_tokens_positivo():
    assert settings.max_tokens > 0


def test_max_tool_iterations_positivo():
    assert settings.max_tool_iterations > 0
