from dataclasses import dataclass

from app.services.concept_extractor import MatchedConcept, normalize_text
from app.services.processed_data import load_medical_concepts


@dataclass(frozen=True)
class ClinicalConceptRule:
    triggers: tuple[str, ...]
    concept_ids: tuple[str, ...]
    matched_term: str


CLINICAL_CONCEPT_RULES = (
    ClinicalConceptRule(
        triggers=(
            "腳黑掉",
            "腳發黑",
            "腳變黑",
            "足部變黑",
            "整支腳黑",
            "下肢發黑",
            "下肢變黑",
        ),
        concept_ids=(
            "CVS_PERIPHERAL_ARTERIAL_DISEASE",
            "ENDO_DIABETIC_FOOT",
        ),
        matched_term="clinical_rule:lower_limb_black_discoloration",
    ),
)


def apply_clinical_query_rules(
    query: str,
    concepts: list[MatchedConcept],
) -> list[MatchedConcept]:
    normalized_query = normalize_text(query)
    if not normalized_query:
        return concepts

    concept_by_id = {concept.concept_id: concept for concept in concepts}
    processed_concepts = {
        concept["concept_id"]: concept for concept in load_medical_concepts()
    }

    for rule in CLINICAL_CONCEPT_RULES:
        if not any(normalize_text(trigger) in normalized_query for trigger in rule.triggers):
            continue

        for concept_id in rule.concept_ids:
            if concept_id in concept_by_id:
                existing = concept_by_id[concept_id]
                terms = tuple(dict.fromkeys((*existing.matched_terms, rule.matched_term)))
                concept_by_id[concept_id] = MatchedConcept(
                    concept_id=existing.concept_id,
                    canonical_name_zh=existing.canonical_name_zh,
                    canonical_name_en=existing.canonical_name_en,
                    category=existing.category,
                    matched_terms=terms,
                )
                continue

            concept = processed_concepts.get(concept_id)
            if not concept:
                continue

            concept_by_id[concept_id] = MatchedConcept(
                concept_id=concept["concept_id"],
                canonical_name_zh=concept["canonical_name_zh"],
                canonical_name_en=concept["canonical_name_en"],
                category=concept["category"],
                matched_terms=(rule.matched_term,),
            )

    return sorted(concept_by_id.values(), key=lambda item: (item.category, item.concept_id))
