from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, Field, model_validator


PatientType = Literal["first_visit", "department_first", "returning", "unknown"]
SessionName = Literal["上午", "下午", "夜診"]
Weekday = Annotated[int, Field(ge=0, le=6)]


class IntakeState(BaseModel):
    clinical_query: str = Field(default="", max_length=2000)
    hospital: str = Field(default="林口長庚", max_length=60)
    both_hospitals_patient_type_confirmed: bool = False
    patient_type: PatientType | None = None
    date_from: date | None = None
    date_to: date | None = None
    date_range_known: bool = False
    sessions: list[SessionName] | None = Field(default=None, min_length=1, max_length=3)
    weekdays: list[Weekday] = Field(default_factory=lambda: list(range(7)), max_length=7)

    @model_validator(mode="after")
    def validate_dates(self):
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise ValueError("開始日期不可晚於結束日期")
        return self


class IntakePreferences(BaseModel):
    """Fixed choices supplied alongside free text; never accepts clinical memory."""
    model_config = {"extra": "forbid"}

    hospital: Literal["林口長庚", "台北榮總", "兩院皆可"] = "林口長庚"
    patient_type: PatientType = "unknown"
    date_window: Literal["any", "next_week", "two_weeks"] = "any"
    sessions: list[SessionName] = Field(default_factory=lambda: ["上午", "下午", "夜診"], min_length=1, max_length=3)


class IntakeRequest(BaseModel):
    message: str = Field(min_length=1, max_length=1000)
    state: IntakeState = Field(default_factory=IntakeState)
    intake_preferences: IntakePreferences | None = None


class IntakeResponse(BaseModel):
    state: IntakeState
    reply: str
    question: str | None = None
    quick_replies: list[str] = Field(default_factory=list)
    ready: bool = False
    extraction_method: Literal["openai", "local"] = "local"


class IntakePatch(BaseModel):
    model_config = {"extra": "forbid"}

    updated_fields: list[Literal["clinical_query", "hospital", "patient_type", "date_range", "sessions", "weekdays"]]
    clinical_query: str | None
    hospital: str | None
    patient_type: PatientType | None
    date_from: date | None
    date_to: date | None
    sessions: list[SessionName] | None
    weekdays: list[Weekday] | None
