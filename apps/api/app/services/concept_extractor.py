import re
from dataclasses import dataclass

from app.settings import get_openai_settings
from app.services.processed_data import load_medical_concepts


@dataclass(frozen=True)
class MatchedConcept:
    concept_id: str
    canonical_name_zh: str
    canonical_name_en: str
    category: str
    matched_terms: tuple[str, ...]


@dataclass(frozen=True)
class ConceptExtractionResult:
    concepts: list[MatchedConcept]
    extractor: str
    fallback_used: bool
    candidate_concepts_count: int | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None


class ConceptExtractor:
    extractor_name = "base"

    def extract_concepts(self, query: str) -> list[MatchedConcept]:
        raise NotImplementedError

    def extract_with_metadata(self, query: str) -> ConceptExtractionResult:
        concepts = self.extract_concepts(query)
        return ConceptExtractionResult(
            concepts=concepts,
            extractor=self.extractor_name,
            fallback_used=False,
            candidate_concepts_count=len(load_medical_concepts()),
        )


class KeywordConceptExtractor(ConceptExtractor):
    extractor_name = "keyword"

    def extract_concepts(self, query: str) -> list[MatchedConcept]:
        normalized_query = normalize_text(query)
        if not normalized_query:
            return []

        matched: list[MatchedConcept] = []
        for concept in load_medical_concepts():
            terms = concept_terms(concept)
            matched_terms = sorted(
                {
                    term
                    for term in terms
                    if term
                    and len(normalize_text(term)) >= 2
                    and normalize_text(term) in normalized_query
                },
                key=lambda term: (-len(term), term),
            )
            if matched_terms:
                matched.append(
                    MatchedConcept(
                        concept_id=concept["concept_id"],
                        canonical_name_zh=concept["canonical_name_zh"],
                        canonical_name_en=concept["canonical_name_en"],
                        category=concept["category"],
                        matched_terms=tuple(matched_terms),
                    )
                )

        return sorted(matched, key=lambda item: (item.category, item.concept_id))


def get_concept_extractor() -> ConceptExtractor:
    if not get_openai_settings().api_key:
        return KeywordConceptExtractor()

    from app.services.openai_concept_extractor import OpenAIConceptExtractor

    return FallbackConceptExtractor(
        primary=OpenAIConceptExtractor(),
        fallback=KeywordConceptExtractor(),
    )


class FallbackConceptExtractor(ConceptExtractor):
    extractor_name = "fallback"

    def __init__(self, primary: ConceptExtractor, fallback: ConceptExtractor) -> None:
        self.primary = primary
        self.fallback = fallback

    def extract_concepts(self, query: str) -> list[MatchedConcept]:
        return self.extract_with_metadata(query).concepts

    def extract_with_metadata(self, query: str) -> ConceptExtractionResult:
        try:
            primary_result = self.primary.extract_with_metadata(query)
        except Exception:
            result = self.fallback.extract_with_metadata(query)
            return ConceptExtractionResult(
                concepts=result.concepts,
                extractor=result.extractor,
                fallback_used=True,
                candidate_concepts_count=result.candidate_concepts_count,
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
            )

        if primary_result.concepts:
            return primary_result

        fallback_result = self.fallback.extract_with_metadata(query)
        if not fallback_result.concepts:
            return primary_result

        return ConceptExtractionResult(
            concepts=fallback_result.concepts,
            extractor=fallback_result.extractor,
            fallback_used=True,
            candidate_concepts_count=primary_result.candidate_concepts_count,
            input_tokens=primary_result.input_tokens,
            output_tokens=primary_result.output_tokens,
        )


def get_keyword_concept_extractor() -> ConceptExtractor:
    return KeywordConceptExtractor()


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", "", value or "").lower()


def concept_terms(concept: dict[str, str]) -> list[str]:
    terms = [concept["canonical_name_zh"]]
    terms.extend(split_terms(concept.get("synonyms_zh", "")))
    terms.extend(split_terms(concept.get("lay_terms_zh", "")))
    return [term for term in terms if term]


def split_terms(value: str) -> list[str]:
    return [term.strip() for term in (value or "").split(";") if term.strip()]
