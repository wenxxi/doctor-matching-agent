from openai import OpenAI

from app.settings import get_openai_settings


class OpenAIConfigurationError(Exception):
    pass


def get_openai_client() -> OpenAI:
    settings = get_openai_settings()
    if not settings.api_key:
        raise OpenAIConfigurationError("OPENAI_API_KEY is not configured")

    return OpenAI(api_key=settings.api_key)


def get_openai_model() -> str:
    return get_openai_settings().model
