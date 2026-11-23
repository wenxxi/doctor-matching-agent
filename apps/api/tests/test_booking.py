import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from urllib.parse import unquote

import pytest
from fastapi.testclient import TestClient

from app.booking_schemas import BookingContinueRequest, BookingPatientRequest
from app.main import app
from app.schemas import AppointmentsResponse, AppointmentSlotResponse
from app.services import booking


SLOT = AppointmentSlotResponse(
    date="2099-10-19", session="上午", eligibility="一般掛號（資格以院方確認為準）",
    registration_url="https://register.cgmh.org.tw/Checkin/3/32700A/20991019/2245/1",
)
DOCTOR = {"doctor_id": "CGMH_LINKOU_ORTHO_001", "doctor_name_zh": "傅再生"}
ACTION = SLOT.registration_url.replace("/Checkin/", "/CheckinConfirm/")
INITIAL = f"""<p>傅再生 2099/10/19 上午</p><form method='post' action='{ACTION}'>
<input type='hidden' name='__RequestVerificationToken' value='test-csrf'>
<input type='hidden' name='hospitalID' value='3'><input type='hidden' name='deptID' value='32700A'>
<input type='hidden' name='opdDate' value='20991019'><input type='hidden' name='opdTimeID' value='1'>
<input type='hidden' name='doctorID' value='2245'><input name='idNumber'><input name='verification'>
</form>"""
CONFIRMATION = f"""<form method='post' action='{ACTION}'>
<input type='hidden' name='__RequestVerificationToken' value='next-csrf'>
<input type='hidden' name='doctorID' value='2245'><input name='tel' required placeholder='聯絡電話'>
</form>"""
RECEIPT = "<h1>掛號成功</h1><p>傅再生 2099/10/19 上午</p><p>掛號序號：42</p>"
PATIENT = {"id_type": "2", "id_number": "TEST000000", "birthday": "1990-01-01", "verification": "TEST", "consent": True}


class FakeHospitalClient:
    instances = []

    def __init__(self):
        self.calls = []
        self.query_result = {
            "Func": "PatQueryChick", "codeError": "N", "assError": "N", "isFirst": "N",
            "PatQuery": json.dumps([{"patNumber": "TEST1234", "name": "測試患者"}]),
        }
        self.pages = [CONFIRMATION, RECEIPT]
        self.instances.append(self)

    def page(self, url, fields=None):
        self.calls.append((url, fields))
        if fields is None:
            return INITIAL
        page = self.pages.pop(0)
        if isinstance(page, Exception):
            raise page
        return page

    def request(self, url, fields=None):
        self.calls.append((url, fields))
        return json.dumps(self.query_result).encode(), "application/json"

    def captcha(self):
        return "data:image/png;base64,dGVzdA=="


@pytest.fixture(autouse=True)
def isolated_booking(monkeypatch):
    booking.SESSIONS.clear()
    FakeHospitalClient.instances.clear()
    monkeypatch.setattr(booking, "HospitalClient", FakeHospitalClient)
    monkeypatch.setattr(booking, "get_appointments", lambda doctor: AppointmentsResponse(
        doctor_id=doctor["doctor_id"], status="available", registration_url=None,
        schedule_urls=[], checked_at=None, slots=[SLOT], message="test",
    ))
    yield
    booking.SESSIONS.clear()


def start():
    response = booking.start_booking(DOCTOR, SLOT.registration_url)
    return response.token, booking.get_session(response.token)


def test_start_does_not_send_patient_data_or_expose_hospital_tokens():
    token, session = start()
    assert len(token) >= 32
    assert session.client.calls == [(SLOT.registration_url, None)]
    assert booking.refresh_captcha(token).captcha_image.startswith("data:image/png;")
    assert session.form.hidden["__RequestVerificationToken"] == "test-csrf"


def test_cookie_context_is_not_shared_between_patients():
    first_token, first = start()
    second_token, second = start()
    assert first_token != second_token
    assert first.client is not second.client
    booking.close_booking(first_token)
    assert booking.get_session(second_token) is second


def test_unknown_slot_is_rejected_before_opening_any_hospital_session():
    with pytest.raises(booking.BookingError):
        booking.start_booking(DOCTOR, "https://example.com/")
    assert FakeHospitalClient.instances == []


def test_expired_session_cannot_submit():
    token, session = start()
    session.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    with pytest.raises(booking.BookingError):
        booking.submit_patient(token, BookingPatientRequest(**PATIENT))
    assert token not in booking.SESSIONS


def test_ajax_verification_precedes_form_post_and_preserves_csrf():
    token, session = start()
    response = booking.submit_patient(token, BookingPatientRequest(**PATIENT))
    assert response.status == "awaiting_confirmation"
    assert response.step_token
    query_call = session.client.calls[1]
    assert query_call[0] == "/Ajax"
    assert query_call[1]["__RequestVerificationToken"] == "test-csrf"
    query = {item["name"]: item["value"] for item in json.loads(unquote(query_call[1]["Val"]))}
    assert query["CKROC_birthday"] == "TRUE"
    assert query["birthday"] == "19900101"
    form_call = session.client.calls[2]
    assert form_call[0] == ACTION
    assert form_call[1]["patNumber"] == "TEST1234"
    assert form_call[1]["insuuid"] == "A"
    assert response.fields[0].label == "聯絡電話"


def test_wrong_captcha_never_posts_the_registration_form():
    token, session = start()
    session.client.query_result["codeError"] = "Y"
    response = booking.submit_patient(token, BookingPatientRequest(**PATIENT))
    assert response.status == "captcha_error"
    assert response.captcha_image
    assert len(session.client.calls) == 2
    assert session.status == "awaiting_patient"


def test_rejected_eligibility_never_posts_the_registration_form():
    token, session = start()
    session.form.hidden.update({"isFull": "Y", "canReg": "Y", "memo": "限科初診"})
    session.client.query_result["isDptFirst"] = "N"
    response = booking.submit_patient(token, BookingPatientRequest(**PATIENT))
    assert response.status == "rejected"
    assert len(session.client.calls) == 2


def test_final_submit_requires_confirmation_and_only_returns_verified_receipt():
    token, session = start()
    prepared = booking.submit_patient(token, BookingPatientRequest(**PATIENT))
    response = booking.continue_booking(token, BookingContinueRequest(step_token=prepared.step_token, fields={"tel": "0000000000"}, consent=True))
    assert response.status == "confirmed"
    assert response.receipt_number == "42"
    assert session.form.hidden == {}
    assert session.response == response


def test_replayed_confirmation_does_not_advance_a_new_step():
    token, session = start()
    session.client.pages = [CONFIRMATION, CONFIRMATION, RECEIPT]
    initial = booking.submit_patient(token, BookingPatientRequest(**PATIENT))
    request = BookingContinueRequest(step_token=initial.step_token, fields={"tel": "0000000000"}, consent=True)
    next_step = booking.continue_booking(token, request)
    calls_before = len(session.client.calls)
    repeated = booking.continue_booking(token, request)
    assert repeated == next_step
    assert repeated.step_token != initial.step_token
    assert len(session.client.calls) == calls_before


def test_double_submit_does_not_create_two_form_posts():
    token, session = start()
    patient = BookingPatientRequest(**PATIENT)
    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(executor.map(lambda _: booking.submit_patient(token, patient), range(2)))
    assert all(response.status == "awaiting_confirmation" for response in responses)
    assert len(session.client.calls) == 3


def test_timeout_is_unknown_and_never_automatically_retried():
    token, session = start()
    client = session.client
    client.pages = [TimeoutError("test")]
    patient = BookingPatientRequest(**PATIENT)
    assert booking.submit_patient(token, patient).status == "unknown"
    calls_before = len(client.calls)
    assert booking.submit_patient(token, patient).status == "unknown"
    assert len(client.calls) == calls_before


def test_tampered_hidden_fields_are_not_forwarded():
    token, session = start()
    prepared = booking.submit_patient(token, BookingPatientRequest(**PATIENT))
    calls_before = len(session.client.calls)
    with pytest.raises(booking.BookingError):
        booking.continue_booking(token, BookingContinueRequest(step_token=prepared.step_token, fields={"doctorID": "other"}, consent=True))
    assert len(session.client.calls) == calls_before


def test_success_notice_or_mismatched_receipt_does_not_claim_success():
    _, session = start()
    assert booking.finish_response(session, "如掛號成功請記下序號 42").status == "needs_official"
    assert booking.finish_response(session, "掛號成功 其他醫師 2099/10/19 上午 序號 42").status == "needs_official"
    assert booking.finish_response(session, "<script>掛號成功 傅再生 2099/10/19 上午 序號 42</script>").status == "needs_official"


def test_external_form_actions_are_rejected():
    with pytest.raises(booking.BookingError):
        booking.parse_hospital_page("<form method='post' action='https://example.com/CheckinConfirm/3/32700A/20991019/2245/1'></form>")


def test_api_uses_no_store_and_never_echoes_invalid_patient_data():
    client = TestClient(app)
    response = client.post("/api/booking/sessions", json={"doctor_id": DOCTOR["doctor_id"], "registration_url": SLOT.registration_url})
    assert response.status_code == 200
    assert "no-store" in response.headers["cache-control"]
    assert "test-csrf" not in response.text
    token = response.json()["token"]
    invalid = client.post("/api/booking/submit", headers={"X-Booking-Token": token}, json={**PATIENT, "consent": False})
    assert invalid.status_code == 422
    assert PATIENT["id_number"] not in invalid.text
    assert PATIENT["verification"] not in invalid.text
    assert len(booking.get_session(token).client.calls) == 1
