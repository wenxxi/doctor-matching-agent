"use client";

import { FormEvent, useEffect, useState } from "react";
import BookingForm, { AppointmentSlot } from "./booking-form";
import { IntakeState, weekdayLabels } from "./intake-types";

type Appointments = {
  status: string;
  checked_at: string | null;
  schedule_urls: string[];
  message: string;
  slots: AppointmentSlot[];
};

type Preparation = {
  status: string;
  selected_slot: AppointmentSlot | null;
  verified_at: string | null;
  steps: string[];
  message: string;
};

const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "") || "http://localhost:8000";
const inputClass = "mt-1 w-full rounded border border-slate-300 bg-white px-2 py-2";

export default function AppointmentPanel({ doctor, preferences, onBookingBusy }: {
  doctor: { doctor_id: string; doctor_name_zh: string; registration_url: string | null };
  preferences: IntakeState | null;
  onBookingBusy: (doctorId: string, busy: boolean) => void;
}) {
  const [result, setResult] = useState<Appointments | null>(null);
  const [preparation, setPreparation] = useState<Preparation | null>(null);
  const [selected, setSelected] = useState<AppointmentSlot | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dateFrom, setDateFrom] = useState(preferences?.date_from ?? "");
  const [dateTo, setDateTo] = useState(preferences?.date_to ?? "");
  const [sessions, setSessions] = useState<string[]>(preferences?.sessions ?? ["上午", "下午", "夜診"]);
  const [weekdays, setWeekdays] = useState(preferences?.weekdays ?? [0, 1, 2, 3, 4, 5, 6]);
  const [patientType, setPatientType] = useState<string>(preferences?.patient_type ?? "unknown");
  const [bookingBusy, setBookingBusy] = useState(false);

  useEffect(() => { onBookingBusy(doctor.doctor_id, bookingBusy); }, [doctor.doctor_id, bookingBusy, onBookingBusy]);
  useEffect(() => () => { onBookingBusy(doctor.doctor_id, false); }, [doctor.doctor_id, onBookingBusy]);

  if (!doctor.registration_url) return null;

  async function queryAppointments(prepare: boolean) {
    setIsLoading(true);
    setError(null);
    setPreparation(null);
    setSelected(null);
    try {
      const endpoint = `${apiBaseUrl}/api/doctors/${encodeURIComponent(doctor.doctor_id)}/appointments`;
      const response = await fetch(prepare ? `${endpoint}/prepare` : endpoint, prepare ? {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          patient_type: patientType, date_from: dateFrom || null, date_to: dateTo || null,
          sessions,
          weekdays,
        }),
      } : undefined);
      if (!response.ok) throw new Error("查詢失敗，請確認日期範圍或稍後重試。");
      if (prepare) {
        const data = await response.json() as Preparation;
        setPreparation(data);
        setSelected(data.selected_slot);
      } else {
        setResult(await response.json() as Appointments);
      }
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "暫時無法查詢時段，請稍後重試。");
    } finally {
      setIsLoading(false);
    }
  }

  function prepare(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void queryAppointments(true);
  }

  return (
    <section aria-label={`${doctor.doctor_name_zh}掛號助理`} className="mt-4 space-y-3 border-t border-slate-200 pt-4 text-sm leading-6 text-slate-700">
      <h4 className="font-semibold text-slate-950">掛號助理</h4>
      <p>告訴我就診條件，我會查時段、挑選最早符合的門診，確認院方資料頁後，讓你直接在這裡填寫資料與驗證碼。</p>
      {preferences ? <p className="text-xs text-teal-800">已套用對話中確認的條件；你也可以單獨調整這張醫師卡片。</p> : null}
      <form onSubmit={prepare} className="space-y-3">
        <fieldset disabled={isLoading || Boolean(selected)} className="grid gap-3 sm:grid-cols-2 disabled:opacity-60">
          <label>患者類型<select value={patientType} onChange={(event) => setPatientType(event.target.value)} className={inputClass}>
            <option value="unknown">不確定（排除初診限定時段）</option><option value="first_visit">全院初診（從未在林口長庚看診）</option><option value="department_first">科初診（半年內未看過該科）</option><option value="returning">複診</option>
          </select></label>
          <div><p>可看診時段</p><div className="mt-2 flex flex-wrap gap-3">
            {["上午", "下午", "夜診"].map((name) => <label key={name} className="inline-flex items-center gap-1"><input type="checkbox" checked={sessions.includes(name)} onChange={(event) => setSessions(event.target.checked ? [...sessions, name] : sessions.filter((item) => item !== name))} />{name}</label>)}
          </div></div>
          <label>最早日期<input type="date" value={dateFrom} onChange={(event) => setDateFrom(event.target.value)} className={inputClass} /></label>
          <label>最晚日期<input type="date" min={dateFrom || undefined} value={dateTo} onChange={(event) => setDateTo(event.target.value)} className={inputClass} /></label>
          <div><p>可看診星期</p><div className="mt-2 flex flex-wrap gap-3">
            {weekdayLabels.map((name, day) => <label key={name} className="inline-flex items-center gap-1"><input type="checkbox" checked={weekdays.includes(day)} onChange={(event) => setWeekdays(event.target.checked ? [...weekdays, day].sort() : weekdays.filter((item) => item !== day))} />週{name}</label>)}
          </div></div>
          <button type="submit" disabled={isLoading || Boolean(selected) || !sessions.length || !weekdays.length} className="self-end rounded-md bg-teal-700 px-4 py-2 font-semibold text-white disabled:bg-slate-400">{isLoading ? "正在查詢、挑選與確認…" : "請助理安排掛號"}</button>
        </fieldset>
      </form>
      <div aria-live="polite" className="space-y-2">
        {error ? <p role="alert" className="text-red-700">{error}</p> : null}
        {preparation ? <><ol className="list-inside list-decimal text-xs text-slate-600">{preparation.steps.map((step, index) => <li key={index}>{step}</li>)}</ol><p>{preparation.message}</p></> : null}
      </div>
      {selected ? (
        <>
          <BookingForm key={selected.registration_url} doctorId={doctor.doctor_id} doctorName={doctor.doctor_name_zh} slot={selected} onBusyChange={setBookingBusy} />
          <button type="button" disabled={bookingBusy} onClick={() => { setSelected(null); setPreparation(null); }} className="text-xs text-slate-600 underline disabled:opacity-50">關閉此表單、重新選時段（不會取消院方已完成的掛號）</button>
        </>
      ) : null}
      <details>
        <summary className="cursor-pointer font-semibold text-teal-700">我想自行查看其他時段</summary>
        <button type="button" onClick={() => void queryAppointments(false)} disabled={isLoading || Boolean(selected)} className="my-3 rounded border border-teal-300 px-3 py-2 disabled:opacity-50">查詢這位醫師可掛號時段</button>
        {result ? <p>{result.message}</p> : null}
        {result?.checked_at ? <p className="text-xs">查詢時間：{new Date(result.checked_at).toLocaleString("zh-TW", { timeZone: "Asia/Taipei" })}（台北時間；快取約 2 分鐘）</p> : null}
        <ul className="mt-3 max-h-80 space-y-2 overflow-y-auto">
          {result?.slots.map((slot) => <li key={slot.registration_url} className="rounded border border-slate-200 p-3">
            <p className="font-semibold">{slot.date} {slot.session}</p><p>{slot.eligibility}</p>
            <button type="button" disabled={Boolean(selected)} onClick={() => setSelected(slot)} className="font-semibold text-teal-700 disabled:opacity-50">在本站填寫掛號資料</button>
          </li>)}
        </ul>
        {result?.schedule_urls.map((url, index) => <a key={url} href={url} target="_blank" rel="noopener noreferrer" className="mr-3 inline-block text-xs font-semibold text-teal-700">科別門診表{result.schedule_urls.length > 1 ? ` ${index + 1}` : ""}</a>)}
      </details>
    </section>
  );
}
