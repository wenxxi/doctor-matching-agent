from fastapi import APIRouter

from app.schemas import ConceptExtractionRequest, ConceptExtractionResponse
from app.services.clinical_query_rules import apply_clinical_query_rules
from app.services.concept_extractor import get_concept_extractor
from app.services.doctor_matcher import to_concept_response

router = APIRouter(prefix="/api/concepts", tags=["concepts"])


@router.post("/extract", response_model=ConceptExtractionResponse)
def extract_concepts(request: ConceptExtractionRequest) -> ConceptExtractionResponse:
    extraction = get_concept_extractor().extract_with_metadata(request.query)
    matched_concepts = apply_clinical_query_rules(request.query, extraction.concepts)

    return ConceptExtractionResponse(
        query=request.query,
        extractor=extraction.extractor,
        fallback_used=extraction.fallback_used,
        candidate_concepts_count=extraction.candidate_concepts_count,
        input_tokens=extraction.input_tokens,
        output_tokens=extraction.output_tokens,
        matched_concepts=[to_concept_response(concept) for concept in matched_concepts],
    )
