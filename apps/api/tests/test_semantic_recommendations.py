import json
from types import SimpleNamespace

import pytest

from app.schemas import RecommendedDoctorResponse
from app.services import doctor_relevance, openai_concept_extractor
from app.services.concept_extractor import FallbackConceptExtractor, KeywordConceptExtractor
from app.services.concept_extractor import ConceptExtractionResult


class FakeClient:
    def __init__(self, payload):
        self.payload = payload
        self.responses = self

    def with_options(self, **kwargs):
        return self

    def create(self, **kwargs):
        return SimpleNamespace(output_text=json.dumps(self.payload), usage=None)


def doctor(identifier, specialty):
    return RecommendedDoctorResponse(doctor_id=identifier, doctor_name_zh=identifier, hospital_zh="test", department_zh="骨科部",
                                     subdepartment_zh="", specialty_raw_zh=specialty, source_url="", score=1, matched_concepts=[], reasons=[])


@pytest.mark.parametrize("query,positive,negative", [
    ("沒有糖尿病，只有膝蓋痛", "ORTHO_KNEE", "ENDO_DIABETES"),
    ("爸爸有糖尿病，但我膝蓋痛", "ORTHO_KNEE", "ENDO_DIABETES"),
    ("沒有膝蓋痛，只有肩膀痛", "ORTHO_SHOULDER", "ORTHO_KNEE"),
    ("No diabetes, knee pain", "ORTHO_KNEE", "ENDO_DIABETES"),
])
def test_keyword_fallback_distinguishes_patient_symptoms_from_denial_and_family(query, positive, negative):
    concepts = {item.concept_id for item in KeywordConceptExtractor().extract_concepts(query)}
    assert positive in concepts
    assert negative not in concepts


def test_parent_can_be_the_actual_patient_not_only_family_history():
    assert "ORTHO_KNEE" in {item.concept_id for item in KeywordConceptExtractor().extract_concepts("想幫媽媽看膝蓋痛")}


def test_explicit_semantic_abstention_does_not_reintroduce_denied_keywords(monkeypatch):
    payload = {"concept_ids": [], "confidence": 0.95, "concept_evidence": [],
               "assessment_summary": "患者明確否定糖尿病", "clarification_question": "目前想處理哪個症狀？"}
    monkeypatch.setattr(openai_concept_extractor, "get_openai_client", lambda: FakeClient(payload))
    result = FallbackConceptExtractor(openai_concept_extractor.OpenAIConceptExtractor(), KeywordConceptExtractor()).extract_with_metadata("我沒有糖尿病")
    assert result.concepts == []
    assert result.semantic_complete
    assert result.extractor == "openai"
    assert result.clarification_question
    assert not result.fallback_used


def test_concepts_require_actual_patient_evidence_and_assertion(monkeypatch):
    payload = {"concept_ids": ["ORTHO_KNEE", "ENDO_DIABETES", "ORTHO_ACL_INJURY"], "confidence": 0.9,
               "assessment_summary": "膝蓋症狀", "clarification_question": None, "concept_evidence": [
                   {"concept_id": "ORTHO_KNEE", "assertion": "reported", "patient_quote": "膝蓋痛", "confidence": 0.9},
                   {"concept_id": "ENDO_DIABETES", "assertion": "negated", "patient_quote": "沒有糖尿病", "confidence": 0.9},
                   {"concept_id": "ORTHO_ACL_INJURY", "assertion": "reported", "patient_quote": "前十字韌帶斷裂", "confidence": 0.9},
               ]}
    monkeypatch.setattr(openai_concept_extractor, "get_openai_client", lambda: FakeClient(payload))
    result = openai_concept_extractor.OpenAIConceptExtractor().extract_with_metadata("沒有糖尿病，膝蓋痛")
    assert [item.concept_id for item in result.concepts] == ["ORTHO_KNEE"]
    assert result.concepts[0].patient_evidence == "膝蓋痛"


def test_model_reorders_by_source_evidence_and_cannot_invent_expertise(monkeypatch):
    candidates = [doctor("spine", "脊椎手術"), doctor("knee", "膝關節運動傷害、韌帶重建")]
    payload = {"clarification_question": "請問疼痛位置？", "decisions": [
        {"doctor_id": "knee", "relevant": True, "patient_quote": "膝蓋痛", "specialty_quote": "膝關節運動傷害", "relevance_summary": "matching"},
        {"doctor_id": "spine", "relevant": True, "patient_quote": "膝蓋痛", "specialty_quote": "膝關節運動傷害", "relevance_summary": "invented"},
        {"doctor_id": "unknown", "relevant": True, "patient_quote": "膝蓋痛", "specialty_quote": "膝蓋", "relevance_summary": "invented"},
    ]}
    monkeypatch.setattr(doctor_relevance, "get_openai_settings", lambda: SimpleNamespace(api_key="test"))
    monkeypatch.setattr(doctor_relevance, "get_openai_client", lambda: FakeClient(payload))
    result = doctor_relevance.review_candidates("膝蓋痛", candidates, {"spine"})
    assert [item.doctor_id for item in result.doctors] == ["knee"]
    assert result.method == "evidence_review"
    assert result.doctors[0].specialty_evidence == "膝關節運動傷害"
    assert "invented" not in result.doctors[0].relevance_summary
    assert result.clarification_question is None


def test_symptom_quote_cannot_make_inferred_disease_a_reported_diagnosis(monkeypatch):
    payload = {"concept_ids": ["ORTHO_KNEE_OSTEOARTHRITIS"], "confidence": 0.9,
               "clarification_question": None, "concept_evidence": [
                   {"concept_id": "ORTHO_KNEE_OSTEOARTHRITIS", "assertion": "reported",
                    "patient_quote": "膝頭會痠痛", "confidence": 0.9},
               ]}
    monkeypatch.setattr(openai_concept_extractor, "get_openai_client", lambda: FakeClient(payload))
    result = openai_concept_extractor.OpenAIConceptExtractor().extract_with_metadata("膝頭會痠痛")
    assert result.concepts[0].assertion == "suspected"
    assert "疑似，未確診" in result.assessment_summary


def test_rule_fallback_does_not_promote_unreviewed_lexical_candidates(monkeypatch):
    monkeypatch.setattr(doctor_relevance, "get_openai_settings", lambda: SimpleNamespace(api_key=None))
    result = doctor_relevance.review_candidates("膝蓋痛", [doctor("rule", "膝關節"), doctor("lexical", "關節")], {"rule"})
    assert [item.doctor_id for item in result.doctors] == ["rule"]
    assert result.method == "rule_fallback"


def test_unclear_input_stops_before_candidate_lookup_or_appointment_requests(monkeypatch):
    from app.routers import recommendations
    from app.schemas import RecommendationRequest

    result = ConceptExtractionResult(concepts=[], extractor="openai", fallback_used=False,
                                     semantic_complete=True, clarification_question="想處理哪個部位的不舒服？")
    monkeypatch.setattr(recommendations, "get_concept_extractor", lambda: SimpleNamespace(extract_with_metadata=lambda query: result))

    def forbidden(*args, **kwargs):
        raise AssertionError("Unclear input must not trigger candidate or appointment lookup")

    monkeypatch.setattr(recommendations, "retrieve_candidates", forbidden)
    response = recommendations.recommend_doctors(RecommendationRequest(query="幫我推薦"))
    assert response.ranking_method == "needs_clarification"
    assert response.recommended_doctors == []
    assert response.clarification_question


def test_agent_broadens_once_without_relaxing_hard_preferences(monkeypatch):
    from app.routers import recommendations
    from app.schemas import RecommendationRequest, AppointmentPreparationRequest
    from app.services.openai_reason_generator import ReasonGenerationResult

    first, second = doctor("first", "膝關節"), doctor("second", "膝關節")
    calls = []
    monkeypatch.setattr(recommendations, "get_concept_extractor", lambda: KeywordConceptExtractor())
    monkeypatch.setattr(recommendations, "retrieve_candidates", lambda query, concepts, intent, expanded=False, **kwargs: ([second] if expanded else [first], {"first", "second"}))
    monkeypatch.setattr(recommendations, "review_candidates", lambda query, candidates, rule_ids: doctor_relevance.ReviewResult(doctors=candidates))
    monkeypatch.setattr(recommendations, "generate_llm_reasons_with_metadata", lambda **kwargs: ReasonGenerationResult(reasons={}))

    def capacity(candidates, preferences, limit):
        calls.append(preferences.model_dump(mode="json"))
        return ([] if candidates[0].doctor_id == "first" else candidates), False

    monkeypatch.setattr(recommendations, "filter_available_doctors", capacity)
    preferences = AppointmentPreparationRequest(patient_type="returning", sessions=["下午"], weekdays=[1], date_from="2099-10-19", date_to="2099-10-19")
    result = recommendations.recommend_doctors(RecommendationRequest(query="膝蓋痛", preferences=preferences))
    assert len(calls) == 2 and calls[0] == calls[1] == preferences.model_dump(mode="json")
    assert [item.doctor_id for item in result.recommended_doctors] == ["second"]
    assert sum(step["node"] == "broaden" for step in result.decision_trace) == 1


def test_expanded_retrieval_does_not_repeat_small_initial_pool(monkeypatch):
    monkeypatch.setattr(doctor_relevance, "rank_doctors", lambda *args, **kwargs: [])
    monkeypatch.setattr(doctor_relevance, "load_doctors", lambda: [
        {"doctor_id": str(i), "doctor_name_zh": str(i), "hospital_zh": "測試",
         "department_zh": "骨科部", "subdepartment_zh": "", "specialty_raw_zh": "膝關節", "source_url": ""}
        for i in range(8)
    ])
    initial, _ = doctor_relevance.retrieve_candidates("膝關節痛", [], None)
    expanded, _ = doctor_relevance.retrieve_candidates("膝關節痛", [], None, expanded=True)
    assert len(initial) == 8
    assert expanded == []
