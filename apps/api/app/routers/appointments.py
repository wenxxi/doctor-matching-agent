from fastapi import APIRouter, HTTPException

from app.schemas import AppointmentsResponse
from app.services.appointments import get_appointments
from app.services.processed_data import load_doctors


router = APIRouter(prefix="/api/doctors", tags=["appointments"])


@router.get("/{doctor_id}/appointments", response_model=AppointmentsResponse)
def doctor_appointments(doctor_id: str) -> AppointmentsResponse:
    doctor = next((row for row in load_doctors() if row["doctor_id"] == doctor_id), None)
    if doctor is None:
        raise HTTPException(status_code=404, detail="Doctor not found")
    return get_appointments(doctor)
