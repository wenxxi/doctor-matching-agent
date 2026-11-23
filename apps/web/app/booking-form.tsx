"use client";

import { FormEvent, useEffect, useRef, useState } from "react";

export type AppointmentSlot = {
  date: string;
  session: string;
  eligibility: string;
  registration_url: string;
};

type BookingField = {
  name: string;
  label: string;
  kind: string;
  value: string;
  required: boolean;
  options: { value: string; label: string }[];
};

type BookingState = {
  status: "awaiting_patient" | "captcha_error" | "awaiting_confirmation" | "confirmed" | "needs_official" | "unknown" | "rejected" | "closed";
  message: string;
  token: string | null;
  expires_at: string | null;
  captcha_image: string | null;
  fields: BookingField[];
  receipt_number: string | null;
  step_token?: string | null;
};

const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "") || "http://localhost:8000";
const inputClass = "mt-1 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-slate-900";

export default function BookingForm({ doctorId, doctorName, slot, onBusyChange }: {
  doctorId: string;
  doctorName: string;
  slot: AppointmentSlot;
  onBusyChange: (busy: boolean) => void;
}) {
  const [state, setState] = useState<BookingState | null>(null);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [idType, setIdType] = useState("2");
  const [idNumber, setIdNumber] = useState("");
  const [birthday, setBirthday] = useState("");
  const [verification, setVerification] = useState("");
  const [consent, setConsent] = useState(false);
  const [fields, setFields] = useState<Record<string, string>>({});
  const token = useRef<string | null>(null);
  const inFlight = useRef(false);

  useEffect(() => { onBusyChange(busy); }, [busy, onBusyChange]);

  useEffect(() => {
    function confirmLeave(event: BeforeUnloadEvent) {
      if (inFlight.current) {
        event.preventDefault();
        event.returnValue = "";
      }
    }
    window.addEventListener("beforeunload", confirmLeave);
    return () => window.removeEventListener("beforeunload", confirmLeave);
  }, []);

  useEffect(() => {
    let active = true;
    async function start() {
      try {
        const response = await fetch(`${apiBaseUrl}/api/booking/sessions`, {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ doctor_id: doctorId, registration_url: slot.registration_url }),
        });
        const data = await response.json();
        if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : "無法建立掛號工作階段。");
        if (!active) {
          if (data.token) void fetch(`${apiBaseUrl}/api/booking/session`, { method: "DELETE", headers: { "X-Booking-Token": data.token } });
          return;
        }
        token.current = data.token;
        setState(data as BookingState);
      } catch (requestError) {
        if (active) setError(requestError instanceof Error ? requestError.message : "無法建立掛號工作階段。");
      } finally {
        if (active) setBusy(false);
      }
    }
    void start();
    return () => {
      active = false;
      if (token.current && !inFlight.current) {
        void fetch(`${apiBaseUrl}/api/booking/session`, { method: "DELETE", headers: { "X-Booking-Token": token.current }, keepalive: true });
      }
    };
  }, [doctorId, slot.registration_url]);

  async function send(action: "submit" | "continue" | "captcha", body?: unknown) {
    if (!token.current || inFlight.current) return;
    inFlight.current = true;
    setBusy(true);
    setError(null);
    try {
      const response = await fetch(`${apiBaseUrl}/api/booking/${action}`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Booking-Token": token.current },
        ...(body ? { body: JSON.stringify(body) } : {}),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : "院方處理失敗。");
      const next = data as BookingState;
      setState((previous) => ({ ...next, expires_at: previous?.expires_at ?? next.expires_at }));
      setVerification("");
      setConsent(false);
      setFields(Object.fromEntries(next.fields.map((item) => [item.name, item.value])));
      if (next.status !== "captcha_error" && action !== "captcha") {
        setIdNumber("");
        setBirthday("");
      }
    } catch (requestError) {
      const message = requestError instanceof Error ? requestError.message : "連線中斷。";
      if (action === "captcha") {
        setError(message);
      } else {
        setIdNumber("");
        setBirthday("");
        setFields({});
        setState({ status: "unknown", message: `${message} 尚未能確認掛號結果，請先至院方掛號查詢確認，勿重複送出。`, token: null, expires_at: null, captcha_image: null, fields: [], receipt_number: null });
      }
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (state?.status === "awaiting_confirmation") {
      void send("continue", { fields, consent, step_token: state.step_token });
    } else {
      void send("submit", { id_type: idType, id_number: idNumber.trim(), birthday, verification: verification.trim(), consent });
    }
  }

  const patientStep = state?.status === "awaiting_patient" || state?.status === "captcha_error";
  const formStep = patientStep || state?.status === "awaiting_confirmation";

  return (
    <section aria-label="本站掛號表單" className="space-y-3 rounded-md border border-teal-300 bg-white p-4">
      <p className="text-xs font-semibold text-teal-700">本站掛號 · 試用</p>
      <h4 className="font-semibold text-slate-950">{doctorName} · {slot.date} {slot.session}</h4>
      <p className="text-xs text-slate-600">{slot.eligibility} · 到院看診／健保身分</p>
      <div aria-live="polite">
        {busy ? <p>{state ? "正在與院方處理，請勿關閉或重複送出…" : "正在建立院方工作階段並取得驗證碼…"}</p> : null}
        {error ? <p role="alert" className="text-red-700">{error}</p> : null}
        {state ? <p className={state.status === "confirmed" ? "font-semibold text-teal-800" : "text-slate-700"}>{state.message}</p> : null}
        {state?.receipt_number ? <p className="text-lg font-bold">掛號序號：{state.receipt_number}</p> : null}
      </div>
      {state?.expires_at && formStep ? <p className="text-xs text-slate-500">本次資料暫存至 {new Date(state.expires_at).toLocaleTimeString("zh-TW", { timeZone: "Asia/Taipei" })}（台北時間），逾期需重新開始。</p> : null}
      {formStep ? (
        <form onSubmit={submit} autoComplete="off" className="space-y-3">
          <fieldset disabled={busy} className="space-y-3 disabled:opacity-60">
            {patientStep ? (
              <>
                <label className="block">證件類型
                  <select value={idType} onChange={(event) => setIdType(event.target.value)} className={inputClass}>
                    <option value="2">身分證字號</option><option value="1">病歷號</option><option value="3">護照號碼</option><option value="4">居留證號</option><option value="5">入出境許可證號</option>
                  </select>
                </label>
                <label className="block">證號<input type="text" required maxLength={20} value={idNumber} onChange={(event) => setIdNumber(event.target.value)} className={inputClass} autoComplete="off" spellCheck={false} /></label>
                <label className="block">出生日期（西元）<input type="date" required value={birthday} onChange={(event) => setBirthday(event.target.value)} className={inputClass} /></label>
              </>
            ) : state?.fields.map((item) => (
              <label key={item.name} className="block">{item.label}{item.required ? "（必填）" : ""}
                {item.kind === "select" ? (
                  <select value={fields[item.name] ?? ""} required={item.required} onChange={(event) => setFields({ ...fields, [item.name]: event.target.value })} className={inputClass}>
                    <option value="">請選擇</option>{item.options.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
                  </select>
                ) : item.kind === "checkbox" ? (
                  <input type="checkbox" checked={Boolean(fields[item.name])} required={item.required} onChange={(event) => setFields({ ...fields, [item.name]: event.target.checked ? item.value || "on" : "" })} className="ml-2" />
                ) : (
                  <input type={item.kind} value={fields[item.name] ?? ""} maxLength={500} required={item.required} onChange={(event) => setFields({ ...fields, [item.name]: event.target.value })} className={inputClass} />
                )}
              </label>
            ))}
            {state?.captcha_image ? (
              <div className="space-y-2">
                <img src={state.captcha_image} alt="長庚院方驗證碼，請自行辨識並輸入" className="h-12 w-auto border border-slate-200" />
                {patientStep ? <button type="button" onClick={() => void send("captcha")} className="text-teal-700 underline">看不清楚，換一張</button> : null}
              </div>
            ) : null}
            {patientStep ? <label className="block">院方驗證碼<input type="text" required maxLength={12} value={verification} onChange={(event) => setVerification(event.target.value)} className={inputClass} autoComplete="off" /></label> : null}
            <label className="flex items-start gap-2 text-xs leading-6">
              <input type="checkbox" required checked={consent} onChange={(event) => setConsent(event.target.checked)} className="mt-1.5" />
              <span>我已核對醫師、日期與患者資料，並同意<a href="https://register.cgmh.org.tw/BasicmedicalinfoPDF/3" target="_blank" rel="noopener noreferrer" className="text-teal-700 underline">院方一般同意書及病人權利與配合事項</a>，授權系統將本次資料傳送長庚辦理這一筆掛號。</span>
            </label>
            <button type="submit" disabled={!consent || busy} className="rounded-md bg-teal-700 px-4 py-2 font-semibold text-white disabled:bg-slate-400">{state?.status === "awaiting_confirmation" ? "確認資料並送出院方下一步" : "確認並送出掛號"}</button>
          </fieldset>
        </form>
      ) : null}
      {state && ["unknown", "needs_official", "confirmed"].includes(state.status) ? <a href="https://register.cgmh.org.tw/Query/3" target="_blank" rel="noopener noreferrer" className="inline-block font-semibold text-teal-700">至院方查詢掛號結果</a> : null}
      <p className="text-xs leading-5 text-slate-500">患者資料不會傳給語言模型或存入本專案資料庫；後端工作階段暫存最長 10 分鐘。掛號完成與否以院方成功回條為準。</p>
    </section>
  );
}
