"use client";

import { useLocale, displayUserMessage } from "./i18n";

import { FormEvent, useEffect, useRef, useState } from "react";
import { defaultPreferences, IntakeFeedback, IntakePreferences, IntakeResponse, IntakeState, patientLabels, weekdayLabels } from "./intake-types";
import type { CaseDetail } from "./agent-types";

const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "") || "http://localhost:8000";
const greeting = "你好，請描述想看診的部位或症狀，並在下方選擇就診偏好；日期與時段都可以選不限。資訊不足時我會再詢問你。";
const examples = ["膝蓋運動後會痛，想下週下午看診。", "胃脹氣，吃完飯肚子脹，想看腸胃科。"];

export default function IntakeChat({ onUpdate, disabled, caseDetail, onSend, onLoadOlder }: {
  onUpdate: (state: IntakeState | null, ready: boolean) => Promise<IntakeFeedback | void>;
  disabled: boolean;
  caseDetail?: CaseDetail | null;
  onSend?: (message: string, preferences?: IntakePreferences) => Promise<void>;
  onLoadOlder?: () => Promise<void>;
}) {
  const { locale, t } = useLocale();
  const [state, setState] = useState<IntakeState | null>(null);
  const [messages, setMessages] = useState<{ role: "user" | "assistant"; content: string }[]>([{ role: "assistant", content: greeting }]);
  const [input, setInput] = useState("");
  const [preferences, setPreferences] = useState<IntakePreferences>(defaultPreferences);
  const [quickReplies, setQuickReplies] = useState(examples);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const sending = useRef(false);
  const transcript = useRef<HTMLDivElement>(null);
  // Send menu choices only on the first turn. Clarification must not reapply
  // defaults and erase dates or sessions already extracted from that turn.
  const initialIntake = !messages.some((message) => message.role === "user");

  useEffect(() => {
    if (!caseDetail) return;
    setState(caseDetail.task.intake);
    setMessages(caseDetail.messages.length ? caseDetail.messages.map((item) => ({ role: item.role, content: item.content })) : [{ role: "assistant", content: greeting }]);
    setQuickReplies(caseDetail.task.intake_response?.quick_replies ?? examples);
    setInput("");
    setError(null);
  }, [caseDetail]);

  async function send(message: string) {
    const content = message.trim();
    if (!content || sending.current || disabled || (initialIntake && !preferences.sessions.length)) return;
    sending.current = true;
    setBusy(true);
    setError(null);
    try {
      if (onSend) {
        await onSend(content, initialIntake ? preferences : undefined);
        setInput("");
        return;
      }
      const response = await fetch(apiBaseUrl + "/api/intake/chat", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: content, ...(state ? { state } : {}), ...(initialIntake ? { intake_preferences: preferences } : {}) }),
      });
      if (!response.ok) {
        const failure = await response.json().catch(() => ({}));
        throw new Error(typeof failure.detail === "string" ? failure.detail : "暫時無法更新對話，原本的條件仍保留，請稍後重試。");
      }
      const data = await response.json() as IntakeResponse;
      setState(data.state);
      const feedback = await onUpdate(data.state, data.ready);
      setMessages((previous) => ["重新開始", "清除記憶", "清除對話", "重設條件"].includes(content)
        ? [{ role: "assistant", content: data.reply }]
        : [...previous, { role: "user", content }, { role: "assistant", content: feedback?.reply ?? data.reply }]);
      setQuickReplies(feedback?.quick_replies ?? data.quick_replies);
      setInput("");
      requestAnimationFrame(() => transcript.current?.scrollTo({ top: transcript.current.scrollHeight, behavior: "smooth" }));
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "暫時無法更新對話，請重試。");
    } finally {
      sending.current = false;
      setBusy(false);
    }
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void send(input);
  }

  async function reset() {
    if (busy || disabled) return;
    setState(null);
    setPreferences(defaultPreferences);
    setMessages([{ role: "assistant", content: greeting }]);
    setQuickReplies(examples);
    setInput("");
    setError(null);
    await onUpdate(null, false);
  }

  const summary = state ? [
    ["就醫需求", state.clinical_query || "待確認"],
    ["醫院", state.hospital],
    ["初複診", state.patient_type ? t(patientLabels[state.patient_type]) : t("待確認")],
    ["日期", state.date_range_known ? state.date_from || state.date_to ? (state.date_from || t("即日起")) + " ～ " + (state.date_to || t("院方開放範圍")) : t("不限（院方開放範圍內）") : t("待確認")],
    ["時段", state.sessions?.length === 3 ? t("都可以") : state.sessions?.map(t).join(locale === "en" ? ", " : "、") || t("待確認")],
    ["星期", state.weekdays.length === 7 ? t("不限") : state.weekdays.length ? state.weekdays.map((day) => t("週") + t(weekdayLabels[day])).join(locale === "en" ? ", " : "、") : t("沒有可選星期，請調整")],
  ] : [];

  return (
    <section className="space-y-4 rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
      <div className="flex items-center justify-between gap-3">
        <h2 className="font-semibold">{t("就醫需求對話")}</h2>
        {!caseDetail ? <button type="button" disabled={busy || disabled} onClick={() => void reset()} className="text-xs text-slate-600 underline disabled:opacity-50">{t("清除對話與條件")}</button> : null}
      </div>
      <div ref={transcript} role="log" aria-label={t("就醫需求對話紀錄")} aria-live="polite" aria-relevant="additions" className="max-h-96 space-y-3 overflow-y-auto">
        {caseDetail?.messages_cursor && onLoadOlder ? <button type="button" disabled={busy || disabled} onClick={() => void onLoadOlder()} className="text-xs text-teal-700 underline">{t("載入較早的對話")}</button> : null}
        {messages.map((message, index) => <div key={index} className={message.role === "assistant" ? "mr-4 rounded-lg bg-slate-100 p-3 text-sm leading-7" : "ml-4 rounded-lg bg-teal-50 p-3 text-sm leading-7 text-teal-950"}>
          <p className="mb-1 text-xs font-semibold text-slate-500">{t(message.role === "assistant" ? "就醫助理" : "你")}</p>
          <p className="whitespace-pre-wrap">{message.role === "assistant" ? t(message.content) : displayUserMessage(message.content, locale)}</p>
        </div>)}
      </div>
      {summary.length ? <dl aria-label={t("目前記住的條件")} className="grid grid-cols-[4.5rem_minmax(0,1fr)] gap-x-3 gap-y-2 rounded-md border border-teal-200 bg-teal-50 p-3 text-xs leading-6">
        {summary.map(([label, value]) => <div key={label} className="contents"><dt className="font-semibold text-teal-900">{t(label)}</dt><dd className="min-w-0 break-words">{t(value)}</dd></div>)}
      </dl> : null}
      <form onSubmit={submit} className="space-y-3">
        {initialIntake ? <fieldset disabled={busy || disabled} className="space-y-3 rounded-md border border-slate-200 p-3">
          <legend className="px-1 text-sm font-semibold">{t("就診偏好（與描述一起送出）")}</legend>
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="text-xs">{t("醫院")}<select aria-label={t("醫院")} value={preferences.hospital} onChange={(event) => setPreferences({ ...preferences, hospital: event.target.value as IntakePreferences["hospital"] })} className="mt-1 w-full rounded border border-slate-300 bg-white p-2">
              {["林口長庚", "台北榮總", "兩院皆可"].map((value) => <option key={value} value={value}>{t(value)}</option>)}
            </select></label>
            <label className="text-xs">{t("初複診")}<select aria-label={t("初複診")} value={preferences.patient_type} onChange={(event) => setPreferences({ ...preferences, patient_type: event.target.value as IntakePreferences["patient_type"] })} className="mt-1 w-full rounded border border-slate-300 bg-white p-2">
              {Object.entries(patientLabels).map(([value, label]) => <option key={value} value={value}>{t(label)}</option>)}
            </select></label>
            <label className="text-xs">{t("日期")}<select aria-label={t("日期")} value={preferences.date_window} onChange={(event) => setPreferences({ ...preferences, date_window: event.target.value as IntakePreferences["date_window"] })} className="mt-1 w-full rounded border border-slate-300 bg-white p-2">
              <option value="any">{t("都可以（院方開放日期內）")}</option><option value="next_week">{t("下週")}</option><option value="two_weeks">{t("兩週內")}</option>
            </select></label>
          </div>
          <fieldset className="flex flex-wrap gap-3">
            <legend className="mb-2 text-xs">{t("可看診時段（可複選）")}</legend>
            <label className="flex items-center gap-1 text-sm"><input type="checkbox" checked={preferences.sessions.length === 3} onChange={() => setPreferences({ ...preferences, sessions: ["上午", "下午", "夜診"] })} />{t("都可以")}</label>
            {(["上午", "下午", "夜診"] as const).map((session) => <label key={session} className="flex items-center gap-1 text-sm"><input type="checkbox" checked={preferences.sessions.includes(session)} onChange={(event) => setPreferences({ ...preferences, sessions: event.target.checked ? [...preferences.sessions, session] : preferences.sessions.filter((value) => value !== session) })} />{t(session)}</label>)}
          </fieldset>
          {!preferences.sessions.length ? <p role="alert" className="text-xs text-red-700">{t("請至少選一個時段，或選「都可以」。")}</p> : null}
          <p className="text-xs leading-6 text-slate-500">{t("若描述中的時間與選單不同，以描述為準。指定日期或星期也可以直接寫在描述中；送出後可用對話調整。")}</p>
        </fieldset> : null}
        <label htmlFor="conversation-message" className="text-sm font-semibold">{t("描述需求或補充條件")}</label>
        <textarea id="conversation-message" value={input} onChange={(event) => setInput(event.target.value)} disabled={busy || disabled} maxLength={1000} rows={3} className="w-full resize-y rounded-md border border-slate-300 px-3 py-2 text-sm leading-7 focus:border-teal-600 focus:outline-none disabled:bg-slate-100" placeholder={t("例如：我是複診，下週下午都可以，但週三不行。")} />
        <div className="flex flex-wrap gap-2">
          {quickReplies.map((reply) => <button key={reply} type="button" disabled={busy || disabled || (initialIntake && !preferences.sessions.length)} onClick={() => { if (initialIntake) setInput(t(reply)); else void send(t(reply)); }} className="rounded-md border border-teal-200 px-3 py-2 text-left text-xs text-teal-800 disabled:opacity-50">{t(reply)}</button>)}
        </div>
        <button type="submit" disabled={busy || disabled || !input.trim() || (initialIntake && !preferences.sessions.length)} className="rounded-md bg-teal-700 px-4 py-2 text-sm font-semibold text-white disabled:bg-slate-400">{t(busy ? "正在整理需求與更新推薦…" : "傳送")}</button>
        {error ? <p role="alert" className="text-sm text-red-700">{t(error)}</p> : null}
        {disabled ? <p role="status" className="text-xs text-amber-800">{t("個案正在更新、處理掛號或已結案，請稍候或從上方管理個案。")}</p> : null}
      </form>
      <p className="text-xs leading-6 text-slate-500">{t(caseDetail ? "此對話與條件會保存到選定個案，重新開啟網頁可接續。" : "未建立可追蹤個案時，條件只記在目前頁面，重新整理會重設。")}{t("請勿在對話輸入證號、生日或驗證碼；這些資料請填在掛號表單。")}</p>
      <p className="text-xs leading-6 text-slate-500">{t("就醫描述會送交語言模型處理。本站已停用模型回應儲存；模型供應商仍可能依安全政策保留日誌。")}</p>
    </section>
  );
}
