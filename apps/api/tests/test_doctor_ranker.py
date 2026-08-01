from app.services.concept_extractor import MatchedConcept
from app.services.department_intent import DepartmentIntent
from app.services.doctor_matcher import (
    build_ranking_debug,
    calculate_department_intent_adjustment,
    weighted_row_score,
)


def matched_concept(concept_id: str, category: str) -> MatchedConcept:
    return MatchedConcept(
        concept_id=concept_id,
        canonical_name_zh=concept_id,
        canonical_name_en=concept_id,
        category=category,
        matched_terms=(concept_id,),
    )


def mapping_row(
    concept_id: str,
    match_type: str = "exact_keyword",
    confidence: str = "0.95",
) -> dict[str, str]:
    return {
        "concept_id": concept_id,
        "match_type": match_type,
        "confidence": confidence,
    }


def test_disease_match_scores_higher_than_anatomy_match():
    matched_by_id = {
        "ORTHO_KNEE": matched_concept("ORTHO_KNEE", "anatomy"),
        "ORTHO_MENISCUS_INJURY": matched_concept(
            "ORTHO_MENISCUS_INJURY",
            "disease_or_condition",
        ),
    }

    anatomy_score = weighted_row_score(mapping_row("ORTHO_KNEE"), matched_by_id)
    disease_score = weighted_row_score(
        mapping_row("ORTHO_MENISCUS_INJURY"),
        matched_by_id,
    )

    assert disease_score > anatomy_score


def test_exact_match_scores_higher_than_inferred_match():
    matched_by_id = {
        "ORTHO_ACL_INJURY": matched_concept(
            "ORTHO_ACL_INJURY",
            "disease_or_condition",
        ),
    }

    exact_score = weighted_row_score(
        mapping_row("ORTHO_ACL_INJURY", match_type="exact_keyword"),
        matched_by_id,
    )
    inferred_score = weighted_row_score(
        mapping_row("ORTHO_ACL_INJURY", match_type="inferred_from_phrase"),
        matched_by_id,
    )

    assert exact_score > inferred_score


def test_generic_concept_gets_penalty_in_ranking_debug():
    matched_by_id = {
        "CARDIO_CARDIOLOGY": matched_concept("CARDIO_CARDIOLOGY", "subspecialty"),
        "CARDIO_ARRHYTHMIA": matched_concept(
            "CARDIO_ARRHYTHMIA",
            "disease_or_condition",
        ),
    }

    debug = build_ranking_debug(
        [
            mapping_row("CARDIO_CARDIOLOGY"),
            mapping_row("CARDIO_ARRHYTHMIA"),
        ],
        matched_by_id,
    )

    assert debug.matched_concept_count == 2
    assert debug.distinct_concepts_bonus > 0
    assert debug.generic_concept_penalty > 0
    assert debug.department_intent_adjustment == 0
    assert debug.weighted_evidence_score > 0


def test_department_intent_boosts_matching_department():
    doctor = {"department_zh": "心臟內科"}
    intent = DepartmentIntent(department_zh="心臟內科", confidence=0.8)

    assert calculate_department_intent_adjustment(doctor, intent) > 0


def test_high_confidence_department_intent_penalizes_non_matching_department():
    doctor = {"department_zh": "骨科部"}
    intent = DepartmentIntent(department_zh="心臟內科", confidence=0.8)

    assert calculate_department_intent_adjustment(doctor, intent) < 0


def test_low_confidence_department_intent_does_not_penalize_non_matching_department():
    doctor = {"department_zh": "骨科部"}
    intent = DepartmentIntent(department_zh="心臟內科", confidence=0.5)

    assert calculate_department_intent_adjustment(doctor, intent) == 0
