from datetime import date, datetime, timezone

from app.schemas import AppointmentPreparationRequest, AppointmentSlotResponse, AppointmentsResponse, RecommendedDoctorResponse
from app.services import appointment_agent, available_doctors


def candidate(index):
    return RecommendedDoctorResponse(
        doctor_id=f"CGMH_LINKOU_TEST_{index}", doctor_name_zh=f"測試醫師{index}",
        hospital_zh="林口長庚", department_zh="骨科部", subdepartment_zh="", specialty_raw_zh="膝蓋",
        source_url="", score=10 - index, matched_concepts=[], reasons=[],
    )


def hospital(monkeypatch, candidates, slots_by_id, broken=()):
    monkeypatch.setattr(available_doctors, "load_doctors", lambda: [item.model_dump() for item in candidates])

    def snapshot(doctor):
        return AppointmentsResponse(
            doctor_id=doctor["doctor_id"], status="available", registration_url=None,
            schedule_urls=[], checked_at=datetime.now(timezone.utc),
            slots=slots_by_id.get(doctor["doctor_id"], []), message="test",
        )

    def live(url):
        if url in broken:
            return "名額已滿，無法掛號", datetime.now(timezone.utc)
        doctor = next(item for item in candidates if item.doctor_id in url)
        selected = next(slot for slot in slots_by_id[doctor.doctor_id] if slot.registration_url == url)
        return (f'<p>{doctor.doctor_name_zh} {selected.date.replace("-", "/")} {selected.session}</p>'
                f'<form method="post" action="{url.replace("/Checkin/", "/CheckinConfirm/")}">'
                '<input name="idNumber"><input name="verification"></form>'), datetime.now(timezone.utc)

    monkeypatch.setattr(appointment_agent, "get_appointments", snapshot)
    monkeypatch.setattr(appointment_agent, "fetch_live_page", live)


def slot(doctor, eligibility="一般掛號", date="2099-10-19", session="下午"):
    return AppointmentSlotResponse(
        date=date, session=session, eligibility=eligibility,
        registration_url=f"https://register.cgmh.org.tw/Checkin/3/{doctor.doctor_id}/{date.replace('-', '')}/1/2",
    )


def test_filters_full_and_first_visit_only_doctors_then_backfills_by_relevance(monkeypatch):
    doctors = [candidate(i) for i in range(6)]
    slots = {doctor.doctor_id: [slot(doctor)] for doctor in doctors}
    slots[doctors[0].doctor_id] = []
    slots[doctors[1].doctor_id] = [slot(doctors[1], "初診可掛（從未在本院看診）")]
    hospital(monkeypatch, doctors, slots)
    selected, incomplete = available_doctors.filter_available_doctors(
        doctors, AppointmentPreparationRequest(patient_type="returning"), 3,
    )
    assert [doctor.doctor_id for doctor in selected[:3]] == [doctor.doctor_id for doctor in doctors[2:5]]
    assert all(doctor.availability.verified_at for doctor in selected)
    assert selected[0].score == doctors[2].score
    assert incomplete is False


def test_rejects_schedule_link_when_patient_form_is_no_longer_available(monkeypatch):
    doctors = [candidate(i) for i in range(2)]
    slots = {doctor.doctor_id: [slot(doctor)] for doctor in doctors}
    hospital(monkeypatch, doctors, slots, broken=[slots[doctors[0].doctor_id][0].registration_url])
    selected, incomplete = available_doctors.filter_available_doctors(
        doctors, AppointmentPreparationRequest(patient_type="unknown"), 3,
    )
    assert [doctor.doctor_id for doctor in selected] == [doctors[1].doctor_id]
    assert incomplete is True


def test_uses_exact_dates_sessions_weekdays_and_patient_type(monkeypatch):
    doctor = candidate(0)
    first_only = slot(doctor, "科初診可掛（半年內未看過該科）")
    hospital(monkeypatch, [doctor], {doctor.doctor_id: [first_only]})
    request = AppointmentPreparationRequest(patient_type="department_first", sessions=["下午"],
                                            date_from="2099-10-19", date_to="2099-10-19")
    assert available_doctors.filter_available_doctors([doctor], request, 3)[0]
    for changes in ({"patient_type": "returning"}, {"sessions": ["上午"]}, {"date_to": date(2099, 10, 18), "date_from": None},
                    {"weekdays": [(datetime.fromisoformat(first_only.date).weekday() + 1) % 7]}):
        assert available_doctors.filter_available_doctors([doctor], request.model_copy(update=changes), 3)[0] == []


def test_unreachable_hospital_is_excluded_instead_of_claiming_no_capacity(monkeypatch):
    doctor = candidate(0)
    hospital(monkeypatch, [doctor], {doctor.doctor_id: [slot(doctor)]})

    def fail(url):
        raise OSError("timeout")

    monkeypatch.setattr(appointment_agent, "fetch_live_page", fail)
    selected, incomplete = available_doctors.filter_available_doctors([doctor], AppointmentPreparationRequest(patient_type="unknown"), 3)
    assert selected == []
    assert incomplete is True
