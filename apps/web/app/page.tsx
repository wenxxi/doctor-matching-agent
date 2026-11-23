"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import AppointmentPanel from "./appointments";
import IntakeChat from "./intake-chat";
import { IntakeState } from "./intake-types";

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
  registration_url: string | null;
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

const apiBaseUrl =
  process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "") ||
  "http://localhost:8000";

export default function Home() {
  const [intake, setIntake] = useState<IntakeState | null>(null);
  const [conditionRevision, setConditionRevision] = useState(0);
  const [bookingBusyIds, setBookingBusyIds] = useState<string[]>([]);
  const lastQuery = useRef<string | null>(null);
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

  const updateBookingBusy = useCallback((doctorId: string, busy: boolean) => {
    setBookingBusyIds((previous) => {
      if (previous.includes(doctorId) === busy) return previous;
      return busy ? [...previous, doctorId] : previous.filter((item) => item !== doctorId);
    });
  }, []);

  async function updateIntake(state: IntakeState | null, ready: boolean) {
    setIntake(state);
    setConditionRevision((previous) => previous + 1);
    setError(null);
    if (!state || !ready) {
      setResult(null);
      lastQuery.current = null;
      return;
    }
    if (lastQuery.current === state.clinical_query && result) return;

    setIsLoading(true);
    setResult(null);

    try {
      const response = await fetch(`${apiBaseUrl}/api/recommendations`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          query: state.clinical_query,
          limit: 3,
        }),
      });

      if (!response.ok) {
        throw new Error(`API request failed with status ${response.status}`);
      }

      const data = (await response.json()) as RecommendationResponse;
      lastQuery.current = state.clinical_query;
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
            <p className="text-sm font-semibold text-teal-700">你的就醫與掛號助理</p>
            <h1 className="mt-2 text-3xl font-bold tracking-normal sm:text-5xl">
              Doctor Matching Agent
            </h1>
          </div>
          <p className="max-w-3xl text-base leading-7 text-slate-600">
            透過對話整理症狀與就診條件，找到相關醫師，再由掛號助理協助安排門診。目前支援林口長庚。
          </p>
        </div>
      </section>

      <section className="mx-auto grid max-w-6xl gap-6 px-5 py-6 sm:px-8 lg:grid-cols-[minmax(0,0.95fr)_minmax(0,1.25fr)]">
        <div className="space-y-5">
          <IntakeChat onUpdate={updateIntake} disabled={bookingBusyIds.length > 0} />

          {showDebug ? (
            <DebugPanel result={result} totalTokens={totalTokens} />
          ) : null}
        </div>

        <div className="space-y-5">
          {isLoading ? <p role="status" className="text-sm text-teal-800">正在依就醫需求更新推薦醫師…</p> : null}
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
            key={conditionRevision}
            doctors={result?.recommended_doctors ?? []}
            showDebug={showDebug}
            preferences={intake}
            onBookingBusy={updateBookingBusy}
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
  preferences,
  onBookingBusy,
}: {
  doctors: RecommendedDoctor[];
  showDebug: boolean;
  preferences: IntakeState | null;
  onBookingBusy: (doctorId: string, busy: boolean) => void;
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
            <AppointmentPanel key={doctor.doctor_id} doctor={doctor} preferences={preferences} onBookingBusy={onBookingBusy} />
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
