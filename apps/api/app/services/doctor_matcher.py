from collections import defaultdict

from app.schemas import (
    MatchedConceptResponse,
    RankingDebugResponse,
    RecommendedDoctorResponse,
)
from app.services.concept_extractor import MatchedConcept
from app.services.department_intent import DepartmentIntent
from app.services.processed_data import load_doctor_concept_map, load_doctors


CATEGORY_WEIGHTS = {
    "disease_or_condition": 1.35,
    "procedure": 1.25,
    "symptom": 1.0,
    "subspecialty": 0.75,
    "procedure_modifier": 0.7,
    "imaging_or_test": 0.65,
    "anatomy": 0.55,
    "non_clinical": 0.25,
}

MATCH_TYPE_WEIGHTS = {
    "exact_keyword": 1.0,
    "synonym_keyword": 0.9,
    "manual_seed": 0.8,
    "inferred_from_phrase": 0.65,
}

GENERIC_CONCEPT_IDS = {
    "CARDIO_CARDIOLOGY",
    "CARDIO_CARDIOVASCULAR_DISEASE",
    "CARDIO_GENERAL_INTERNAL_MEDICINE",
    "NEURO_NEUROLOGY",
    "ORTHO_SPINE",
    "ORTHO_TRAUMA",
    "ORTHO_SPORTS_MEDICINE",
    "ORTHO_JOINT_RECONSTRUCTION",
    "CHEST_PULMONOLOGY",
    "ENDO_ENDOCRINOLOGY",
    "GI_GASTROENTEROLOGY",
    "GERI_GERIATRICS",
    "GERI_CHRONIC_DISEASE_CARE",
    "GYN_OBSTETRICS_GYNECOLOGY",
    "GYN_GENERAL_GYNECOLOGY",
    "GYN_UROGYNECOLOGY",
    "HEME_HEMATOLOGY",
    "HEME_GENERAL_INTERNAL_MEDICINE",
    "ID_INFECTIOUS_DISEASE",
    "ID_GENERAL_INTERNAL_MEDICINE",
    "NEPHRO_NEPHROLOGY",
    "ONCO_ONCOLOGY",
    "ONCO_GENERAL_INTERNAL_MEDICINE",
    "RHEUM_RHEUMATOLOGY",
    "RHEUM_GENERAL_INTERNAL_MEDICINE",
    "PROCTO_COLORECTAL_SURGERY",
    "PLASTIC_PLASTIC_SURGERY",
    "PLASTIC_RECONSTRUCTIVE_SURGERY",
    "NS_NEUROSURGERY",
    "URO_UROLOGY",
    "CVS_CARDIOVASCULAR_SURGERY",
    "TS_THORACIC_SURGERY",
    "TRAUMA_TRAUMA_SURGERY",
    "TRAUMA_GENERAL_SURGERY",
    "LT_LIVER_TRANSPLANT_SURGERY",
    "LT_LIVER_SURGERY",
    "GS_GENERAL_SURGERY",
    "GS_HEPATOBILIARY_SURGERY",
    "PED_PEDIATRICS",
    "PED_NEONATOLOGY",
    "PED_INFECTIOUS_DISEASE",
    "PED_GI_HEPATOLOGY",
    "PED_ALLERGY_IMMUNOLOGY_RHEUM",
    "PED_PULMONOLOGY",
    "PED_NEPHROLOGY",
    "PED_CARDIOLOGY",
    "PED_NEUROLOGY",
    "PED_ENDOCRINOLOGY_METABOLISM",
    "PED_HEMATOLOGY_ONCOLOGY",
    "PED_CRITICAL_CARE_EMERGENCY",
}

DISTINCT_CONCEPT_BONUS = 0.18
GENERIC_CONCEPT_PENALTY = 0.12
DEPARTMENT_INTENT_BOOST = 0.3
DEPARTMENT_INTENT_PENALTY = 0.18
DEPARTMENT_INTENT_HIGH_CONFIDENCE = 0.75


def rank_doctors(
    matched_concepts: list[MatchedConcept],
    limit: int,
    department_intent: DepartmentIntent | None = None,
) -> list[RecommendedDoctorResponse]:
    if not matched_concepts:
        return []

    limit = max(1, min(limit, 3))
    matched_by_id = {concept.concept_id: concept for concept in matched_concepts}
    doctors_by_id = {doctor["doctor_id"]: doctor for doctor in load_doctors()}
    rows_by_doctor: dict[str, list[dict[str, str]]] = defaultdict(list)

    for row in load_doctor_concept_map():
        if row["concept_id"] in matched_by_id:
            rows_by_doctor[row["doctor_id"]].append(row)

    ranked = []
    for doctor_id, rows in rows_by_doctor.items():
        doctor = doctors_by_id.get(doctor_id)
        if not doctor:
            continue

        concept_ids = {row["concept_id"] for row in rows}
        ranking_debug = build_ranking_debug(rows, matched_by_id, doctor, department_intent)
        score = (
            ranking_debug.weighted_evidence_score
            + ranking_debug.distinct_concepts_bonus
            + ranking_debug.department_intent_adjustment
            - ranking_debug.generic_concept_penalty
        )
        concept_responses = [
            to_concept_response(matched_by_id[concept_id])
            for concept_id in sorted(concept_ids)
        ]
        ranked.append(
            RecommendedDoctorResponse(
                doctor_id=doctor["doctor_id"],
                doctor_name_zh=doctor["doctor_name_zh"],
                hospital_zh=doctor["hospital_zh"],
                department_zh=doctor["department_zh"],
                subdepartment_zh=doctor["subdepartment_zh"],
                specialty_raw_zh=doctor["specialty_raw_zh"],
                source_url=doctor["source_url"],
                score=round(score, 3),
                matched_concepts=concept_responses,
                reasons=build_reasons(rows, matched_by_id, doctor["specialty_raw_zh"]),
                ranking_debug=ranking_debug,
            )
        )

    return sorted(
        ranked,
        key=lambda doctor: (-doctor.score, doctor.doctor_id),
    )[:limit]


def build_ranking_debug(
    rows: list[dict[str, str]],
    matched_by_id: dict[str, MatchedConcept],
    doctor: dict[str, str] | None = None,
    department_intent: DepartmentIntent | None = None,
) -> RankingDebugResponse:
    concept_ids = {row["concept_id"] for row in rows}
    weighted_evidence_score = sum(weighted_row_score(row, matched_by_id) for row in rows)
    distinct_concepts_bonus = len(concept_ids) * DISTINCT_CONCEPT_BONUS
    generic_concept_penalty = sum(
        GENERIC_CONCEPT_PENALTY
        for concept_id in concept_ids
        if concept_id in GENERIC_CONCEPT_IDS
    )
    department_intent_adjustment = calculate_department_intent_adjustment(
        doctor,
        department_intent,
    )

    return RankingDebugResponse(
        weighted_evidence_score=round(weighted_evidence_score, 3),
        distinct_concepts_bonus=round(distinct_concepts_bonus, 3),
        generic_concept_penalty=round(generic_concept_penalty, 3),
        department_intent_adjustment=round(department_intent_adjustment, 3),
        matched_concept_count=len(concept_ids),
    )


def weighted_row_score(
    row: dict[str, str],
    matched_by_id: dict[str, MatchedConcept],
) -> float:
    concept = matched_by_id[row["concept_id"]]
    confidence = float(row["confidence"])
    category_weight = CATEGORY_WEIGHTS.get(concept.category, 0.75)
    match_type_weight = MATCH_TYPE_WEIGHTS.get(row["match_type"], 0.75)
    generic_weight = 0.85 if row["concept_id"] in GENERIC_CONCEPT_IDS else 1.0
    return confidence * category_weight * match_type_weight * generic_weight


def calculate_department_intent_adjustment(
    doctor: dict[str, str] | None,
    department_intent: DepartmentIntent | None,
) -> float:
    if (
        not doctor
        or not department_intent
        or not department_intent.department_zh
        or department_intent.confidence <= 0
    ):
        return 0.0

    if doctor["department_zh"] == department_intent.department_zh:
        return DEPARTMENT_INTENT_BOOST * department_intent.confidence

    if department_intent.confidence >= DEPARTMENT_INTENT_HIGH_CONFIDENCE:
        return -(DEPARTMENT_INTENT_PENALTY * department_intent.confidence)

    return 0.0


def to_concept_response(concept: MatchedConcept) -> MatchedConceptResponse:
    return MatchedConceptResponse(
        concept_id=concept.concept_id,
        canonical_name_zh=concept.canonical_name_zh,
        canonical_name_en=concept.canonical_name_en,
        category=concept.category,
        matched_terms=list(concept.matched_terms),
    )


def build_reasons(
    rows: list[dict[str, str]],
    matched_by_id: dict[str, MatchedConcept],
    specialty_raw_zh: str,
) -> list[str]:
    concept_names = [
        matched_by_id[row["concept_id"]].canonical_name_zh
        for row in sorted(rows, key=lambda item: item["concept_id"])
    ]
    source_phrases = sorted({row["source_phrase_zh"] for row in rows if row["source_phrase_zh"]})

    reasons = []
    if concept_names:
        reasons.append(f"符合概念：{'、'.join(concept_names)}")
    if source_phrases:
        reasons.append(f"對應專長關鍵詞：{'、'.join(source_phrases)}")
    if specialty_raw_zh:
        reasons.append(f"來源專長：{specialty_raw_zh}")
    return reasons
