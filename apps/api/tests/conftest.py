from datetime import datetime, timezone

import pytest

from app.schemas import AppointmentPreparationResponse, AppointmentSlotResponse
from app.services import available_doctors


@pytest.fixture
def verified_doctor_availability(monkeypatch):
    """Keep ranking and case tests independent of live hospital availability."""
    def prepare(doctor, preferences):
        return AppointmentPreparationResponse(
            doctor_id=doctor["doctor_id"], status="awaiting_patient",
            selected_slot=AppointmentSlotResponse(
                date=str(preferences.date_from or "2099-10-19"), session=preferences.sessions[0],
                eligibility="一般掛號", registration_url="https://register.cgmh.org.tw/Checkin/3/TEST/20991019/1/1",
            ), verified_at=datetime.now(timezone.utc), message="verified test slot",
        )
    monkeypatch.setattr(available_doctors, "prepare_appointment", prepare)
