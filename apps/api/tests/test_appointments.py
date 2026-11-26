from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.main import app
from app.services import appointments


DOCTOR = {
    "doctor_id": "CGMH_LINKOU_ORTHO_001",
    "doctor_name_zh": "傅再生",
    "department_zh": "骨科部",
}
DEPARTMENT = "/Department_WEEK/3/32700A"
SCHEDULE = """
看診醫師時間表 掛號
<a href='/Checkin/3/32700A/20991019/2245/1'>12245 傅再生<span>(額滿)初診可掛</span></a>
<a href='/Checkin/3/32700A/20991020/2245/2'>22245 傅再生<span>(額滿)科初診可掛</span></a>
<a href='/Checkin/3/32700A/20991021/2245/3'>32245 傅再生</a>
<a href='javascript:void(0)' class='state-full'>12245 傅再生(額滿)</a>
<a href='/Checkin/3/32700A/20991022/2245/1'>12245 傅再生(額滿)</a>
<a href='/Checkin/3/32700A/20991023/2245/1'>12245 傅再生(停診)</a>
<a href='/Checkin/3/32700A/20991024/1390/1'>11390 胡永學</a>
<a href='/Checkin/3/32700A/20991025/2245/1'>12245 傅再生明</a>
<a href='/Checkin/5/32700A/20991026/2245/1'>12245 傅再生</a>
<a href='https://example.com/Checkin/3/32700A/20991027/2245/1'>12245 傅再生</a>
<a href='/Checkin/3/32700A/20200101/2245/1'>12245 傅再生</a>
<!-- <a href='/Checkin/3/32700A/20991028/2245/1'>12245 傅再生</a> -->
"""


def test_slots_preserve_eligibility_and_exclude_unsafe_or_unavailable_links():
    slots = appointments.parse_slots(SCHEDULE, "傅再生", "2026-10-18")
    assert [slot.session for slot in slots] == ["上午", "下午", "夜診"]
    assert slots[0].eligibility.startswith("初診可掛")
    assert slots[1].eligibility.startswith("科初診可掛")
    assert slots[2].eligibility.startswith("一般掛號")
    assert all(slot.registration_url.startswith(appointments.BASE_URL) for slot in slots)


def mock_pages(monkeypatch, failed_weeks=(), schedule=SCHEDULE):
    calls = []

    def fake_fetch(url, cache_window):
        calls.append(url)
        if url == appointments.REGISTRATION_URL:
            return f'<a href="{DEPARTMENT}">骨科</a>', datetime.now(timezone.utc)
        if any(url.endswith(f"WEEK={week}") for week in failed_weeks):
            raise OSError("timeout")
        return schedule, datetime.now(timezone.utc)

    monkeypatch.setattr(appointments, "fetch_page", fake_fetch)
    return calls


def test_lookup_discovers_department_queries_four_weeks_and_deduplicates(monkeypatch):
    calls = mock_pages(monkeypatch)
    result = appointments.get_appointments(DOCTOR)
    assert result.status == "available"
    assert len(result.slots) == 3
    assert result.checked_at is not None
    assert result.schedule_urls == [appointments.BASE_URL + DEPARTMENT]
    assert {url.split("WEEK=")[-1] for url in calls[1:]} == {"1", "2", "3", "4"}


def test_partial_failure_keeps_successful_slots(monkeypatch):
    mock_pages(monkeypatch, failed_weeks=(2,))
    result = appointments.get_appointments(DOCTOR)
    assert result.status == "partial"
    assert result.slots


def test_total_failure_is_not_reported_as_no_slots(monkeypatch):
    mock_pages(monkeypatch, failed_weeks=(1, 2, 3, 4))
    result = appointments.get_appointments(DOCTOR)
    assert result.status == "unavailable"
    assert result.checked_at is None
    assert result.registration_url == appointments.REGISTRATION_URL


def test_no_slots_and_changed_page_format_are_distinct(monkeypatch):
    mock_pages(monkeypatch, schedule="看診醫師時間表 掛號")
    assert appointments.get_appointments(DOCTOR).status == "no_slots"
    mock_pages(monkeypatch, schedule="網站維護中 掛號")
    assert appointments.get_appointments(DOCTOR).status == "unavailable"


def test_index_failure_falls_back_to_official_site(monkeypatch):
    def fail_fetch(*args):
        raise OSError("timeout")

    monkeypatch.setattr(appointments, "fetch_page", fail_fetch)
    result = appointments.get_appointments(DOCTOR)
    assert result.status == "unavailable"
    assert result.registration_url == appointments.REGISTRATION_URL


def test_unsupported_hospital_never_fetches(monkeypatch):
    calls = mock_pages(monkeypatch)
    result = appointments.get_appointments({**DOCTOR, "doctor_id": "OTHER_001"})
    assert result.status == "unsupported"
    assert calls == []


def test_appointments_endpoint_uses_known_doctor_and_returns_404_for_unknown(monkeypatch):
    mock_pages(monkeypatch)
    client = TestClient(app)
    response = client.get(f'/api/doctors/{DOCTOR["doctor_id"]}/appointments')
    assert response.status_code == 200
    assert response.json()["status"] == "available"
    assert client.get("/api/doctors/unknown/appointments").status_code == 404


def test_search_excludes_initial_only_and_outside_preferences(monkeypatch):
    mock_pages(monkeypatch)
    client = TestClient(app)
    url = f'/api/doctors/{DOCTOR["doctor_id"]}/appointments/search'
    result = client.post(url, json={"patient_type": "returning", "sessions": ["夜診"]})
    assert result.status_code == 200
    assert [slot["session"] for slot in result.json()["slots"]] == ["夜診"]
    result = client.post(url, json={"patient_type": "returning", "sessions": ["上午"]})
    assert result.json()["slots"] == []
    assert result.json()["status"] == "no_slots"
