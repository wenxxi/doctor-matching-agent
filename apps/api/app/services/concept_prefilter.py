from app.services.concept_extractor import concept_terms, normalize_text
from app.services.processed_data import load_medical_concepts

DEFAULT_MAX_CANDIDATES = 30
DEFAULT_MIN_CANDIDATES = 15

COMMON_FALLBACK_CONCEPT_IDS = (
    "ORTHO_SPINE",
    "ORTHO_KNEE",
    "NEURO_NEUROLOGY",
    "NEURO_HEADACHE",
    "CARDIO_CARDIOLOGY",
    "CARDIO_CARDIOVASCULAR_DISEASE",
    "CHEST_PULMONOLOGY",
    "CHEST_ASTHMA",
    "ENDO_ENDOCRINOLOGY",
    "ENDO_DIABETES",
    "GI_GASTROENTEROLOGY",
    "GI_GERD",
    "GERI_GERIATRICS",
    "GYN_OBSTETRICS_GYNECOLOGY",
    "GYN_GENERAL_GYNECOLOGY",
    "HEME_HEMATOLOGY",
    "ID_INFECTIOUS_DISEASE",
    "NEPHRO_NEPHROLOGY",
    "ONCO_ONCOLOGY",
    "RHEUM_RHEUMATOLOGY",
)

RELATED_CONCEPT_IDS = {
    "ORTHO_KNEE": (
        "ORTHO_LIGAMENT_INJURY",
        "ORTHO_ACL_INJURY",
        "ORTHO_MENISCUS_INJURY",
        "ORTHO_KNEE_OSTEOARTHRITIS",
        "ORTHO_SPORTS_MEDICINE",
    ),
    "ORTHO_SHOULDER": (
        "ORTHO_ROTATOR_CUFF_INJURY",
        "ORTHO_SHOULDER_INSTABILITY",
        "ORTHO_SPORTS_MEDICINE",
        "ORTHO_ARTHROSCOPIC_SURGERY",
    ),
    "ORTHO_CERVICAL_SPINE": (
        "ORTHO_SPINE",
        "ORTHO_SPINE_NECK_SHOULDER_PAIN",
        "ORTHO_SPINE_DEGENERATIVE_DISEASE",
        "ORTHO_SPINE_DISC_HERNIATION",
    ),
    "ORTHO_LUMBAR_SPINE": (
        "ORTHO_SPINE",
        "ORTHO_SPINE_LOW_BACK_PAIN",
        "ORTHO_SPINE_SCIATICA",
        "ORTHO_SPINE_DISC_HERNIATION",
    ),
    "NEURO_HEADACHE": (
        "NEURO_MIGRAINE",
        "NEURO_DIZZINESS_VERTIGO",
        "NEURO_NEUROLOGY",
    ),
    "NEURO_EPILEPSY": (
        "NEURO_REFRACTORY_EPILEPSY",
        "NEURO_EPILEPSY_SURGERY_EVALUATION",
        "NEURO_SLEEP_DISORDERS",
    ),
    "NEURO_PARKINSON_DISEASE": (
        "NEURO_MOVEMENT_DISORDERS",
        "NEURO_TREMOR",
        "NEURO_DYSTONIA",
    ),
    "NEURO_CEREBROVASCULAR_DISEASE": (
        "NEURO_STROKE",
        "NEURO_VASCULAR_DEMENTIA",
    ),
    "CARDIO_ARRHYTHMIA": (
        "CARDIO_ELECTROPHYSIOLOGY",
        "CARDIO_PACEMAKER",
    ),
    "CARDIO_CARDIOVASCULAR_DISEASE": (
        "CARDIO_CORONARY_ARTERY_DISEASE",
        "CARDIO_HYPERTENSION",
        "CARDIO_HYPERLIPIDEMIA",
    ),
    "CARDIO_CATHETERIZATION": (
        "CARDIO_INTERVENTIONAL_CARDIOLOGY",
        "CARDIO_STENT",
    ),
    "CARDIO_CARDIOLOGY": (
        "CARDIO_ECHOCARDIOGRAPHY",
        "CARDIO_VALVULAR_HEART_DISEASE",
        "CARDIO_HEART_FAILURE",
    ),
    "CHEST_PULMONOLOGY": (
        "CHEST_ASTHMA",
        "CHEST_COPD",
        "CHEST_CHRONIC_COUGH",
        "CHEST_TUBERCULOSIS",
    ),
    "ENDO_ENDOCRINOLOGY": (
        "ENDO_DIABETES",
        "ENDO_THYROID_DISEASE",
        "ENDO_METABOLIC_SYNDROME",
        "ENDO_OBESITY",
    ),
    "GI_GASTROENTEROLOGY": (
        "GI_BLOATING",
        "GI_GERD",
        "GI_LIVER_DISEASE",
        "GI_ENDOSCOPY",
        "GI_GASTROINTESTINAL_CANCER",
    ),
    "GERI_GERIATRICS": (
        "GERI_CHRONIC_DISEASE_CARE",
        "GERI_COMPREHENSIVE_GERIATRIC_ASSESSMENT",
        "GERI_POLYPHARMACY",
    ),
    "GYN_OBSTETRICS_GYNECOLOGY": (
        "GYN_GENERAL_GYNECOLOGY",
        "GYN_UROGYNECOLOGY",
        "GYN_PREGNANCY_CARE",
        "GYN_INFERTILITY",
    ),
    "GYN_UROGYNECOLOGY": (
        "GYN_URINARY_INCONTINENCE",
        "GYN_PELVIC_ORGAN_PROLAPSE",
        "GYN_FREQUENT_URINATION",
        "GYN_URINARY_TRACT_INFECTION",
    ),
    "GYN_PREGNANCY_CARE": (
        "GYN_HIGH_RISK_PREGNANCY",
        "GYN_PRENATAL_GENETIC_COUNSELING",
        "GYN_FETAL_ULTRASOUND",
    ),
    "GYN_INFERTILITY": (
        "GYN_ASSISTED_REPRODUCTION",
        "GYN_IVF",
        "GYN_PCOS",
        "GYN_ENDOMETRIOSIS",
    ),
    "GYN_GYNECOLOGIC_ONCOLOGY": (
        "GYN_CERVICAL_CANCER",
        "GYN_ENDOMETRIAL_CANCER",
        "GYN_OVARIAN_CANCER",
        "GYN_CHEMOTHERAPY",
    ),
    "HEME_HEMATOLOGY": (
        "HEME_LYMPHOMA",
        "HEME_HEMOPHILIA",
        "HEME_STEM_CELL_TRANSPLANT",
    ),
    "ID_INFECTIOUS_DISEASE": (
        "ID_HIV",
        "ID_MYCOBACTERIAL_INFECTION",
        "ID_MICROBIAL_INFECTION",
    ),
    "NEPHRO_NEPHROLOGY": (
        "NEPHRO_CKD",
        "NEPHRO_HEMODIALYSIS",
        "NEPHRO_PERITONEAL_DIALYSIS",
        "NEPHRO_KIDNEY_TRANSPLANT",
    ),
    "ONCO_ONCOLOGY": (
        "ONCO_GI_CANCER",
        "ONCO_BREAST_CANCER",
        "ONCO_LUNG_CANCER",
        "ONCO_IMMUNO_ONCOLOGY",
    ),
    "RHEUM_RHEUMATOLOGY": (
        "RHEUM_GOUT",
        "RHEUM_RHEUMATOID_ARTHRITIS",
        "RHEUM_LUPUS",
        "RHEUM_ANKYLOSING_SPONDYLITIS",
    ),
}


def prefilter_concepts(
    query: str,
    max_candidates: int = DEFAULT_MAX_CANDIDATES,
    min_candidates: int = DEFAULT_MIN_CANDIDATES,
) -> list[dict[str, str]]:
    concepts = load_medical_concepts()
    concept_by_id = {concept["concept_id"]: concept for concept in concepts}
    normalized_query = normalize_text(query)
    query_chars = chinese_chars(normalized_query)

    scored = []
    for concept in concepts:
        score = score_concept(concept, normalized_query, query_chars)
        if score > 0:
            scored.append((score, concept["concept_id"], concept))

    ranked = [
        concept
        for _, _, concept in sorted(scored, key=lambda item: (-item[0], item[1]))
    ]

    selected = []
    selected_ids = set()
    for concept in ranked:
        if concept["concept_id"] not in selected_ids:
            selected.append(concept)
            selected_ids.add(concept["concept_id"])
        if len(selected) >= max_candidates:
            return selected

    for concept_id in list(selected_ids):
        for related_id in RELATED_CONCEPT_IDS.get(concept_id, ()):
            concept = concept_by_id.get(related_id)
            if concept and related_id not in selected_ids:
                selected.append(concept)
                selected_ids.add(related_id)
            if len(selected) >= max_candidates:
                return selected

    for concept_id in COMMON_FALLBACK_CONCEPT_IDS:
        concept = concept_by_id.get(concept_id)
        if concept and concept_id not in selected_ids:
            selected.append(concept)
            selected_ids.add(concept_id)
        if len(selected) >= min_candidates or len(selected) >= max_candidates:
            break

    return selected[:max_candidates]


def score_concept(concept: dict[str, str], normalized_query: str, query_chars: set[str]) -> float:
    score = 0.0
    for term in concept_terms(concept):
        normalized_term = normalize_text(term)
        if not normalized_term:
            continue
        if len(normalized_term) < 2:
            continue
        if normalized_term in normalized_query:
            score += 20.0 + min(len(normalized_term), 10)
        elif normalized_query and normalized_query in normalized_term:
            score += 8.0

        term_chars = chinese_chars(normalized_term)
        if term_chars and query_chars:
            overlap = len(term_chars & query_chars)
            ratio = overlap / len(term_chars)
            if overlap >= 3 and ratio >= 0.5:
                score += ratio * 5.0

    return score


def chinese_chars(value: str) -> set[str]:
    return {char for char in value if "\u4e00" <= char <= "\u9fff"}
