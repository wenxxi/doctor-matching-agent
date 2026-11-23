from fastapi import APIRouter, Response

from app.intake_schemas import IntakeRequest, IntakeResponse
from app.services.intake import intake_turn


router = APIRouter(prefix="/api/intake", tags=["intake"])


@router.post("/chat", response_model=IntakeResponse)
def chat(request: IntakeRequest, response: Response) -> IntakeResponse:
    response.headers["Cache-Control"] = "no-store, private"
    return intake_turn(request)
