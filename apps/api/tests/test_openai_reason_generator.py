from types import SimpleNamespace

import app.services.openai_reason_generator as reason_module
from app.services.concept_extractor import KeywordConceptExtractor
from app.services.doctor_matcher import rank_doctors
from app.services.openai_reason_generator import generate_llm_reasons
from app.settings import get_openai_settings


class FakeResponses:
    def __init__(self, output_text: str | Exception) -> None:
        self.output_text = output_text
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if isinstance(self.output_text, Exception):
            raise self.output_text
        return SimpleNamespace(output_text=self.output_text)


class FakeClient:
    def __init__(self, output_text: str | Exception) -> None:
        self.responses = FakeResponses(output_text)


def clear_settings_cache() -> None:
    get_openai_settings.cache_clear()


def test_generate_llm_reasons_inserts_mocked_reason_and_ignores_unknown_doctor(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    clear_settings_cache()
    concepts = KeywordConceptExtractor().extract_concepts("膝蓋韌帶受傷")
    doctors = rank_doctors(concepts, limit=2)
    first_doctor_id = doctors[0].doctor_id
    fake_client = FakeClient(
        (
            '{"doctor_reasons":['
            f'{{"doctor_id":"{first_doctor_id}","llm_reason_zh":"這位醫師的資料包含膝部與韌帶相關專長，可作為就醫討論方向。"}}'
            ',{"doctor_id":"UNKNOWN_DOCTOR","llm_reason_zh":"不要出現"}'
            "]}"
        )
    )
    monkeypatch.setattr(reason_module, "get_openai_client", lambda: fake_client)
    monkeypatch.setattr(reason_module, "get_openai_model", lambda: "gpt-4o-mini")

    reasons = generate_llm_reasons("膝蓋韌帶受傷", concepts, doctors)

    assert reasons == {
        first_doctor_id: "這位醫師的資料包含膝部與韌帶相關專長，可作為就醫討論方向。"
    }
    assert fake_client.responses.calls[0]["model"] == "gpt-4o-mini"
    assert fake_client.responses.calls[0]["text"]["format"]["type"] == "json_schema"


def test_generate_llm_reasons_returns_empty_when_openai_fails(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    clear_settings_cache()
    concepts = KeywordConceptExtractor().extract_concepts("肩關節不穩定")
    doctors = rank_doctors(concepts, limit=2)
    fake_client = FakeClient(RuntimeError("simulated OpenAI failure"))
    monkeypatch.setattr(reason_module, "get_openai_client", lambda: fake_client)

    assert generate_llm_reasons("肩關節不穩定", concepts, doctors) == {}


def test_generate_llm_reasons_returns_empty_without_api_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    clear_settings_cache()
    concepts = KeywordConceptExtractor().extract_concepts("肩關節不穩定")
    doctors = rank_doctors(concepts, limit=2)

    assert generate_llm_reasons("肩關節不穩定", concepts, doctors) == {}
