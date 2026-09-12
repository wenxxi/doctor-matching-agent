from fastapi.testclient import TestClient

import app.routers.recommendations as recommendations_router
from app.main import app
from app.services.openai_reason_generator import ReasonGenerationResult
from app.settings import get_openai_settings


client = TestClient(app)


def clear_openai_settings(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    get_openai_settings.cache_clear()


def test_recommendations_for_knee_query(monkeypatch):
    clear_openai_settings(monkeypatch)

    response = client.post(
        "/api/recommendations",
        json={"query": "我膝蓋運動後疼痛，可能韌帶受傷", "limit": 3},
    )

    assert response.status_code == 200
    data = response.json()
    concept_ids = {concept["concept_id"] for concept in data["matched_concepts"]}
    assert data["concept_extraction_method"] == "keyword"
    assert data["fallback_used"] is False
    assert data["department_intent"] == "骨科部"
    assert data["department_intent_confidence"] > 0
    assert data["candidate_concepts_count"] is not None
    assert data["input_tokens"] is None
    assert data["output_tokens"] is None
    assert data["reason_input_tokens"] is None
    assert data["reason_output_tokens"] is None
    assert "ORTHO_KNEE" in concept_ids
    assert "ORTHO_LIGAMENT_INJURY" in concept_ids
    assert data["recommended_doctors"]
    assert len(data["recommended_doctors"]) <= 3
    assert data["message"] is None


def test_recommendations_for_shoulder_query(monkeypatch):
    clear_openai_settings(monkeypatch)

    response = client.post(
        "/api/recommendations",
        json={"query": "肩關節不穩定，擔心旋轉肌袖損傷", "limit": 3},
    )

    assert response.status_code == 200
    data = response.json()
    concept_ids = {concept["concept_id"] for concept in data["matched_concepts"]}
    assert data["concept_extraction_method"] == "keyword"
    assert data["fallback_used"] is False
    assert "ORTHO_ROTATOR_CUFF_INJURY" in concept_ids
    assert "ORTHO_SHOULDER_INSTABILITY" in concept_ids
    assert data["department_intent"] == "骨科部"
    assert data["recommended_doctors"]


def test_recommendations_for_neurology_query(monkeypatch):
    clear_openai_settings(monkeypatch)

    response = client.post(
        "/api/recommendations",
        json={"query": "我常常頭痛，也有癲癇和睡眠障礙", "limit": 3},
    )

    assert response.status_code == 200
    data = response.json()
    concept_ids = {concept["concept_id"] for concept in data["matched_concepts"]}
    departments = {doctor["department_zh"] for doctor in data["recommended_doctors"]}
    assert "NEURO_HEADACHE" in concept_ids
    assert "NEURO_EPILEPSY" in concept_ids
    assert data["department_intent"] == "神經內科"
    assert data["recommended_doctors"]
    assert departments == {"神經內科"}


def test_recommendations_for_cardiology_query(monkeypatch):
    clear_openai_settings(monkeypatch)

    response = client.post(
        "/api/recommendations",
        json={"query": "我有心律不整和高血壓，想看心臟科", "limit": 3},
    )

    assert response.status_code == 200
    data = response.json()
    concept_ids = {concept["concept_id"] for concept in data["matched_concepts"]}
    departments = {doctor["department_zh"] for doctor in data["recommended_doctors"]}
    assert "CARDIO_ARRHYTHMIA" in concept_ids
    assert "CARDIO_HYPERTENSION" in concept_ids
    assert data["department_intent"] == "心臟內科"
    assert data["recommended_doctors"]
    assert departments == {"心臟內科"}


def test_recommendations_for_productive_cough_query(monkeypatch):
    clear_openai_settings(monkeypatch)

    response = client.post(
        "/api/recommendations",
        json={"query": "有點喉嚨痛，最近有黃痰，一直咳嗽兩個禮拜", "limit": 3},
    )

    assert response.status_code == 200
    data = response.json()
    concept_ids = {concept["concept_id"] for concept in data["matched_concepts"]}
    departments = {doctor["department_zh"] for doctor in data["recommended_doctors"]}
    assert "CHEST_CHRONIC_COUGH" in concept_ids
    assert "CHEST_PULMONARY_INFECTION" in concept_ids
    assert data["department_intent"] == "胸腔內科"
    assert data["recommended_doctors"]
    assert departments == {"胸腔內科"}
    assert data["message"] is None


def test_recommendations_for_ocular_surface_query(monkeypatch):
    clear_openai_settings(monkeypatch)

    response = client.post(
        "/api/recommendations",
        json={"query": "眼睛酸澀 異物感", "limit": 3},
    )

    assert response.status_code == 200
    data = response.json()
    concept_ids = {concept["concept_id"] for concept in data["matched_concepts"]}
    departments = {doctor["department_zh"] for doctor in data["recommended_doctors"]}
    assert "OPH_CORNEA_OCULAR_SURFACE" in concept_ids
    assert data["department_intent"] == "眼科"
    assert data["recommended_doctors"]
    assert departments == {"眼科"}
    assert data["message"] is None


def test_recommendations_unknown_query_returns_helpful_message(monkeypatch):
    clear_openai_settings(monkeypatch)

    response = client.post(
        "/api/recommendations",
        json={"query": "我想詢問睡眠品質和皮膚保養", "limit": 3},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["concept_extraction_method"] == "keyword"
    assert data["fallback_used"] is False
    assert data["department_intent"] is None
    assert data["department_intent_confidence"] == 0.0
    assert data["matched_concepts"] == []
    assert data["recommended_doctors"] == []
    assert data["message"]


def test_recommendations_limit_is_applied(monkeypatch):
    clear_openai_settings(monkeypatch)

    response = client.post(
        "/api/recommendations",
        json={"query": "骨折外傷", "limit": 2},
    )

    assert response.status_code == 200
    data = response.json()
    assert len(data["recommended_doctors"]) == 2


def test_recommendations_limit_is_capped_at_three(monkeypatch):
    clear_openai_settings(monkeypatch)

    response = client.post(
        "/api/recommendations",
        json={"query": "骨折外傷", "limit": 10},
    )

    assert response.status_code == 200
    data = response.json()
    assert len(data["recommended_doctors"]) == 3


def test_recommendations_includes_mocked_llm_reason(monkeypatch):
    clear_openai_settings(monkeypatch)

    def fake_generate_llm_reasons_with_metadata(query, matched_concepts, doctors):
        return ReasonGenerationResult(
            reasons={doctors[0].doctor_id: "這位醫師的專長資料與膝部症狀相關。"},
            input_tokens=88,
            output_tokens=21,
        )

    monkeypatch.setattr(
        recommendations_router,
        "generate_llm_reasons_with_metadata",
        fake_generate_llm_reasons_with_metadata,
    )

    response = client.post(
        "/api/recommendations",
        json={"query": "膝蓋韌帶受傷", "limit": 3},
    )

    assert response.status_code == 200
    doctors = response.json()["recommended_doctors"]
    assert response.json()["reason_input_tokens"] == 88
    assert response.json()["reason_output_tokens"] == 21
    assert doctors[0]["llm_reason_zh"] == "這位醫師的專長資料與膝部症狀相關。"
    assert doctors[1]["llm_reason_zh"] is None
