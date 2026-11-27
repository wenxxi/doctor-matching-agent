from datetime import datetime, timezone
from types import SimpleNamespace
import json

import pytest

from app.schemas import AppointmentPreparationResponse, AppointmentSlotResponse
from app.services import available_doctors
from app.services import doctor_relevance


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
