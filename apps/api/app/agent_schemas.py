from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.intake_schemas import IntakePreferences, IntakeResponse, IntakeState
from app.schemas import AppointmentPreparationRequest, AppointmentPreparationResponse, RecommendationResponse


class AgentSessionResponse(BaseModel):
    token: str


class CaseCreateRequest(BaseModel):
    title: str = Field(default="新的就醫個案", min_length=1, max_length=120)
    subject_label: str = Field(default="自己", min_length=1, max_length=60)
    consent: bool


class CaseSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    subject_label: str
    status: str
    updated_at: datetime


class AgentMessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    role: str
    content: str


class AgentTaskResponse(BaseModel):
    id: UUID
    status: str
    version: int
    intake: IntakeState = Field(default_factory=IntakeState)
    intake_response: IntakeResponse | None = None
    recommendation: RecommendationResponse | None = None
    preparation: AppointmentPreparationResponse | None = None
    trace: list[dict[str, str]] = Field(default_factory=list)
    booking_status: str | None = None
    booking_receipt_number: str | None = None


class CaseDetailResponse(BaseModel):
    case: CaseSummary
    task: AgentTaskResponse
    messages: list[AgentMessageResponse]
    messages_cursor: UUID | None = None


class CaseMessagesPage(BaseModel):
    messages: list[AgentMessageResponse]
    next_cursor: UUID | None = None


class AgentTurnRequest(BaseModel):
    message: str = Field(min_length=1, max_length=1000)
    intake_preferences: IntakePreferences | None = None
    operation_id: UUID
    expected_version: int = Field(ge=0)


class AgentPrepareRequest(BaseModel):
    doctor_id: str = Field(max_length=100)
    preferences: AppointmentPreparationRequest
    operation_id: UUID
    expected_version: int = Field(ge=0)
