from datetime import datetime, timezone
from types import SimpleNamespace
import json

import pytest

from app.schemas import AppointmentPreparationResponse, AppointmentSlotResponse
from app.services import available_doctors
from app.services import doctor_relevance


@pytest.fixture(autouse=True)
def isolated_security_store(monkeypatch, tmp_path):
    """Real admission code, disposable counters; never use developer/production DB."""
    from app.services import agent_storage
    monkeypatch.setenv("AGENT_DATABASE_URL", f"sqlite:///{tmp_path / 'security.sqlite3'}")
    monkeypatch.delenv("RENDER", raising=False)
    monkeypatch.setenv("LLM_PRICED_MODEL", "test-model")
    monkeypatch.setenv("LLM_INPUT_USD_PER_MILLION", "0.15")
    monkeypatch.setenv("LLM_OUTPUT_USD_PER_MILLION", "0.60")
    agent_storage.get_agent_engine.cache_clear()
    agent_storage.initialize_agent_storage.cache_clear()
    yield
    if agent_storage.get_agent_engine.cache_info().currsize:
        agent_storage.get_agent_engine().dispose()
    agent_storage.get_agent_engine.cache_clear()
    agent_storage.initialize_agent_storage.cache_clear()


def structured_concept_response(output_text, request, usage=None):
    """Build a current-contract model fixture, retaining the test's chosen IDs."""
    payload = json.loads(output_text)
    query = json.loads(request["input"])["user_query"]
    payload.setdefault("concept_evidence", [{"concept_id": identifier, "assertion": "suspected",
                                             "patient_quote": query, "confidence": payload.get("confidence", 0)}
                                            for identifier in payload.get("concept_ids", [])])
    payload.setdefault("assessment_summary", "test interpretation")
    payload.setdefault("search_terms", [])
    payload.setdefault("clarification_question", None)
    return SimpleNamespace(output_text=json.dumps(payload), usage=usage)


@pytest.fixture
def verified_doctor_availability(monkeypatch):
    """Keep ranking and case tests independent of live hospital availability."""
    monkeypatch.setattr(doctor_relevance, "get_openai_settings", lambda: SimpleNamespace(api_key=None))
    def prepare(doctor, preferences):
        return AppointmentPreparationResponse(
            doctor_id=doctor["doctor_id"], status="awaiting_patient",
            selected_slot=AppointmentSlotResponse(
                date=str(preferences.date_from or "2099-10-19"), session=preferences.sessions[0],
                eligibility="一般掛號", registration_url="https://register.cgmh.org.tw/Checkin/3/TEST/20991019/1/1",
            ), verified_at=datetime.now(timezone.utc), message="verified test slot",
        )
    monkeypatch.setattr(available_doctors, "prepare_appointment", prepare)
