"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import { IntakeResponse, IntakeState, patientLabels, weekdayLabels } from "./intake-types";
import type { CaseDetail } from "./agent-types";

const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "") || "http://localhost:8000";
const greeting = "你好，我會幫你整理就醫需求。目前支援林口長庚，想看哪個部位、症狀或科別？也可以一起告訴我方便的日期與時段。";
const examples = ["膝蓋運動後會痛，想下週下午看診。", "胃脹氣，吃完飯肚子脹，想看腸胃科。"];

export default function IntakeChat({ onUpdate, disabled, caseDetail, onSend }: {
  onUpdate: (state: IntakeState | null, ready: boolean) => Promise<void>;
  disabled: boolean;
  caseDetail?: CaseDetail | null;
  onSend?: (message: string) => Promise<void>;
}) {
  const [state, setState] = useState<IntakeState | null>(null);
  const [messages, setMessages] = useState<{ role: "user" | "assistant"; content: string }[]>([{ role: "assistant", content: greeting }]);
  const [input, setInput] = useState("");
  const [quickReplies, setQuickReplies] = useState(examples);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const sending = useRef(false);
  const transcript = useRef<HTMLDivElement>(null);

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
    if (!content || sending.current || disabled) return;
    sending.current = true;
    setBusy(true);
    setError(null);
    try {
      if (onSend) {
        await onSend(content);
        setInput("");
        return;
      }
      const response = await fetch(apiBaseUrl + "/api/intake/chat", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: content, ...(state ? { state } : {}) }),
      });
      if (!response.ok) throw new Error("暫時無法更新對話，原本的條件仍保留，請稍後重試。");
      const data = await response.json() as IntakeResponse;
      setState(data.state);
      setMessages((previous) => ["重新開始", "清除記憶", "清除對話", "重設條件"].includes(content)
        ? [{ role: "assistant", content: data.reply }]
        : [...previous, { role: "user", content }, { role: "assistant", content: data.reply }]);
      setQuickReplies(data.quick_replies);
      setInput("");
      await onUpdate(data.state, data.ready);
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
    setMessages([{ role: "assistant", content: greeting }]);
    setQuickReplies(examples);
    setInput("");
    setError(null);
    await onUpdate(null, false);
  }

  const summary = state ? [
    ["就醫需求", state.clinical_query || "待確認"],
    ["醫院", state.hospital],
    ["初複診", state.patient_type ? patientLabels[state.patient_type] : "待確認"],
    ["日期", state.date_range_known ? state.date_from || state.date_to ? (state.date_from || "即日起") + " ～ " + (state.date_to || "院方開放範圍") : "不限（院方開放範圍內）" : "待確認"],
    ["時段", state.sessions?.join("、") || "待確認"],
    ["星期", state.weekdays.length === 7 ? "不限" : state.weekdays.length ? state.weekdays.map((day) => "週" + weekdayLabels[day]).join("、") : "沒有可選星期，請調整"],
  ] : [];

  return (
    <section className="space-y-4 rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
      <div className="flex items-center justify-between gap-3">
        <h2 className="font-semibold">就醫需求對話</h2>
        {!caseDetail ? <button type="button" disabled={busy || disabled} onClick={() => void reset()} className="text-xs text-slate-600 underline disabled:opacity-50">清除對話與條件</button> : null}
      </div>
      <div ref={transcript} role="log" aria-label="就醫需求對話紀錄" aria-live="polite" aria-relevant="additions" className="max-h-96 space-y-3 overflow-y-auto">
        {messages.map((message, index) => <div key={index} className={message.role === "assistant" ? "mr-4 rounded-lg bg-slate-100 p-3 text-sm leading-7" : "ml-4 rounded-lg bg-teal-50 p-3 text-sm leading-7 text-teal-950"}>
          <p className="mb-1 text-xs font-semibold text-slate-500">{message.role === "assistant" ? "就醫助理" : "你"}</p>
          <p className="whitespace-pre-wrap">{message.content}</p>
        </div>)}
      </div>
      {summary.length ? <dl aria-label="目前記住的條件" className="grid grid-cols-[4.5rem_minmax(0,1fr)] gap-x-3 gap-y-2 rounded-md border border-teal-200 bg-teal-50 p-3 text-xs leading-6">
        {summary.map(([label, value]) => <div key={label} className="contents"><dt className="font-semibold text-teal-900">{label}</dt><dd className="min-w-0 break-words">{value}</dd></div>)}
      </dl> : null}
      <form onSubmit={submit} className="space-y-3">
        <label htmlFor="conversation-message" className="text-sm font-semibold">描述需求或補充條件</label>
        <textarea id="conversation-message" value={input} onChange={(event) => setInput(event.target.value)} disabled={busy || disabled} maxLength={1000} rows={3} className="w-full resize-y rounded-md border border-slate-300 px-3 py-2 text-sm leading-7 focus:border-teal-600 focus:outline-none disabled:bg-slate-100" placeholder="例如：我是複診，下週下午都可以，但週三不行。" />
        <div className="flex flex-wrap gap-2">
          {quickReplies.map((reply) => <button key={reply} type="button" disabled={busy || disabled} onClick={() => void send(reply)} className="rounded-md border border-teal-200 px-3 py-2 text-left text-xs text-teal-800 disabled:opacity-50">{reply}</button>)}
        </div>
        <button type="submit" disabled={busy || disabled || !input.trim()} className="rounded-md bg-teal-700 px-4 py-2 text-sm font-semibold text-white disabled:bg-slate-400">{busy ? "正在整理需求與更新推薦…" : "傳送"}</button>
        {error ? <p role="alert" className="text-sm text-red-700">{error}</p> : null}
        {disabled ? <p role="status" className="text-xs text-amber-800">個案正在更新、處理掛號或已結案，請稍候或從上方管理個案。</p> : null}
      </form>
      <p className="text-xs leading-6 text-slate-500">{caseDetail ? "此對話與條件會保存到選定個案，重新開啟網頁可接續。" : "未建立可追蹤個案時，條件只記在目前頁面，重新整理會重設。"}請勿在對話輸入證號、生日或驗證碼；這些資料請填在掛號表單。</p>
    </section>
  );
}
