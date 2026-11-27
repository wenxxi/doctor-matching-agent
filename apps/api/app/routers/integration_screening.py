from typing import Literal
import os

from fastapi import APIRouter, HTTPException

from app.services.hospital_screening import screen_candidate

router = APIRouter(prefix="/api/integrations/hospital-screening", tags=["integration-screening"])


@router.get("/{candidate_id}")
def hospital_screening(candidate_id: Literal["mmh_taipei_orthopedics", "ntuh_orthopedics", "femh_orthopedics", "skh_registration"]):
    """Fixed public-source checks, cached ten minutes. No patient input or registration submission."""
    if os.getenv("ENABLE_HOSPITAL_SCREENING") != "true":
        raise HTTPException(404, "研究檢測入口尚未啟用。")
    return screen_candidate(candidate_id)
