from fastapi import APIRouter, HTTPException

from app.schemas import AppointmentsResponse, AppointmentPreparationRequest, AppointmentPreparationResponse
from app.services.appointment_agent import matches_preferences, prepare_appointment
from app.services.appointments import get_appointments
from app.services.processed_data import load_doctors


router = APIRouter(prefix="/api/doctors", tags=["appointments"])


@router.get("/{doctor_id}/appointments", response_model=AppointmentsResponse)
def doctor_appointments(doctor_id: str) -> AppointmentsResponse:
    doctor = next((row for row in load_doctors() if row["doctor_id"] == doctor_id), None)
    if doctor is None:
        raise HTTPException(status_code=404, detail="Doctor not found")
    return get_appointments(doctor)


@router.post("/{doctor_id}/appointments/search", response_model=AppointmentsResponse)
def search_doctor_appointments(doctor_id: str, request: AppointmentPreparationRequest) -> AppointmentsResponse:
    doctor = next((row for row in load_doctors() if row["doctor_id"] == doctor_id), None)
    if doctor is None:
        raise HTTPException(status_code=404, detail="Doctor not found")
    if doctor_id.startswith("TPVGH_MAIN_"):
        from app.services.tpvgh import get_appointments as tpvgh_appointments
        if request.patient_type not in {"first_visit", "returning"}:
            return AppointmentsResponse(doctor_id=doctor_id, slots=[], status="no_slots", registration_url=None,
                schedule_urls=[], checked_at=None, message="榮總需要先確認全院初診或複診，請調整患者類型。")
        snapshot = tpvgh_appointments(doctor, request.patient_type)
    else:
        snapshot = get_appointments(doctor)
    snapshot.slots = [slot for slot in snapshot.slots if matches_preferences(slot, request)]
    if snapshot.status == "available" and not snapshot.slots:
        snapshot.status = "no_slots"
        snapshot.message = "沒有符合目前日期、星期、時段與初複診條件的時段。"
    return snapshot


@router.post("/{doctor_id}/appointments/prepare", response_model=AppointmentPreparationResponse)
def prepare_doctor_appointment(
    doctor_id: str, request: AppointmentPreparationRequest,
) -> AppointmentPreparationResponse:
    doctor = next((row for row in load_doctors() if row["doctor_id"] == doctor_id), None)
    if doctor is None:
        raise HTTPException(status_code=404, detail="Doctor not found")
    return prepare_appointment(doctor, request)
