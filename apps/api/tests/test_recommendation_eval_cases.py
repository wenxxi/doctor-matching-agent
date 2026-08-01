import csv
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.settings import get_openai_settings


PROJECT_ROOT = Path(__file__).resolve().parents[3]
EVAL_CASES_CSV = PROJECT_ROOT / "data" / "evaluation" / "recommendation_eval_cases.csv"

client = TestClient(app)


def load_eval_cases():
    with EVAL_CASES_CSV.open(newline="", encoding="utf-8-sig") as csv_file:
        return list(csv.DictReader(csv_file))


@pytest.mark.parametrize("case", load_eval_cases(), ids=lambda case: case["case_id"])
def test_recommendation_eval_case_with_keyword_fallback(case, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    get_openai_settings.cache_clear()

    response = client.post(
        "/api/recommendations",
        json={"query": case["query"], "limit": 3},
    )

    assert response.status_code == 200
    data = response.json()
    concept_ids = {concept["concept_id"] for concept in data["matched_concepts"]}
    expected_concept_ids = {
        concept_id.strip()
        for concept_id in case["expected_concept_ids"].split(";")
        if concept_id.strip()
    }
    departments = {
        doctor["department_zh"]
        for doctor in data["recommended_doctors"]
    }

    assert data["concept_extraction_method"] == "keyword"
    assert data["fallback_used"] is False
    assert expected_concept_ids <= concept_ids
    assert data["recommended_doctors"]
    assert len(data["recommended_doctors"]) <= 3
    assert departments == {case["expected_department_zh"]}
