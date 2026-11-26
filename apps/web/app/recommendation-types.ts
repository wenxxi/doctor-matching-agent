export type MatchedConcept = {
  concept_id: string;
  canonical_name_zh: string;
  canonical_name_en: string;
  category: string;
  matched_terms: string[];
};

type RankingDebug = {
  weighted_evidence_score: number;
  distinct_concepts_bonus: number;
  generic_concept_penalty: number;
  department_intent_adjustment: number;
  matched_concept_count: number;
};

export type RecommendedDoctor = {
  doctor_id: string;
  doctor_name_zh: string;
  hospital_zh: string;
  department_zh: string;
  subdepartment_zh: string;
  specialty_raw_zh: string;
  source_url: string;
  registration_url: string | null;
  score: number;
  matched_concepts: MatchedConcept[];
  reasons: string[];
  ranking_debug: RankingDebug | null;
  llm_reason_zh: string | null;
};

export type RecommendationResponse = {
  query: string;
  concept_extraction_method: string;
  fallback_used: boolean;
  department_intent: string | null;
  department_intent_confidence: number;
  candidate_concepts_count: number | null;
  input_tokens: number | null;
  output_tokens: number | null;
  reason_input_tokens: number | null;
  reason_output_tokens: number | null;
  matched_concepts: MatchedConcept[];
  recommended_doctors: RecommendedDoctor[];
  message: string | null;
};
