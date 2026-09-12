import json
from types import SimpleNamespace

import pytest

import app.services.concept_extractor as concept_extractor_module
import app.services.openai_concept_extractor as openai_extractor_module
from app.services.concept_extractor import (
    ConceptExtractionResult,
    FallbackConceptExtractor,
    KeywordConceptExtractor,
)
from app.services.openai_concept_extractor import OpenAIConceptExtractor
from app.services.processed_data import load_medical_concepts
from app.settings import get_openai_settings


class FakeResponses:
    def __init__(self, output_text: str | Exception, usage=None) -> None:
        self.output_text = output_text
        self.usage = usage
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if isinstance(self.output_text, Exception):
            raise self.output_text
        return SimpleNamespace(output_text=self.output_text, usage=self.usage)


class FakeClient:
    def __init__(self, output_text: str | Exception, usage=None) -> None:
        self.responses = FakeResponses(output_text, usage)


def clear_settings_cache() -> None:
    get_openai_settings.cache_clear()


@pytest.fixture(autouse=True)
def reset_openai_settings():
    clear_settings_cache()
    yield
    clear_settings_cache()


def test_openai_extractor_maps_knee_text_when_mocked(monkeypatch):
    fake_client = FakeClient(
        '{"concept_ids":["ORTHO_KNEE","ORTHO_LIGAMENT_INJURY"],"confidence":0.82}',
        usage=SimpleNamespace(input_tokens=111, output_tokens=22),
    )
    monkeypatch.setattr(openai_extractor_module, "get_openai_client", lambda: fake_client)
    monkeypatch.setattr(openai_extractor_module, "get_openai_model", lambda: "gpt-4o-mini")

    result = OpenAIConceptExtractor().extract_with_metadata("我膝蓋運動後疼痛，可能韌帶受傷")
    matched = result.concepts

    concept_ids = {concept.concept_id for concept in matched}
    assert concept_ids == {"ORTHO_KNEE", "ORTHO_LIGAMENT_INJURY"}
    assert result.candidate_concepts_count == len(load_medical_concepts())
    assert result.input_tokens == 111
    assert result.output_tokens == 22
    assert all(concept.matched_terms == ("LLM:0.82",) for concept in matched)
    assert fake_client.responses.calls[0]["model"] == "gpt-4o-mini"
    assert fake_client.responses.calls[0]["text"]["format"]["type"] == "json_schema"
    request_payload = json.loads(fake_client.responses.calls[0]["input"])
    allowed_concept_ids = {
        concept["concept_id"]
        for concept in request_payload["allowed_concepts"]
    }
    assert len(allowed_concept_ids) == len(load_medical_concepts())
    assert "ORTHO_KNEE" in allowed_concept_ids
    assert "ORTHO_LIGAMENT_INJURY" in allowed_concept_ids


def test_openai_extractor_can_use_medical_knowledge_across_departments(monkeypatch):
    fake_client = FakeClient(
        '{"concept_ids":["CVS_PERIPHERAL_ARTERIAL_DISEASE","ENDO_DIABETIC_FOOT"],"confidence":0.86}'
    )
    monkeypatch.setattr(openai_extractor_module, "get_openai_client", lambda: fake_client)
    monkeypatch.setattr(openai_extractor_module, "get_openai_model", lambda: "gpt-4o-mini")

    result = OpenAIConceptExtractor().extract_with_metadata("整支腳黑掉了")
    concept_ids = {concept.concept_id for concept in result.concepts}
    request_payload = json.loads(fake_client.responses.calls[0]["input"])
    allowed_concept_ids = {
        concept["concept_id"]
        for concept in request_payload["allowed_concepts"]
    }

    assert concept_ids == {"CVS_PERIPHERAL_ARTERIAL_DISEASE", "ENDO_DIABETIC_FOOT"}
    assert "CVS_PERIPHERAL_ARTERIAL_DISEASE" in allowed_concept_ids
    assert "ENDO_DIABETIC_FOOT" in allowed_concept_ids
    assert result.candidate_concepts_count == len(load_medical_concepts())


def test_openai_extractor_ignores_unknown_concept_ids(monkeypatch):
    fake_client = FakeClient('{"concept_ids":["ORTHO_KNEE","MADE_UP_CONCEPT"],"confidence":0.91}')
    monkeypatch.setattr(openai_extractor_module, "get_openai_client", lambda: fake_client)
    monkeypatch.setattr(openai_extractor_module, "get_openai_model", lambda: "gpt-4o-mini")

    matched = OpenAIConceptExtractor().extract_concepts("膝蓋痛")

    assert [concept.concept_id for concept in matched] == ["ORTHO_KNEE"]


def test_extractor_selection_uses_keyword_without_api_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    clear_settings_cache()

    extractor = concept_extractor_module.get_concept_extractor()

    assert isinstance(extractor, KeywordConceptExtractor)


def test_openai_failure_falls_back_to_keyword_extractor(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    clear_settings_cache()

    class FailingOpenAIConceptExtractor:
        def extract_concepts(self, query: str):
            raise RuntimeError("simulated OpenAI failure")

    extractor = FallbackConceptExtractor(
        primary=FailingOpenAIConceptExtractor(),
        fallback=KeywordConceptExtractor(),
    )
    matched = extractor.extract_concepts("膝蓋韌帶受傷")

    concept_ids = {concept.concept_id for concept in matched}
    assert "ORTHO_KNEE" in concept_ids
    assert "ORTHO_LIGAMENT_INJURY" in concept_ids


def test_openai_empty_result_falls_back_to_keyword_extractor(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    clear_settings_cache()

    class EmptyOpenAIConceptExtractor:
        def extract_with_metadata(self, query: str):
            return ConceptExtractionResult(
                concepts=[],
                extractor="openai",
                fallback_used=False,
                candidate_concepts_count=20,
                input_tokens=12,
                output_tokens=4,
            )

    extractor = FallbackConceptExtractor(
        primary=EmptyOpenAIConceptExtractor(),
        fallback=KeywordConceptExtractor(),
    )
    result = extractor.extract_with_metadata("一直咳嗽兩個禮拜，有黃痰")

    concept_ids = {concept.concept_id for concept in result.concepts}
    assert result.extractor == "keyword"
    assert result.fallback_used is True
    assert result.candidate_concepts_count == 20
    assert result.input_tokens == 12
    assert result.output_tokens == 4
    assert "CHEST_CHRONIC_COUGH" in concept_ids
    assert "CHEST_PULMONARY_INFECTION" in concept_ids
