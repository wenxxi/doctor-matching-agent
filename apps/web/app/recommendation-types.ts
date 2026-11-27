export type MatchedConcept = {
  assertion?: string;
  patient_evidence?: string | null;
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
  specialty_evidence?: string | null;
  relevance_summary?: string | null;
  availability: {
    selected_slot: { date: string; session: string; eligibility: string; registration_url: string };
    verified_at: string;
  } | null;
};

export type RecommendationResponse = {
  ranking_method?: string;
  assessment_summary?: string | null;
  clarification_question?: string | null;
  provider_failures?: { http_status?: number }[];
  decision_trace?: { node: string; message: string }[];
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

// Temporary conversations receive the same next-step guidance as saved cases.
export function recommendationFeedback(result: RecommendationResponse) {
  if (result.clarification_question) return { reply: result.clarification_question, quick_replies: [] };
  if (result.recommended_doctors.length) return;
  if (result.provider_failures?.some((failure) => failure.http_status === 403)) {
    return { reply: (result.message || "院方限制本站查詢。") + " 原有就診條件已保留，不會自動改院。", quick_replies: ["維持目前條件", "改成林口長庚"] };
  }
  return {
    reply: (result.message || "目前沒有確認到符合條件的醫師門診。") + " 你可以修改就診條件後再查詢；我不會自行放寬條件。",
    quick_replies: ["時段不限", "日期不限", "維持目前條件"],
  };
}
