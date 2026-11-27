from datetime import date, datetime
from uuid import UUID
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class DoctorExpertiseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    keyword: str
    canonical_keyword: str | None
    category: str | None


class DoctorResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    hospital: str
    campus: str | None
    department: str
    subspecialty: str | None
    title: str | None
    profile_url: str | None
    registration_url: str | None
    bio: str | None
    raw_expertise: str | None
    created_at: datetime
    updated_at: datetime
    expertise: list[DoctorExpertiseResponse]


class AppointmentSlotResponse(BaseModel):
    date: str
    session: str
    eligibility: str
    registration_url: str
    provider_slot_id: str | None = None
    booking_mode: Literal["embedded", "official_handoff"] = "embedded"


class DoctorAvailability(BaseModel):
    selected_slot: AppointmentSlotResponse
    verified_at: datetime


class ConceptExtractionRequest(BaseModel):
    query: str


class MatchedConceptResponse(BaseModel):
    concept_id: str
    canonical_name_zh: str
    canonical_name_en: str
    category: str
    matched_terms: list[str]
    assertion: str = "reported"
    patient_evidence: str | None = None


class RankingDebugResponse(BaseModel):
    weighted_evidence_score: float
    distinct_concepts_bonus: float
    generic_concept_penalty: float
    department_intent_adjustment: float
    matched_concept_count: int


class RecommendedDoctorResponse(BaseModel):
    doctor_id: str
    doctor_name_zh: str
    hospital_zh: str
    department_zh: str
    subdepartment_zh: str
    specialty_raw_zh: str
    source_url: str
    registration_url: str | None = None
    score: float
    matched_concepts: list[MatchedConceptResponse]
    reasons: list[str]
    ranking_debug: RankingDebugResponse | None = None
    llm_reason_zh: str | None = None
    availability: DoctorAvailability | None = None
    specialty_evidence: str | None = None
    relevance_summary: str | None = None


class RecommendationResponse(BaseModel):
    query: str
    concept_extraction_method: str
    fallback_used: bool
    department_intent: str | None = None
    department_intent_confidence: float = 0.0
    candidate_concepts_count: int | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    reason_input_tokens: int | None = None
    reason_output_tokens: int | None = None
    matched_concepts: list[MatchedConceptResponse]
    recommended_doctors: list[RecommendedDoctorResponse]
    message: str | None = None
    ranking_method: str = "rule_fallback"
    assessment_summary: str | None = None
    clarification_question: str | None = None
    decision_trace: list[dict[str, str]] = Field(default_factory=list)


class ConceptExtractionResponse(BaseModel):
    query: str
    extractor: str
    fallback_used: bool
    candidate_concepts_count: int | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    matched_concepts: list[MatchedConceptResponse]


class AppointmentsResponse(BaseModel):
    doctor_id: str
    status: Literal["available", "no_slots", "partial", "unavailable", "unsupported"]
    registration_url: str | None
    schedule_urls: list[str]
    checked_at: datetime | None
    slots: list[AppointmentSlotResponse]
    message: str


class AppointmentPreparationRequest(BaseModel):
    patient_type: Literal["first_visit", "department_first", "returning", "unknown"]
    date_from: date | None = None
    date_to: date | None = None
    sessions: list[Literal["上午", "下午", "夜診"]] = Field(
        default_factory=lambda: ["上午", "下午", "夜診"], min_length=1, max_length=3,
    )
    weekdays: list[Annotated[int, Field(ge=0, le=6)]] = Field(
        default_factory=lambda: list(range(7)), min_length=1, max_length=7,
    )

    @model_validator(mode="after")
    def validate_date_range(self):
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise ValueError("開始日期不可晚於結束日期")
        return self


class AppointmentPreparationResponse(BaseModel):
    doctor_id: str
    status: Literal["awaiting_patient", "official_handoff", "no_match", "unavailable", "retry_needed"]
    booking_mode: Literal["embedded", "official_handoff"] = "embedded"
    selected_slot: AppointmentSlotResponse | None = None
    verified_at: datetime | None = None
    candidate_count: int = 0
    attempted_count: int = 0
    steps: list[str] = Field(default_factory=list)
    message: str


class RecommendationRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    hospital: Literal["林口長庚", "台北榮總", "兩院皆可"] = "林口長庚"
    limit: int = 3
    preferences: AppointmentPreparationRequest = Field(
        default_factory=lambda: AppointmentPreparationRequest(patient_type="unknown"),
    )
