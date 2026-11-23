from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.main import app
from app.schemas import AppointmentPreparationRequest, AppointmentsResponse, AppointmentSlotResponse
from app.services import appointment_agent


DOCTOR = {"doctor_id": "CGMH_LINKOU_ORTHO_001", "doctor_name_zh": "傅再生"}


def slot(date="2099-10-19", session="上午", eligibility="一般掛號（資格以院方確認為準）"):
    session_code = {"上午": "1", "下午": "2", "夜診": "3"}[session]
    return AppointmentSlotResponse(date=date, session=session, eligibility=eligibility,
                                   registration_url=f"https://register.cgmh.org.tw/Checkin/3/32700A/{date.replace('-', '')}/2245/{session_code}")


def checkin_html(selected):
    action = selected.registration_url.replace("/Checkin/", "/CheckinConfirm/")
    return f"""<p>傅再生 {selected.date.replace('-', '/')} {selected.session}</p>
    <form method='post' action='{action}'><input name='idNumber'><input name='verification'></form>"""


def snapshot(monkeypatch, slots, status="available"):
    monkeypatch.setattr(appointment_agent, "get_appointments", lambda doctor: AppointmentsResponse(
        doctor_id=doctor["doctor_id"], status=status, registration_url=None, schedule_urls=[],
        checked_at=None, slots=slots, message="test",
    ))


def test_agent_uses_exact_preferences_and_does_not_relax_patient_eligibility():
    first_only = slot(eligibility="初診可掛（從未在本院看診）")
    department_only = slot(eligibility="科初診可掛（半年內未看過該科）")
    for patient_type in ("unknown", "returning"):
        request = AppointmentPreparationRequest(patient_type=patient_type)
        assert not appointment_agent.matches_preferences(first_only, request)
        assert not appointment_agent.matches_preferences(department_only, request)
    assert appointment_agent.matches_preferences(department_only, AppointmentPreparationRequest(patient_type="department_first"))
    assert not appointment_agent.matches_preferences(first_only, AppointmentPreparationRequest(patient_type="department_first"))
    assert appointment_agent.matches_preferences(first_only, AppointmentPreparationRequest(patient_type="first_visit"))
    selected = slot()
    assert not appointment_agent.matches_preferences(selected, AppointmentPreparationRequest(patient_type="unknown", sessions=["下午"]))
    assert not appointment_agent.matches_preferences(selected, AppointmentPreparationRequest(patient_type="unknown", date_from="2099-10-20"))
    assert not appointment_agent.matches_preferences(selected, AppointmentPreparationRequest(patient_type="unknown", weekdays=[(datetime.fromisoformat(selected.date).weekday() + 1) % 7]))


def test_agent_replans_when_first_candidate_is_not_available(monkeypatch):
    first, second = slot(), slot(date="2099-10-20")
    snapshot(monkeypatch, [second, first])
    calls = []

    def live_page(url):
        calls.append(url)
        return ("已額滿" if url == first.registration_url else checkin_html(second)), datetime.now(timezone.utc)

    monkeypatch.setattr(appointment_agent, "fetch_live_page", live_page)
    result = appointment_agent.prepare_appointment(DOCTOR, AppointmentPreparationRequest(patient_type="returning"))
    assert result.status == "awaiting_patient"
    assert result.selected_slot == second
    assert result.attempted_count == 2
    assert calls == [first.registration_url, second.registration_url]


def test_agent_bounds_retries_and_does_not_claim_booking_success(monkeypatch):
    snapshot(monkeypatch, [slot(date=f"2099-10-{day}") for day in range(19, 24)])
    monkeypatch.setattr(appointment_agent, "fetch_live_page", lambda url: ("系統維護中", datetime.now(timezone.utc)))
    result = appointment_agent.prepare_appointment(DOCTOR, AppointmentPreparationRequest(patient_type="unknown"))
    assert result.status == "retry_needed"
    assert result.attempted_count == 3
    assert result.selected_slot is None


def test_agent_distinguishes_no_match_from_incomplete_lookup(monkeypatch):
    request = AppointmentPreparationRequest(patient_type="returning")
    snapshot(monkeypatch, [])
    assert appointment_agent.prepare_appointment(DOCTOR, request).status == "no_match"
    snapshot(monkeypatch, [], "partial")
    assert appointment_agent.prepare_appointment(DOCTOR, request).status == "retry_needed"


def test_prepare_endpoint_rejects_invalid_constraints():
    client = TestClient(app)
    url = "/api/doctors/CGMH_LINKOU_ORTHO_001/appointments/prepare"
    for payload in (
        {"patient_type": "returning", "date_from": "2099-10-20", "date_to": "2099-10-19"},
        {"patient_type": "returning", "sessions": []},
        {"patient_type": "returning", "weekdays": [7]},
    ):
        assert client.post(url, json=payload).status_code == 422
