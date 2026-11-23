"use client";

import { useState } from "react";

type Appointments = {
  status: "available" | "no_slots" | "partial" | "unavailable" | "unsupported";
  checked_at: string | null;
  schedule_urls: string[];
  message: string;
  slots: {
    date: string;
    session: string;
    eligibility: string;
    registration_url: string;
  }[];
};

const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "") || "http://localhost:8000";

export default function AppointmentPanel({ doctor }: {
  doctor: { doctor_id: string; doctor_name_zh: string; registration_url: string | null };
}) {
  const [result, setResult] = useState<Appointments | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [date, setDate] = useState("");
  const [session, setSession] = useState("");

  if (!doctor.registration_url) return null;

  async function loadAppointments() {
    setIsLoading(true);
    setError(null);
    setResult(null);
    try {
      const response = await fetch(`${apiBaseUrl}/api/doctors/${encodeURIComponent(doctor.doctor_id)}/appointments`);
      if (!response.ok) throw new Error("查詢失敗");
      setResult(await response.json() as Appointments);
    } catch {
      setError("暫時無法查詢時段，請使用官方掛號入口。");
    } finally {
      setIsLoading(false);
    }
  }

  const slots = result?.slots.filter((slot) => (!date || slot.date === date) && (!session || slot.session === session)) ?? [];

  return (
    <section aria-label={`${doctor.doctor_name_zh}掛號`} className="mt-4 space-y-3 border-t border-slate-200 pt-4">
      <div className="flex flex-wrap items-center gap-3">
        <button type="button" onClick={loadAppointments} disabled={isLoading} className="rounded-md bg-teal-700 px-4 py-2 text-sm font-semibold text-white hover:bg-teal-800 disabled:bg-slate-400">
          {isLoading ? "正在查詢院方時段…" : result ? "重新查詢時段" : "查詢這位醫師可掛號時段"}
        </button>
        <a href={doctor.registration_url} target="_blank" rel="noopener noreferrer" className="text-sm font-semibold text-teal-700">官方掛號入口 ↗</a>
      </div>
      <div aria-live="polite" className="space-y-3 text-sm leading-6 text-slate-600">
        {error ? <p role="alert">{error}</p> : null}
        {result ? <p>{result.message}</p> : null}
        {result?.checked_at ? <p className="text-xs">資料查詢時間：{new Date(result.checked_at).toLocaleString("zh-TW", { timeZone: "Asia/Taipei" })}（台北時間；快取最長約 2 分鐘）</p> : null}
        {result && result.slots.length > 0 ? (
          <>
            <div className="flex flex-wrap gap-3">
              <label>日期 <input type="date" value={date} onChange={(event) => setDate(event.target.value)} className="rounded border border-slate-300 px-2 py-1" /></label>
              <label>時段 <select value={session} onChange={(event) => setSession(event.target.value)} className="rounded border border-slate-300 px-2 py-1">
                <option value="">全部</option>
                {["上午", "下午", "夜診"].map((name) => <option key={name}>{name}</option>)}
              </select></label>
            </div>
            {slots.length === 0 ? <p>所選條件沒有時段，請調整日期或時段。</p> : null}
            <ul className="max-h-80 space-y-2 overflow-y-auto">
              {slots.map((slot) => (
                <li key={slot.registration_url} className="rounded-md border border-teal-200 bg-teal-50 p-3">
                  <p className="font-semibold text-slate-900">{slot.date} {slot.session}</p>
                  <p>{slot.eligibility}</p>
                  <a href={slot.registration_url} target="_blank" rel="noopener noreferrer" className="font-semibold text-teal-800">前往院方填寫掛號資料 ↗</a>
                </li>
              ))}
            </ul>
          </>
        ) : null}
        {result?.schedule_urls.map((url, index) => <a key={url} href={url} target="_blank" rel="noopener noreferrer" className="mr-3 inline-block font-semibold text-teal-700">科別門診表{result.schedule_urls.length > 1 ? ` ${index + 1}` : ""} ↗</a>)}
      </div>
      <p className="text-xs leading-5 text-slate-500">選擇時段後，請在長庚官網確認醫師、日期及初診資格，填寫患者資料與驗證碼。完成院方確認才算掛號成功。</p>
    </section>
  );
}
