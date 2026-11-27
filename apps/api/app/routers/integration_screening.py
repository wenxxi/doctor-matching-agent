from typing import Literal

from fastapi import APIRouter

from app.services.hospital_screening import screen_candidate

router = APIRouter(prefix="/api/integrations/hospital-screening", tags=["integration-screening"])


@router.get("/{candidate_id}")
def hospital_screening(candidate_id: Literal["mmh_taipei_orthopedics", "ntuh_orthopedics", "femh_orthopedics", "skh_registration"]):
    """Fixed public-source checks, cached ten minutes. No patient input or registration submission."""
    return screen_candidate(candidate_id)
