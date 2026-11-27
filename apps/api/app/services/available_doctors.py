from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from app.schemas import AppointmentPreparationRequest, DoctorAvailability, RecommendedDoctorResponse
from app.services.appointment_agent import prepare_appointment
from app.services.processed_data import load_doctors


@dataclass
class AvailabilityResult:
    doctors: list[RecommendedDoctorResponse]
    incomplete: bool
    failures: list[dict] = field(default_factory=list)

    def __iter__(self):
        # Preserve the existing two-value caller contract.
        yield self.doctors
        yield self.incomplete

    def __getitem__(self, index):
        return (self.doctors, self.incomplete)[index]

    def __len__(self):
        return 2


def filter_available_doctors(
    candidates: list[RecommendedDoctorResponse], preferences: AppointmentPreparationRequest, limit: int,
) -> AvailabilityResult:
    """Keep only doctors with a matching slot whose patient form was verified.

    Check small batches in ranking order. Only public GET requests are made;
    verification never reserves a slot or submits a registration.
    """
    doctors = {row["doctor_id"]: row for row in load_doctors()}
    selected = []
    incomplete = False
    failures = []

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
                    if preparation is not None and preparation.failure_code:
                        failure = {"hospital": candidate.hospital_zh, "code": preparation.failure_code,
                                   "http_status": preparation.provider_http_status}
                        if failure not in failures:
                            failures.append(failure)
            if len(selected) >= limit:
                break
    return AvailabilityResult(selected, incomplete, failures)
