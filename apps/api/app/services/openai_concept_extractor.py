import json
from typing import Any

from app.services.concept_extractor import (
    ConceptExtractionResult,
    ConceptExtractor,
    MatchedConcept,
)
from app.services.openai_client import get_openai_client, get_openai_model
from app.services.processed_data import load_medical_concepts


class OpenAIConceptExtractionError(Exception):
    pass


class OpenAIConceptExtractor(ConceptExtractor):
    extractor_name = "openai"

    def extract_concepts(self, query: str) -> list[MatchedConcept]:
        return self.extract_with_metadata(query).concepts

    def extract_with_metadata(self, query: str) -> ConceptExtractionResult:
        if not query.strip():
            return ConceptExtractionResult(
                concepts=[],
                extractor=self.extractor_name,
                fallback_used=False,
                candidate_concepts_count=0,
            )

        candidate_concepts = load_medical_concepts()
        concept_by_id = {concept["concept_id"]: concept for concept in candidate_concepts}
        response = get_openai_client().responses.create(
            model=get_openai_model(),
            instructions=build_instructions(),
            input=build_input(query, candidate_concepts),
            temperature=0,
            max_output_tokens=500,
            text={
                "format": {
                    "type": "json_schema",
                    "name": "doctor_matching_concept_extraction",
                    "strict": True,
                    "schema": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "concept_ids": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "confidence": {
                                "type": "number",
                                "minimum": 0,
                                "maximum": 1,
                            },
                        },
                        "required": ["concept_ids", "confidence"],
                    },
                }
            },
        )

        payload = parse_response_json(response)
        concept_ids = payload.get("concept_ids", [])
        if not isinstance(concept_ids, list):
            raise OpenAIConceptExtractionError("OpenAI response concept_ids must be a list")

        matched = []
        seen = set()
        confidence = payload_confidence(payload)
        for concept_id in concept_ids:
            if not isinstance(concept_id, str):
                continue
            if concept_id in seen or concept_id not in concept_by_id:
                continue
            concept = concept_by_id[concept_id]
            matched.append(
                MatchedConcept(
                    concept_id=concept["concept_id"],
                    canonical_name_zh=concept["canonical_name_zh"],
                    canonical_name_en=concept["canonical_name_en"],
                    category=concept["category"],
                    matched_terms=(f"LLM:{confidence:.2f}",),
                )
            )
            seen.add(concept_id)

        return ConceptExtractionResult(
            concepts=sorted(matched, key=lambda item: (item.category, item.concept_id)),
            extractor=self.extractor_name,
            fallback_used=False,
            candidate_concepts_count=len(candidate_concepts),
            input_tokens=response_token_count(response, "input_tokens"),
            output_tokens=response_token_count(response, "output_tokens"),
        )


def response_token_count(response: Any, key: str) -> int | None:
    usage = getattr(response, "usage", None)
    if usage is None:
        return None

    value = getattr(usage, key, None)
    if value is None and isinstance(usage, dict):
        value = usage.get(key)
    if isinstance(value, int):
        return value
    return None


def payload_confidence(payload: dict[str, Any]) -> float:
    value = payload.get("confidence", 0)
    if isinstance(value, int | float):
        return max(0.0, min(float(value), 1.0))
    return 0.0


def build_instructions() -> str:
    return (
        "You are a medical concept extraction assistant for a multi-specialty doctor matching system. "
        "Use medical knowledge to map the user's Chinese symptom description to the most relevant known concept IDs. "
        "Consider that one query can map to multiple concepts and multiple departments. "
        "For symptoms that could indicate a differential diagnosis, include the most clinically relevant plausible concepts "
        "from the allowed list instead of forcing a single department. "
        "Only return concept IDs from the provided allowed_concepts list. "
        "Do not invent concept IDs. Do not recommend doctors. Do not provide medical advice. "
        "If no concept applies, return an empty concept_ids array. Return JSON only."
    )


def build_input(query: str, concepts: list[dict[str, str]]) -> str:
    allowed_concepts = [
        {
            "concept_id": concept["concept_id"],
            "canonical_name_zh": concept["canonical_name_zh"],
            "canonical_name_en": concept["canonical_name_en"],
            "category": concept["category"],
            "synonyms_zh": concept["synonyms_zh"],
            "lay_terms_zh": concept["lay_terms_zh"],
        }
        for concept in concepts
    ]
    return json.dumps(
        {
            "user_query": query,
            "allowed_concepts": allowed_concepts,
            "output_contract": {
                "concept_ids": ["CVS_PERIPHERAL_ARTERIAL_DISEASE", "ENDO_DIABETIC_FOOT"],
                "confidence": 0.82,
            },
        },
        ensure_ascii=False,
    )


def parse_response_json(response: Any) -> dict[str, Any]:
    output_text = getattr(response, "output_text", None)
    if isinstance(output_text, str) and output_text.strip():
        return parse_json_object(output_text)

    output = getattr(response, "output", None)
    if isinstance(output, list):
        text_parts = []
        for item in output:
            content = getattr(item, "content", None)
            if isinstance(content, list):
                for content_item in content:
                    text = getattr(content_item, "text", None)
                    if isinstance(text, str):
                        text_parts.append(text)
        if text_parts:
            return parse_json_object("".join(text_parts))

    raise OpenAIConceptExtractionError("OpenAI response did not contain text output")


def parse_json_object(value: str) -> dict[str, Any]:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise OpenAIConceptExtractionError("OpenAI response was not valid JSON") from exc
    if not isinstance(parsed, dict):
        raise OpenAIConceptExtractionError("OpenAI response JSON must be an object")
    return parsed
