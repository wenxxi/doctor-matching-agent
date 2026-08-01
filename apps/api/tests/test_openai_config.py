from app.services.openai_client import OpenAIConfigurationError, get_openai_client, get_openai_model
from app.settings import get_openai_settings


def clear_settings_cache() -> None:
    get_openai_settings.cache_clear()


def test_openai_model_defaults_to_gpt4o_mini(monkeypatch):
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    clear_settings_cache()

    assert get_openai_model() == "gpt-4o-mini"


def test_openai_model_can_be_configured(monkeypatch):
    monkeypatch.setenv("OPENAI_MODEL", "gpt-4o-2024-08-06")
    clear_settings_cache()

    assert get_openai_model() == "gpt-4o-2024-08-06"


def test_openai_client_requires_api_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    clear_settings_cache()

    try:
        get_openai_client()
    except OpenAIConfigurationError as exc:
        assert str(exc) == "OPENAI_API_KEY is not configured"
    else:
        raise AssertionError("Expected OpenAIConfigurationError")
