from fastapi import APIRouter, Depends, Header, HTTPException, Response

from app.booking_schemas import (
    BookingContinueRequest, BookingPatientRequest, BookingStartRequest, BookingStateResponse,
)
from app.services import booking
from app.services.processed_data import load_doctors


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


@router.post("/sessions", response_model=BookingStateResponse)
def start_session(request: BookingStartRequest):
    doctor = next((row for row in load_doctors() if row["doctor_id"] == request.doctor_id), None)
    if doctor is None:
        raise HTTPException(status_code=404, detail="Doctor not found")
    return booking_call(booking.start_booking, doctor, request.registration_url)


@router.post("/submit", response_model=BookingStateResponse)
def submit_patient(request: BookingPatientRequest, x_booking_token: str = Header(min_length=20, max_length=100)):
    return booking_call(booking.submit_patient, x_booking_token, request)


@router.post("/continue", response_model=BookingStateResponse)
def continue_booking(request: BookingContinueRequest, x_booking_token: str = Header(min_length=20, max_length=100)):
    return booking_call(booking.continue_booking, x_booking_token, request)


@router.post("/captcha", response_model=BookingStateResponse)
def refresh_captcha(x_booking_token: str = Header(min_length=20, max_length=100)):
    return booking_call(booking.refresh_captcha, x_booking_token)


@router.delete("/session", response_model=BookingStateResponse)
def close_session(x_booking_token: str = Header(min_length=20, max_length=100)):
    return booking.close_booking(x_booking_token)
