from pathlib import Path
from types import SimpleNamespace

import pytest

from app.schemas import AppointmentPreparationRequest
from app.services import tpvgh, booking, doctor_relevance
from app.services.hospitals import matches_hospital
from app.services.intake import pending_question, local_updates
from app.services import intake
from app.intake_schemas import IntakeRequest
from app.intake_schemas import IntakeState
from datetime import date
from urllib.error import HTTPError


DOCTOR = {"doctor_id": "TPVGH_MAIN_ORTHO_T807", "doctor_name_zh": "蔡尚聞", "department_zh": "骨科部", "hospital_zh": "臺北榮民總醫院"}
URL = "https://www6.vghtpe.gov.tw/reg/docTimetable.do?docid=DOC2207G&type=return"


def table_row(name="蔡尚聞", status="可掛號", key="2099120105302", disabled="", session="上午"):
    return f'<tr><td>{status}<input type=radio name=regKey value={key} {disabled}><input name=regDocName value="{name}"><input name=regDate value="2099-12-01(二) {session}"></td></tr>'


def page(rows):
    return '<form name="oregForm"><input name=type value=return><input name=pid><input name=pbirth_mm><input name=pbirth_dd>' + rows + '</form>'


def test_slots_require_open_choice_matching_doctor_date_and_patient_form():
    html = page(table_row() + table_row(name="其他醫師") + table_row(status="額滿") + table_row(disabled="disabled") + table_row(key="bad"))
    slots = tpvgh.parse_slots(html, "蔡尚聞", URL, "returning", "2099-11-30")
    assert len(slots) == 1
    assert slots[0].date == "2099-12-01" and slots[0].booking_mode == "official_handoff"
    assert tpvgh.parse_slots(page(table_row()), "蔡尚聞", URL, "returning", "2100-01-01") == []
    with pytest.raises(ValueError):
        tpvgh.parse_slots(table_row(), "蔡尚聞", URL, "returning", "2099-11-30")
    with pytest.raises(ValueError):
        tpvgh.parse_slots(html, "蔡尚聞", URL, "first_visit", "2099-11-30")


def test_unconfirmed_tpvgh_eligibility_does_not_query_or_infer_returning(monkeypatch):
    monkeypatch.setattr(tpvgh, "get_appointments", lambda *args, **kwargs: pytest.fail("Must clarify first"))
    for patient_type in ("unknown", "department_first"):
        assert tpvgh.prepare(DOCTOR, AppointmentPreparationRequest(patient_type=patient_type)).selected_slot is None
        state = IntakeState(clinical_query="膝蓋痛", hospital="台北榮總", patient_type=patient_type)
        assert pending_question(state, date.today()) == "tpvgh_patient_type"


def test_hospital_choice_is_preserved_and_limits_candidate_recall(monkeypatch):
    assert local_updates("改成台北榮總", IntakeState(), date.today())["hospital"] == "台北榮總"
    assert local_updates("兩院皆可", IntakeState(), date.today())["hospital"] == "兩院皆可"
    assert matches_hospital(DOCTOR, "台北榮總")
    assert not matches_hospital(DOCTOR, "林口長庚")
    monkeypatch.setattr(doctor_relevance, "rank_doctors", lambda *a, **kw: [])
    monkeypatch.setattr(doctor_relevance, "load_doctors", lambda: [{**DOCTOR, "specialty_raw_zh": "膝關節", "subdepartment_zh": "", "source_url": ""}])
    assert doctor_relevance.retrieve_candidates("膝關節", [], None, hospital="林口長庚")[0] == []


def test_embedded_booking_cannot_receive_a_tpvgh_patient_submission():
    with pytest.raises(booking.BookingError, match="院方頁面"):
        booking.start_booking(DOCTOR, URL)


def test_profile_parser_uses_specialty_not_publications_or_commented_heading():
    html = '<main><!-- <h2>old</h2> --><h2>蔡尚聞 (Shang-Wen TSAI)</h2><a href="docTimetable.do?docid=DOC2207G">掛號</a><!-- 醫療專長 --><li><div>醫療專長</div><ol><li>人工膝關節置換</li></ol></li><!-- 證照 --><p>脊椎研究論文</p>'
    assert tpvgh.parse_profile(html) == ("蔡尚聞", "人工膝關節置換", "DOC2207G")
    assert tpvgh.parse_profile(html.replace("蔡尚聞", "馬 旭"))[0] == "馬旭"


def test_hospital_change_resets_previous_visit_history_and_both_requires_confirmation(monkeypatch):
    monkeypatch.setattr(intake, "get_openai_settings", lambda: SimpleNamespace(api_key=None))
    state = IntakeState(clinical_query="膝蓋痛", hospital="林口長庚", patient_type="returning", date_range_known=True, sessions=["上午"])
    response = intake.intake_turn(IntakeRequest(message="改成台北榮總", state=state))
    assert response.state.patient_type is None
    assert not response.ready
    response = intake.intake_turn(IntakeRequest(message="兩院皆可", state=state))
    assert response.question == "both_patient_type"
    response = intake.intake_turn(IntakeRequest(message="兩院都是複診", state=response.state))
    assert response.state.both_hospitals_patient_type_confirmed and response.ready
    assert local_updates("改成林口長庚，不要榮總", state, date.today())["hospital"] == "林口長庚"


def test_both_hospitals_have_recall_space_before_model_review(monkeypatch):
    from app.schemas import RecommendedDoctorResponse
    def rank(*args, hospital=None, **kwargs):
        return [RecommendedDoctorResponse(doctor_id=hospital + str(i), doctor_name_zh="測試", hospital_zh=hospital,
            department_zh="骨科部", subdepartment_zh="", specialty_raw_zh="膝關節", source_url="", score=1, matched_concepts=[], reasons=[]) for i in range(12)]
    monkeypatch.setattr(doctor_relevance, "rank_doctors", rank)
    monkeypatch.setattr(doctor_relevance, "load_doctors", lambda: [])
    initial, _ = doctor_relevance.retrieve_candidates("膝蓋痛", [], None, hospital="兩院皆可")
    expanded, _ = doctor_relevance.retrieve_candidates("膝蓋痛", [], None, hospital="兩院皆可", expanded=True)
    assert {row.hospital_zh for row in initial} == {"林口長庚", "台北榮總"}
    assert {row.doctor_id for row in initial}.isdisjoint(row.doctor_id for row in expanded)


def test_provider_http_failure_is_classified_without_exposing_upstream_details(monkeypatch):
    monkeypatch.setattr(tpvgh, "BLOCKED_UNTIL", 0.0)
    monkeypatch.setattr(tpvgh, "BLOCKED_EVIDENCE", {})
    monkeypatch.setattr(tpvgh, "load_provider_metadata", lambda: {DOCTOR["doctor_id"]: {"registration_doctor_id": "DOC2207G"}})
    def denied(url):
        raise HTTPError(url, 403, "private upstream detail", {}, None)
    monkeypatch.setattr(tpvgh, "public_page", denied)
    result = tpvgh.get_appointments(DOCTOR)
    assert result.status == "unavailable" and result.slots == []
    assert result.failure_code == "provider_http_error" and result.provider_http_status == 403
    assert "private upstream detail" not in result.model_dump_json()
    monkeypatch.setattr(tpvgh, "public_page", lambda url: pytest.fail("403 must trigger a cooldown instead of repeatedly querying"))
    second = tpvgh.get_appointments(DOCTOR)
    assert second.provider_http_status == 403 and second.slots == []
    assert second.failure_evidence["evidence_origin"] == "cached_denial"
