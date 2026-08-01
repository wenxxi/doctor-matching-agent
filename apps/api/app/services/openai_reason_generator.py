import json
from dataclasses import dataclass
from typing import Any

from app.schemas import RecommendedDoctorResponse
from app.services.concept_extractor import MatchedConcept
from app.services.openai_client import get_openai_client, get_openai_model
from app.settings import get_openai_settings


class OpenAIReasonGenerationError(Exception):
    pass


@dataclass(frozen=True)
class ReasonGenerationResult:
    reasons: dict[str, str]
    input_tokens: int | None = None
    output_tokens: int | None = None


def generate_llm_reasons(
    query: str,
    matched_concepts: list[MatchedConcept],
    doctors: list[RecommendedDoctorResponse],
) -> dict[str, str]:
    return generate_llm_reasons_with_metadata(query, matched_concepts, doctors).reasons


def generate_llm_reasons_with_metadata(
    query: str,
    matched_concepts: list[MatchedConcept],
    doctors: list[RecommendedDoctorResponse],
) -> ReasonGenerationResult:
    if not get_openai_settings().api_key or not matched_concepts or not doctors:
        return ReasonGenerationResult(reasons={})

    try:
        response = get_openai_client().responses.create(
            model=get_openai_model(),
            instructions=build_instructions(),
            input=build_input(query, matched_concepts, doctors),
            temperature=0,
            max_output_tokens=900,
            text={
                "format": {
                    "type": "json_schema",
                    "name": "doctor_recommendation_reasons",
                    "strict": True,
                    "schema": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "doctor_reasons": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "additionalProperties": False,
                                    "properties": {
                                        "doctor_id": {"type": "string"},
                                        "llm_reason_zh": {"type": "string"},
                                    },
                                    "required": ["doctor_id", "llm_reason_zh"],
                                },
                            }
                        },
                        "required": ["doctor_reasons"],
                    },
                }
            },
        )
        payload = parse_response_json(response)
        return ReasonGenerationResult(
            reasons=valid_reasons(payload, {doctor.doctor_id for doctor in doctors}),
            input_tokens=response_token_count(response, "input_tokens"),
            output_tokens=response_token_count(response, "output_tokens"),
        )
    except Exception:
        return ReasonGenerationResult(reasons={})


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


def build_instructions() -> str:
    return (
        "You write Traditional Chinese patient-facing explanations for an orthopedic doctor "
        "matching system. Use only the provided user query, matched concepts, ranked doctors, "
        "doctor specialty text, and deterministic evidence. Do not invent doctor expertise. "
        "Do not mention concepts that were not provided. Do not give a diagnosis. Do not claim "
        "any doctor is the best. Explain only why each doctor may be relevant. Include a brief "
        "safety note when symptoms are severe, worsening, traumatic, numbness/weakness occurs, "
        "or walking is difficult. Return JSON only."
    )


def build_input(
    query: str,
    matched_concepts: list[MatchedConcept],
    doctors: list[RecommendedDoctorResponse],
) -> str:
    return json.dumps(
        {
            "user_query": query,
            "matched_concepts": [
                {
                    "concept_id": concept.concept_id,
                    "canonical_name_zh": concept.canonical_name_zh,
                    "category": concept.category,
                }
                for concept in matched_concepts
            ],
            "ranked_doctors": [
                {
                    "doctor_id": doctor.doctor_id,
                    "doctor_name_zh": doctor.doctor_name_zh,
                    "specialty_raw_zh": doctor.specialty_raw_zh,
                    "matched_concepts": [
                        {
                            "concept_id": concept.concept_id,
                            "canonical_name_zh": concept.canonical_name_zh,
                        }
                        for concept in doctor.matched_concepts
                    ],
                    "deterministic_reasons": doctor.reasons,
                }
                for doctor in doctors
            ],
            "output_contract": {
                "doctor_reasons": [
                    {
                        "doctor_id": "CGMH_LINKOU_ORTHO_001",
                        "llm_reason_zh": "這位醫師可能相關，因為提供的專長資料包含...",
                    }
                ]
            },
        },
        ensure_ascii=False,
    )


def valid_reasons(payload: dict[str, Any], allowed_doctor_ids: set[str]) -> dict[str, str]:
    items = payload.get("doctor_reasons", [])
    if not isinstance(items, list):
        raise OpenAIReasonGenerationError("doctor_reasons must be a list")

    reasons: dict[str, str] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        doctor_id = item.get("doctor_id")
        reason = item.get("llm_reason_zh")
        if (
            isinstance(doctor_id, str)
            and doctor_id in allowed_doctor_ids
            and isinstance(reason, str)
            and reason.strip()
        ):
            reasons[doctor_id] = reason.strip()
    return reasons


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

    raise OpenAIReasonGenerationError("OpenAI response did not contain text output")


def parse_json_object(value: str) -> dict[str, Any]:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise OpenAIReasonGenerationError("OpenAI response was not valid JSON") from exc
    if not isinstance(parsed, dict):
        raise OpenAIReasonGenerationError("OpenAI response JSON must be an object")
    return parsed
