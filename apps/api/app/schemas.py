from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


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


class RecommendationRequest(BaseModel):
    query: str
    limit: int = 3


class ConceptExtractionRequest(BaseModel):
    query: str


class MatchedConceptResponse(BaseModel):
    concept_id: str
    canonical_name_zh: str
    canonical_name_en: str
    category: str
    matched_terms: list[str]


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
    score: float
    matched_concepts: list[MatchedConceptResponse]
    reasons: list[str]
    ranking_debug: RankingDebugResponse | None = None
    llm_reason_zh: str | None = None


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


class ConceptExtractionResponse(BaseModel):
    query: str
    extractor: str
    fallback_used: bool
    candidate_concepts_count: int | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    matched_concepts: list[MatchedConceptResponse]
