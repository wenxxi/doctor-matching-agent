from fastapi import APIRouter, Depends, Header, HTTPException, Response

from app.booking_schemas import (
    BookingContinueRequest, BookingPatientRequest, BookingStartRequest, BookingStateResponse,
)
from app.services import booking
from app.services.processed_data import load_doctors
from app.services.agent_storage import AGENT_STORAGE_ERRORS, initialize_agent_storage
from app.services.cases import authenticate_owner, observe_booking, validate_booking_task
from app.agent_models import AgentTask, CareCase
from sqlalchemy.orm import Session


def private_response(response: Response):
    response.headers["Cache-Control"] = "no-store, private"
    response.headers["Pragma"] = "no-cache"


router = APIRouter(prefix="/api/booking", tags=["booking"], dependencies=[Depends(private_response)])


def booking_call(operation, *args):
    try:
        return operation(*args)
    except booking.BookingError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    except (OSError, ValueError):
        raise HTTPException(status_code=502, detail="暫時無法取得院方掛號資料，請稍後重試。") from None


def check_linked_booking(token):
    current = booking_call(booking.get_session, token)
    if current.task_id is None or current.status in {"confirmed", "unknown", "needs_official", "rejected"}:
        return current
    try:
        with Session(initialize_agent_storage()) as session:
            task = session.get(AgentTask, current.task_id)
            case = session.get(CareCase, task.case_id) if task else None
            if task is None or case is None or case.status != "active" or task.status != "awaiting_patient" or task.version != current.task_version:
                raise HTTPException(status_code=409, detail="個案條件已更新或任務已關閉，此掛號表單不可再送出。")
    except AGENT_STORAGE_ERRORS:
        raise HTTPException(status_code=503, detail="暫時無法確認個案狀態，尚未送出院方。") from None
    return current


def linked_call(operation, token, *args, submission=True):
    current = check_linked_booking(token)
    linked = current.task_id is not None and current.status not in {"confirmed", "unknown", "needs_official", "rejected"}
    if linked and submission:
        try:
            if not observe_booking(current.task_id, current.task_version, "submitting"):
                raise HTTPException(status_code=409, detail="個案條件或進度已更新，尚未送出院方，請重新載入。")
        except AGENT_STORAGE_ERRORS:
            raise HTTPException(status_code=503, detail="無法保存任務進度，尚未送出院方。") from None
    try:
        return booking_call(operation, token, *args)
    finally:
        if current.task_id is not None:
            try:
                observe_booking(current.task_id, current.task_version, current.status, current.response.receipt_number if current.response else None)
            except AGENT_STORAGE_ERRORS:
                pass


@router.post("/sessions", response_model=BookingStateResponse)
def start_session(request: BookingStartRequest, x_agent_token: str | None = Header(default=None, max_length=100)):
    doctor = next((row for row in load_doctors() if row["doctor_id"] == request.doctor_id), None)
    if doctor is None:
        raise HTTPException(status_code=404, detail="Doctor not found")
    task_id = task_version = None
    if request.task_id is not None:
        try:
            with Session(initialize_agent_storage()) as session:
                owner = authenticate_owner(session, x_agent_token)
                task = validate_booking_task(session, owner, request.task_id, request.registration_url)
                task_id, task_version = task.id, task.version
        except AGENT_STORAGE_ERRORS:
            raise HTTPException(status_code=503, detail="個案記憶暫時無法存取，尚未開始掛號。") from None
    response = booking_call(booking.start_booking, doctor, request.registration_url)
    current = booking.get_session(response.token)
    current.task_id, current.task_version = task_id, task_version
    if task_id is not None:
        if not observe_booking(task_id, task_version, "awaiting_patient"):
            booking.close_booking(response.token)
            raise HTTPException(status_code=409, detail="個案條件已更新，請重新載入。")
    return response


@router.post("/submit", response_model=BookingStateResponse)
def submit_patient(request: BookingPatientRequest, x_booking_token: str = Header(min_length=20, max_length=100)):
    return linked_call(booking.submit_patient, x_booking_token, request)


@router.post("/continue", response_model=BookingStateResponse)
def continue_booking(request: BookingContinueRequest, x_booking_token: str = Header(min_length=20, max_length=100)):
    return linked_call(booking.continue_booking, x_booking_token, request)


@router.post("/captcha", response_model=BookingStateResponse)
def refresh_captcha(x_booking_token: str = Header(min_length=20, max_length=100)):
    return linked_call(booking.refresh_captcha, x_booking_token, submission=False)


@router.delete("/session", response_model=BookingStateResponse)
def close_session(x_booking_token: str = Header(min_length=20, max_length=100)):
    return booking.close_booking(x_booking_token)
