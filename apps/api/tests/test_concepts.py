from types import SimpleNamespace

from fastapi.testclient import TestClient

import app.services.openai_concept_extractor as openai_extractor_module
from app.main import app
from app.settings import get_openai_settings


client = TestClient(app)


class FakeResponses:
    def __init__(self, output_text: str | Exception, usage=None) -> None:
        self.output_text = output_text
        self.usage = usage

    def create(self, **kwargs):
        if isinstance(self.output_text, Exception):
            raise self.output_text
        return SimpleNamespace(output_text=self.output_text, usage=self.usage)


class FakeClient:
    def __init__(self, output_text: str | Exception, usage=None) -> None:
        self.responses = FakeResponses(output_text, usage)


def clear_settings_cache() -> None:
    get_openai_settings.cache_clear()


def test_extract_concepts_uses_keyword_without_api_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    clear_settings_cache()

    response = client.post(
        "/api/concepts/extract",
        json={"query": "膝蓋韌帶受傷"},
    )

    assert response.status_code == 200
    data = response.json()
    concept_ids = {concept["concept_id"] for concept in data["matched_concepts"]}
    assert data["extractor"] == "keyword"
    assert data["fallback_used"] is False
    assert data["candidate_concepts_count"] is not None
    assert data["input_tokens"] is None
    assert data["output_tokens"] is None
    assert "ORTHO_KNEE" in concept_ids
    assert "ORTHO_LIGAMENT_INJURY" in concept_ids


def test_extract_concepts_uses_mocked_openai_with_api_key(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    clear_settings_cache()
    fake_client = FakeClient(
        '{"concept_ids":["ORTHO_KNEE"],"confidence":0.88}',
        usage=SimpleNamespace(input_tokens=101, output_tokens=12),
    )
    monkeypatch.setattr(openai_extractor_module, "get_openai_client", lambda: fake_client)
    monkeypatch.setattr(openai_extractor_module, "get_openai_model", lambda: "gpt-4o-mini")

    response = client.post(
        "/api/concepts/extract",
        json={"query": "跑步後膝蓋痛"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["extractor"] == "openai"
    assert data["fallback_used"] is False
    assert data["candidate_concepts_count"] <= 30
    assert data["input_tokens"] == 101
    assert data["output_tokens"] == 12
    assert [concept["concept_id"] for concept in data["matched_concepts"]] == ["ORTHO_KNEE"]


def test_extract_concepts_reports_fallback_when_openai_fails(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    clear_settings_cache()
    fake_client = FakeClient(RuntimeError("simulated OpenAI failure"))
    monkeypatch.setattr(openai_extractor_module, "get_openai_client", lambda: fake_client)
    monkeypatch.setattr(openai_extractor_module, "get_openai_model", lambda: "gpt-4o-mini")

    response = client.post(
        "/api/concepts/extract",
        json={"query": "膝蓋韌帶受傷"},
    )

    assert response.status_code == 200
    data = response.json()
    concept_ids = {concept["concept_id"] for concept in data["matched_concepts"]}
    assert data["extractor"] == "keyword"
    assert data["fallback_used"] is True
    assert "ORTHO_KNEE" in concept_ids
