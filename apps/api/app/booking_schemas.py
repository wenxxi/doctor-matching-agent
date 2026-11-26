from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, SecretStr, model_validator


class BookingStartRequest(BaseModel):
    doctor_id: str = Field(max_length=100)
    registration_url: str = Field(max_length=400)
    task_id: UUID | None = None


class BookingPatientRequest(BaseModel):
    id_type: Literal["1", "2", "3", "4", "5"]
    id_number: SecretStr
    birthday: date
    verification: SecretStr
    consent: Literal[True]

    @model_validator(mode="after")
    def validate_patient(self):
        identifier = self.id_number.get_secret_value()
        captcha = self.verification.get_secret_value()
        if not 4 <= len(identifier) <= 20 or not identifier.isascii() or not identifier.isalnum():
            raise ValueError("請確認證號格式")
        if not 1 <= len(captcha) <= 12 or not captcha.isascii() or not captcha.isalnum():
            raise ValueError("請確認驗證碼格式")
        if self.birthday > date.today() or self.birthday.year < 1900:
            raise ValueError("請確認出生日期")
        return self


class BookingContinueRequest(BaseModel):
    step_token: str = Field(min_length=20, max_length=100)
    fields: dict[str, str] = Field(default_factory=dict, max_length=80)
    consent: Literal[True]


class BookingField(BaseModel):
    name: str
    label: str
    kind: Literal["text", "date", "email", "tel", "number", "select", "checkbox"] = "text"
    value: str = ""
    required: bool = False
    options: list[dict[str, str]] = Field(default_factory=list)


class BookingStateResponse(BaseModel):
    status: Literal[
        "awaiting_patient", "captcha_error", "awaiting_confirmation", "confirmed",
        "needs_official", "unknown", "rejected", "closed",
    ]
    message: str
    token: str | None = None
    expires_at: datetime | None = None
    captcha_image: str | None = None
    fields: list[BookingField] = Field(default_factory=list)
    receipt_number: str | None = None
    step_token: str | None = None
