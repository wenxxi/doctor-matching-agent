from fastapi import APIRouter

from app.schemas import RecommendationRequest, RecommendationResponse
from app.services.concept_extractor import get_concept_extractor
from app.services.department_intent import detect_department_intent
from app.services.doctor_matcher import diversify_departments_if_needed, rank_doctors, to_concept_response
from app.services.available_doctors import filter_available_doctors
from app.services.openai_reason_generator import generate_llm_reasons_with_metadata

router = APIRouter(prefix="/api/recommendations", tags=["recommendations"])


@router.post("", response_model=RecommendationResponse)
def recommend_doctors(request: RecommendationRequest) -> RecommendationResponse:
    extractor = get_concept_extractor()
    extraction = extractor.extract_with_metadata(request.query)
    matched_concepts = extraction.concepts
    department_intent = detect_department_intent(request.query, matched_concepts)
    limit = max(1, min(request.limit, 3))
    candidates = rank_doctors(
        matched_concepts,
        limit,
        department_intent=department_intent,
        candidate_limit=12,
    )
    available, incomplete = filter_available_doctors(candidates, request.preferences, limit)
    recommended_doctors = diversify_departments_if_needed(available, matched_concepts, limit, department_intent)
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
    elif not candidates:
        message = "已找到相關醫療概念，但目前沒有對應醫師資料。"
    elif not recommended_doctors:
        message = "目前檢查的相關醫師中，沒有確認到符合日期、星期、時段與初複診條件的可掛號門診。請調整條件或稍後重試。"
    elif len(recommended_doctors) < limit:
        message = f"目前確認 {len(recommended_doctors)} 位相關醫師有符合條件的掛號時段；其餘未確認可掛號的醫師已排除。"
    if candidates and incomplete:
        message = (message + " " if message else "") + "部分院方時段無法確認，已排除未確認的醫師；可稍後重新查詢。"

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
