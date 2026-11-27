from fastapi import APIRouter

from app.schemas import RecommendationRequest, RecommendationResponse
from app.services.concept_extractor import get_concept_extractor
from app.services.department_intent import detect_department_intent
from app.services.doctor_matcher import diversify_departments_if_needed, to_concept_response
from app.services.available_doctors import filter_available_doctors
from app.services.doctor_relevance import retrieve_candidates, review_candidates
from app.services.openai_reason_generator import generate_llm_reasons_with_metadata

router = APIRouter(prefix="/api/recommendations", tags=["recommendations"])


@router.post("", response_model=RecommendationResponse)
def recommend_doctors(request: RecommendationRequest) -> RecommendationResponse:
    extractor = get_concept_extractor()
    extraction = extractor.extract_with_metadata(request.query)
    matched_concepts = extraction.concepts
    if extraction.clarification_question:
        return RecommendationResponse(
            query=request.query, concept_extraction_method=extraction.extractor, fallback_used=extraction.fallback_used,
            candidate_concepts_count=extraction.candidate_concepts_count,
            input_tokens=extraction.input_tokens, output_tokens=extraction.output_tokens,
            matched_concepts=[to_concept_response(concept) for concept in matched_concepts], recommended_doctors=[],
            message=extraction.clarification_question, clarification_question=extraction.clarification_question,
            assessment_summary=extraction.assessment_summary, ranking_method="needs_clarification",
            decision_trace=[{"node": "clarify", "message": "患者描述不足，先追問；未查詢掛號時段或強制配對醫師。"}],
        )
    department_intent = detect_department_intent(request.query, matched_concepts)
    limit = max(1, min(request.limit, 3))
    trace = [{"node": "interpret", "message": f"以 {extraction.extractor} 理解患者描述；得到 {len(matched_concepts)} 個可稽核概念，保留疑似／歷史狀態。"}]
    candidates, rule_ids = retrieve_candidates(request.query, matched_concepts, department_intent, search_terms=extraction.search_terms, hospital=request.hospital)
    review = review_candidates(request.query, candidates, rule_ids)
    trace.append({"node": "retrieve", "message": f"概念與原始專長文字召回 {len(candidates)} 位候選；文字相似度不直接決定推薦。"})
    trace.extend(review.trace)
    clarification = extraction.clarification_question or review.clarification_question
    available, incomplete = filter_available_doctors(review.doctors if not clarification else [], request.preferences, limit)
    if len(available) < limit and not clarification:
        extra_candidates, extra_rule_ids = retrieve_candidates(request.query, matched_concepts, department_intent, expanded=True, search_terms=extraction.search_terms, hospital=request.hospital)
        if extra_candidates:
            extra_review = review_candidates(request.query, extra_candidates, extra_rule_ids)
            extra_available, extra_incomplete = filter_available_doctors(extra_review.doctors, request.preferences, limit - len(available))
            available.extend(extra_available)
            incomplete = incomplete or extra_incomplete
            trace.append({"node": "broaden", "message": "首批符合條件的醫師不足，重新查找其他相關候選一次；未放寬日期、時段或資格。"})
            trace.extend(extra_review.trace)
            if extra_review.method != review.method:
                review.method = "mixed_evidence_and_rules"
            review.model_attempted = review.model_attempted or extra_review.model_attempted
            for name in ("input_tokens", "output_tokens"):
                values = [value for value in (getattr(review, name), getattr(extra_review, name)) if value is not None]
                setattr(review, name, sum(values) if values else None)
    # Preserve the semantic review's order; concept-based diversification is a fallback policy.
    recommended_doctors = (diversify_departments_if_needed(available, matched_concepts, limit, department_intent)
                           if review.method == "rule_fallback" else available[:limit])
    reason_generation = generate_llm_reasons_with_metadata(
        query=request.query,
        matched_concepts=matched_concepts,
        doctors=recommended_doctors,
    ) if not review.model_attempted else None
    for doctor in recommended_doctors:
        doctor.llm_reason_zh = doctor.relevance_summary or (reason_generation.reasons.get(doctor.doctor_id) if reason_generation else None)

    message = None
    if clarification:
        message = clarification
    elif not matched_concepts and not recommended_doctors:
        message = "目前無法從輸入內容對應到已建立的醫療概念，請嘗試描述主要症狀、部位、持續時間或已知診斷。"
    elif not candidates:
        message = "已找到相關醫療概念，但目前沒有對應醫師資料。"
    elif not recommended_doctors:
        message = "目前檢查的相關醫師中，沒有確認到符合日期、星期、時段與初複診條件的可掛號門診。請調整條件或稍後重試。"
    elif len(recommended_doctors) < limit:
        message = f"目前確認 {len(recommended_doctors)} 位相關醫師有符合條件的掛號時段；其餘未確認可掛號的醫師已排除。"
    if candidates and incomplete:
        message = (message + " " if message else "") + "部分院方時段無法確認，已排除未確認的醫師；可稍後重新查詢。"
    trace.append({"node": "availability", "message": f"確認 {len(recommended_doctors)} 位醫師具有符合條件的可掛號患者資料頁；未保留名額。"})

    return RecommendationResponse(
        query=request.query,
        concept_extraction_method=extraction.extractor,
        fallback_used=extraction.fallback_used,
        department_intent=department_intent.department_zh,
        department_intent_confidence=department_intent.confidence,
        candidate_concepts_count=extraction.candidate_concepts_count,
        input_tokens=extraction.input_tokens,
        output_tokens=extraction.output_tokens,
        reason_input_tokens=review.input_tokens if review.model_attempted else reason_generation.input_tokens,
        reason_output_tokens=review.output_tokens if review.model_attempted else reason_generation.output_tokens,
        matched_concepts=[to_concept_response(concept) for concept in matched_concepts] if not clarification else [],
        recommended_doctors=recommended_doctors,
        message=message,
        ranking_method=review.method,
        assessment_summary=extraction.assessment_summary if not clarification else "尚無足夠來源證據，先補充需求而不確認疾病。",
        clarification_question=clarification,
        decision_trace=trace,
    )
