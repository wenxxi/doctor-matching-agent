from concurrent.futures import ThreadPoolExecutor

from app.schemas import AppointmentPreparationRequest, DoctorAvailability, RecommendedDoctorResponse
from app.services.appointment_agent import prepare_appointment
from app.services.processed_data import load_doctors


def filter_available_doctors(
    candidates: list[RecommendedDoctorResponse], preferences: AppointmentPreparationRequest, limit: int,
) -> tuple[list[RecommendedDoctorResponse], bool]:
    """Keep only doctors with a matching slot whose patient form was verified.

    Check small batches in ranking order. Only public GET requests are made;
    verification never reserves a slot or submits a registration.
    """
    doctors = {row["doctor_id"]: row for row in load_doctors()}
    selected = []
    incomplete = False

    def verify(candidate):
        doctor = doctors.get(candidate.doctor_id)
        if doctor is None:
            return None
        return prepare_appointment(doctor, preferences)

    with ThreadPoolExecutor(max_workers=3) as executor:
        for start in range(0, min(len(candidates), 12), 3):
            batch = candidates[start:start + 3]
            for candidate, preparation in zip(batch, executor.map(verify, batch)):
                if (preparation is not None and preparation.status in {"awaiting_patient", "official_handoff"}
                        and preparation.selected_slot is not None and preparation.verified_at is not None):
                    selected.append(candidate.model_copy(update={"availability": DoctorAvailability(
                        selected_slot=preparation.selected_slot, verified_at=preparation.verified_at,
                    )}))
                elif preparation is None or preparation.status in {"unavailable", "retry_needed"}:
                    incomplete = True
            if len(selected) >= limit:
                break
    return selected, incomplete
