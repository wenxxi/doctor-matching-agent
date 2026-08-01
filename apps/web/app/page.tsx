"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";

type MatchedConcept = {
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

type RecommendedDoctor = {
  doctor_id: string;
  doctor_name_zh: string;
  hospital_zh: string;
  department_zh: string;
  subdepartment_zh: string;
  specialty_raw_zh: string;
  source_url: string;
  score: number;
  matched_concepts: MatchedConcept[];
  reasons: string[];
  ranking_debug: RankingDebug | null;
  llm_reason_zh: string | null;
};

type RecommendationResponse = {
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

const sampleQueries = [
  "胃脹氣，吃完飯肚子脹，想看腸胃科。",
  "有點喉嚨痛，最近有黃痰，一直咳嗽兩個禮拜。",
  "不孕症想做試管嬰兒，也有多囊性卵巢和子宮內膜異位症。",
];

const apiBaseUrl =
  process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "") ||
  "http://localhost:8000";

export default function Home() {
  const [query, setQuery] = useState(sampleQueries[0]);
  const [result, setResult] = useState<RecommendationResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [showDebug, setShowDebug] = useState(false);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    setShowDebug(
      params.get("debug") === "1" ||
        window.localStorage.getItem("doctorMatchingDebug") === "1",
    );
  }, []);

  const totalTokens = useMemo(() => {
    if (!result) {
      return null;
    }
    const values = [
      result.input_tokens,
      result.output_tokens,
      result.reason_input_tokens,
      result.reason_output_tokens,
    ].filter((value): value is number => typeof value === "number");
    if (values.length === 0) {
      return null;
    }
    return values.reduce((sum, value) => sum + value, 0);
  }, [result]);

  async function submitRecommendation(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmedQuery = query.trim();
    if (!trimmedQuery) {
      setError("請輸入症狀或就醫需求。");
      setResult(null);
      return;
    }

    setIsLoading(true);
    setError(null);

    try {
      const response = await fetch(`${apiBaseUrl}/api/recommendations`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          query: trimmedQuery,
          limit: 3,
        }),
      });

      if (!response.ok) {
        throw new Error(`API request failed with status ${response.status}`);
      }

      const data = (await response.json()) as RecommendationResponse;
      setResult(data);
    } catch (requestError) {
      setResult(null);
      setError(
        requestError instanceof Error
          ? requestError.message
          : "無法連線到推薦 API。",
      );
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <main className="min-h-screen bg-[#f7f9fb] text-slate-950">
      <section className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-6xl flex-col gap-4 px-5 py-8 sm:px-8">
          <div>
            <p className="text-sm font-semibold text-teal-700">MVP Test UI</p>
            <h1 className="mt-2 text-3xl font-bold tracking-normal sm:text-5xl">
              Doctor Matching Agent
            </h1>
          </div>
          <p className="max-w-3xl text-base leading-7 text-slate-600">
            Enter a patient symptom description to find relevant doctors based
            on matched medical concepts and available specialty data.
          </p>
        </div>
      </section>

      <section className="mx-auto grid max-w-6xl gap-6 px-5 py-6 sm:px-8 lg:grid-cols-[minmax(0,0.95fr)_minmax(0,1.25fr)]">
        <div className="space-y-5">
          <form
            onSubmit={submitRecommendation}
            className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm"
          >
            <label
              htmlFor="query"
              className="text-sm font-semibold text-slate-800"
            >
              Patient Input
            </label>
            <textarea
              id="query"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              className="mt-3 min-h-40 w-full resize-y rounded-md border border-slate-300 bg-white px-3 py-3 text-base leading-7 outline-none transition focus:border-teal-600 focus:ring-2 focus:ring-teal-100"
              placeholder="請描述疼痛位置、症狀、受傷情境或已知診斷。"
            />
            <div className="mt-3 flex flex-wrap gap-2">
              {sampleQueries.map((sample) => (
                <button
                  key={sample}
                  type="button"
                  onClick={() => setQuery(sample)}
                  className="rounded-md border border-slate-300 px-3 py-2 text-left text-xs leading-5 text-slate-700 transition hover:border-teal-500 hover:text-teal-800"
                >
                  {sample}
                </button>
              ))}
            </div>
            <button
              type="submit"
              disabled={isLoading}
              className="mt-4 inline-flex min-h-11 items-center justify-center rounded-md bg-teal-700 px-4 py-2 text-sm font-semibold text-white transition hover:bg-teal-800 disabled:cursor-not-allowed disabled:bg-slate-400"
            >
              {isLoading ? "Matching..." : "Recommend 3 Doctors"}
            </button>
          </form>

          {showDebug ? (
            <DebugPanel result={result} totalTokens={totalTokens} />
          ) : null}
        </div>

        <div className="space-y-5">
          {error ? (
            <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm leading-6 text-red-800">
              {error}
            </div>
          ) : null}

          {result?.message ? (
            <div className="rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm leading-6 text-amber-900">
              {result.message}
            </div>
          ) : null}

          <ConceptPanel
            concepts={result?.matched_concepts ?? []}
            showDebug={showDebug}
          />
          <DoctorPanel
            doctors={result?.recommended_doctors ?? []}
            showDebug={showDebug}
          />
        </div>
      </section>
    </main>
  );
}

function DebugPanel({
  result,
  totalTokens,
}: {
  result: RecommendationResponse | null;
  totalTokens: number | null;
}) {
  const rows = [
    ["API", apiBaseUrl],
    ["Method", result?.concept_extraction_method ?? "-"],
    ["Fallback", result ? String(result.fallback_used) : "-"],
    ["Intent", result?.department_intent ?? "-"],
    ["Intent conf", valueOrDash(result?.department_intent_confidence)],
    ["Candidates", valueOrDash(result?.candidate_concepts_count)],
    ["Extract in", valueOrDash(result?.input_tokens)],
    ["Extract out", valueOrDash(result?.output_tokens)],
    ["Reason in", valueOrDash(result?.reason_input_tokens)],
    ["Reason out", valueOrDash(result?.reason_output_tokens)],
    ["Total tokens", valueOrDash(totalTokens)],
  ];

  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
      <h2 className="text-sm font-semibold text-slate-800">Debug</h2>
      <dl className="mt-3 grid grid-cols-[7rem_minmax(0,1fr)] gap-x-3 gap-y-2 text-sm">
        {rows.map(([label, value]) => (
          <div key={label} className="contents">
            <dt className="text-slate-500">{label}</dt>
            <dd className="min-w-0 break-words font-medium text-slate-900">
              {value}
            </dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

function ConceptPanel({
  concepts,
  showDebug,
}: {
  concepts: MatchedConcept[];
  showDebug: boolean;
}) {
  return (
    <section className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
      <div className="flex items-center justify-between gap-3">
        <h2 className="text-base font-semibold">Matched Concepts</h2>
        <span className="rounded-md bg-slate-100 px-2 py-1 text-xs font-semibold text-slate-600">
          {concepts.length}
        </span>
      </div>
      {concepts.length === 0 ? (
        <p className="mt-3 text-sm leading-6 text-slate-600">
          No concepts matched yet.
        </p>
      ) : (
        <div className="mt-3 flex flex-wrap gap-2">
          {concepts.map((concept) => (
            <div
              key={concept.concept_id}
              className="rounded-md border border-teal-200 bg-teal-50 px-3 py-2"
            >
              <p className="text-sm font-semibold text-teal-950">
                {concept.canonical_name_zh}
              </p>
              {showDebug ? (
                <p className="mt-1 text-xs text-teal-800">
                  {concept.concept_id}
                </p>
              ) : null}
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

function DoctorPanel({
  doctors,
  showDebug,
}: {
  doctors: RecommendedDoctor[];
  showDebug: boolean;
}) {
  return (
    <section className="space-y-3">
      <div className="flex items-center justify-between gap-3">
        <h2 className="text-base font-semibold">Recommended Doctors</h2>
        <span className="rounded-md bg-slate-200 px-2 py-1 text-xs font-semibold text-slate-700">
          Top {doctors.length}
        </span>
      </div>

      {doctors.length === 0 ? (
        <div className="rounded-lg border border-slate-200 bg-white p-4 text-sm leading-6 text-slate-600 shadow-sm">
          No doctor recommendations yet.
        </div>
      ) : (
        doctors.map((doctor, index) => (
          <article
            key={doctor.doctor_id}
            className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm"
          >
            <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
              <div>
                <p className="text-xs font-semibold text-teal-700">
                  Recommendation {index + 1}
                </p>
                <h3 className="mt-1 text-xl font-bold tracking-normal">
                  {doctor.doctor_name_zh}
                </h3>
                <p className="mt-1 text-sm text-slate-600">
                  {doctor.hospital_zh} / {doctor.department_zh}
                </p>
              </div>
              {showDebug ? (
                <div className="rounded-md bg-slate-100 px-3 py-2 text-sm font-semibold text-slate-700">
                  Score {doctor.score.toFixed(2)}
                </div>
              ) : null}
            </div>

            {doctor.llm_reason_zh ? (
              <p className="mt-4 rounded-md border border-teal-200 bg-teal-50 p-3 text-sm leading-7 text-teal-950">
                {doctor.llm_reason_zh}
              </p>
            ) : null}

            {!doctor.llm_reason_zh && doctor.reasons[0] ? (
              <p className="mt-4 rounded-md border border-slate-200 bg-slate-50 p-3 text-sm leading-7 text-slate-700">
                {doctor.reasons[0]}
              </p>
            ) : null}

            {showDebug ? (
              <div className="mt-4 space-y-2">
                {doctor.reasons.map((reason) => (
                  <p key={reason} className="text-sm leading-6 text-slate-700">
                    {reason}
                  </p>
                ))}
              </div>
            ) : null}

            {showDebug && doctor.ranking_debug ? (
              <dl className="mt-4 grid grid-cols-2 gap-2 border-t border-slate-200 pt-4 text-xs sm:grid-cols-4">
                <RankingMetric
                  label="Evidence"
                  value={doctor.ranking_debug.weighted_evidence_score}
                />
                <RankingMetric
                  label="Concept bonus"
                  value={doctor.ranking_debug.distinct_concepts_bonus}
                />
                <RankingMetric
                  label="Generic penalty"
                  value={doctor.ranking_debug.generic_concept_penalty}
                />
                <RankingMetric
                  label="Intent adj."
                  value={doctor.ranking_debug.department_intent_adjustment}
                />
                <RankingMetric
                  label="Concepts"
                  value={doctor.ranking_debug.matched_concept_count}
                />
              </dl>
            ) : null}

            <div className="mt-4 flex flex-wrap gap-2">
              {doctor.matched_concepts.map((concept) => (
                <span
                  key={concept.concept_id}
                  className="rounded-md bg-slate-100 px-2 py-1 text-xs font-medium text-slate-700"
                >
                  {concept.canonical_name_zh}
                </span>
              ))}
            </div>

            {doctor.source_url ? (
              <a
                href={doctor.source_url}
                target="_blank"
                rel="noreferrer"
                className="mt-4 inline-block text-sm font-semibold text-teal-700 hover:text-teal-900"
              >
                Source profile
              </a>
            ) : null}
          </article>
        ))
      )}
    </section>
  );
}

function RankingMetric({
  label,
  value,
}: {
  label: string;
  value: number;
}) {
  return (
    <div className="rounded-md bg-slate-50 px-2 py-2">
      <dt className="font-medium text-slate-500">{label}</dt>
      <dd className="mt-1 font-semibold text-slate-900">{value.toFixed(3)}</dd>
    </div>
  );
}

function valueOrDash(value: number | string | null | undefined) {
  if (value === null || typeof value === "undefined" || value === "") {
    return "-";
  }
  return String(value);
}
