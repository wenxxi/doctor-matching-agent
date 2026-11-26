import type { IntakeResponse, IntakeState } from "./intake-types";
import type { RecommendationResponse } from "./recommendation-types";
import type { AppointmentSlot } from "./booking-form";

export type AgentPreparation = {
  doctor_id: string;
  status: string;
  selected_slot: AppointmentSlot | null;
  verified_at: string | null;
  steps: string[];
  message: string;
};

export type CaseSummary = {
  id: string;
  title: string;
  subject_label: string;
  status: string;
  updated_at: string;
};

export type CaseDetail = {
  case: CaseSummary;
  task: {
    id: string;
    status: string;
    version: number;
    intake: IntakeState;
    intake_response: IntakeResponse | null;
    recommendation: RecommendationResponse | null;
    preparation: AgentPreparation | null;
    trace: { node: string; message: string }[];
    booking_status: string | null;
    booking_receipt_number: string | null;
  };
  messages: { id: string; role: "user" | "assistant"; content: string }[];
};

export type AgentContext = {
  token: string;
  case_id: string;
  task_id: string;
  version: number;
  status: string;
  booking_status: string | null;
  preparation: AgentPreparation | null;
};

export const taskLabels: Record<string, string> = {
  clarifying: "等待補充條件", selecting_doctor: "等待選擇醫師", awaiting_patient: "等待患者資料與驗證碼",
  completed: "已取得院方成功回覆", needs_verification: "掛號結果需人工確認",
  human_required: "需至院方處理", closed: "已結案",
};

export const agentApiBase = process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "") || "http://localhost:8000";

export async function agentRequest(path: string, token?: string | null, body?: unknown, method?: string, options: { signal?: AbortSignal; timeoutMs?: number } = {}) {
  const controller = new AbortController();
  let timedOut = false;
  const cancel = () => controller.abort();
  if (options.signal?.aborted) cancel();
  options.signal?.addEventListener("abort", cancel, { once: true });
  const timeout = setTimeout(() => { timedOut = true; controller.abort(); }, options.timeoutMs ?? 90_000);
  try {
    const response = await fetch(agentApiBase + "/api/agent" + path, {
      signal: controller.signal,
      method: method ?? (body ? "POST" : "GET"), cache: "no-store",
      headers: { ...(token ? { "X-Agent-Token": token } : {}), ...(body ? { "Content-Type": "application/json" } : {}) },
      ...(body ? { body: JSON.stringify(body) } : {}),
    });
    if (response.status === 204) return null;
    const data = await response.json();
    if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : "個案服務暫時無法完成。");
    return data;
  } catch (error) {
    if (timedOut) throw new Error("連線等待逾時。若剛才正在處理個案，請先重新載入進度確認結果。");
    throw error;
  } finally {
    clearTimeout(timeout);
    options.signal?.removeEventListener("abort", cancel);
  }
}
