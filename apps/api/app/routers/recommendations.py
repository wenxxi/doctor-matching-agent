from fastapi import APIRouter

from app.schemas import RecommendationRequest, RecommendationResponse
from app.services.concept_extractor import get_concept_extractor
from app.services.department_intent import detect_department_intent
from app.services.doctor_matcher import rank_doctors, to_concept_response
from app.services.openai_reason_generator import generate_llm_reasons_with_metadata

router = APIRouter(prefix="/api/recommendations", tags=["recommendations"])


@router.post("", response_model=RecommendationResponse)
def recommend_doctors(request: RecommendationRequest) -> RecommendationResponse:
    extractor = get_concept_extractor()
    extraction = extractor.extract_with_metadata(request.query)
    matched_concepts = extraction.concepts
    department_intent = detect_department_intent(request.query, matched_concepts)
    recommended_doctors = rank_doctors(
        matched_concepts,
        request.limit,
        department_intent=department_intent,
    )
    reason_generation = generate_llm_reasons_with_metadata(
        query=request.query,
        matched_concepts=matched_concepts,
        doctors=recommended_doctors,
    )
    for doctor in recommended_doctors:
        doctor.llm_reason_zh = reason_generation.reasons.get(doctor.doctor_id)

    message = None
    if not matched_concepts:
        message = "目前無法從輸入內容對應到已建立的醫療概念，請嘗試描述主要症狀、部位、持續時間或已知診斷。"
    elif not recommended_doctors:
        message = "已找到相關醫療概念，但目前沒有對應醫師資料。"

    return RecommendationResponse(
        query=request.query,
        concept_extraction_method=extraction.extractor,
        fallback_used=extraction.fallback_used,
        department_intent=department_intent.department_zh,
        department_intent_confidence=department_intent.confidence,
        candidate_concepts_count=extraction.candidate_concepts_count,
        input_tokens=extraction.input_tokens,
        output_tokens=extraction.output_tokens,
        reason_input_tokens=reason_generation.input_tokens,
        reason_output_tokens=reason_generation.output_tokens,
        matched_concepts=[to_concept_response(concept) for concept in matched_concepts],
        recommended_doctors=recommended_doctors,
        message=message,
    )
