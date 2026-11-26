"use client";

import { useEffect, useRef, useState } from "react";
import IntakeChat from "./intake-chat";
import type { IntakeState } from "./intake-types";
import { agentRequest, CaseDetail, CaseSummary, taskLabels } from "./agent-types";

const tokenKey = "doctorAgentAccess";
const caseKey = "doctorAgentActiveCase";

export default function AgentWorkspace({ currentCase, onCaseUpdate, onUpdate, disabled }: {
  currentCase: CaseDetail | null;
  onCaseUpdate: (detail: CaseDetail | null, token: string | null) => void;
  onUpdate: (state: IntakeState | null, ready: boolean) => Promise<void>;
  disabled: boolean;
}) {
  const [token, setToken] = useState<string | null>(null);
  const [cases, setCases] = useState<CaseSummary[]>([]);
  const [available, setAvailable] = useState(false);
  const [initialized, setInitialized] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [title, setTitle] = useState("");
  const [subject, setSubject] = useState("自己");
  const [consent, setConsent] = useState(false);
  const [temporaryMode, setTemporaryMode] = useState(false);
  const pending = useRef<{ caseId: string; message: string; id: string; version: number } | null>(null);

  useEffect(() => {
    let active = true;
    async function restore() {
      try {
        const status = await agentRequest("/status");
        if (!active) return;
        setAvailable(status.available);
        const savedToken = window.localStorage.getItem(tokenKey);
        if (!status.available || !savedToken) return;
        setToken(savedToken);
        const list = await agentRequest("/cases", savedToken) as CaseSummary[];
        if (!active) return;
        setCases(list);
        const savedCase = window.localStorage.getItem(caseKey);
        const target = list.find((item) => item.id === savedCase) ?? list[0];
        if (target) {
          const detail = await agentRequest("/cases/" + target.id, savedToken) as CaseDetail;
          if (active) onCaseUpdate(detail, savedToken);
        }
      } catch (requestError) {
        if (active) setError(requestError instanceof Error ? requestError.message : "暫時無法載入個案。");
      } finally {
        if (active) setInitialized(true);
      }
    }
    void restore();
    return () => { active = false; };
  }, [onCaseUpdate]);

  useEffect(() => {
    if (!currentCase) return;
    setCases((previous) => [currentCase.case, ...previous.filter((item) => item.id !== currentCase.case.id)]);
    window.localStorage.setItem(caseKey, currentCase.case.id);
  }, [currentCase]);

  async function action(operation: () => Promise<void>) {
    if (busy || disabled) return;
    setBusy(true);
    setError(null);
    try { await operation(); }
    catch (requestError) { setError(requestError instanceof Error ? requestError.message : "個案操作失敗。"); }
    finally { setBusy(false); }
  }

  async function create() {
    if (!consent) { setError("請先同意儲存本個案對話與健康描述。"); return; }
    await action(async () => {
      let access = token;
      if (!access) {
        access = (await agentRequest("/session", null, {})).token as string;
        window.localStorage.setItem(tokenKey, access);
        setToken(access);
      }
      const detail = await agentRequest("/cases", access, { title: title.trim() || "新的就醫個案", subject_label: subject.trim() || "自己", consent: true }) as CaseDetail;
      pending.current = null;
      setTemporaryMode(false);
      onCaseUpdate(detail, access);
      setTitle("");
      setConsent(false);
    });
  }

  async function send(message: string) {
    if (!currentCase || !token) return;
    if (!pending.current || pending.current.message !== message || pending.current.caseId !== currentCase.case.id) {
      pending.current = { caseId: currentCase.case.id, message, id: crypto.randomUUID(), version: currentCase.task.version };
    }
    const operation = pending.current;
    setBusy(true);
    try {
      const detail = await agentRequest("/cases/" + currentCase.case.id + "/messages", token, {
        message, operation_id: operation.id, expected_version: operation.version,
      }) as CaseDetail;
      pending.current = null;
      onCaseUpdate(detail, token);
    } finally { setBusy(false); }
  }

  async function remove() {
    if (!currentCase || !token || !window.confirm("刪除此個案的對話、任務與記憶？這不會取消院方已完成的掛號。")) return;
    await action(async () => {
      await agentRequest("/cases/" + currentCase.case.id, token, undefined, "DELETE");
      const list = cases.filter((item) => item.id !== currentCase.case.id);
      setCases(list);
      window.localStorage.removeItem(caseKey);
      onCaseUpdate(null, null);
      pending.current = null;
    });
  }

  const blocked = !initialized || disabled || busy || Boolean(token && !currentCase && !temporaryMode) || currentCase?.case.status === "resolved";
  return (
    <div className="space-y-4">
      <section className="space-y-3 rounded-lg border border-teal-200 bg-white p-4 text-sm leading-6">
        <h2 className="font-semibold">我的就醫個案</h2>
        {!initialized ? <p role="status">正在確認個案記憶服務…</p> : !available ? <p className="text-slate-600">持久個案記憶尚未連接資料庫，目前仍可使用下方頁面內對話。</p> : null}
        {available ? <>
          {cases.length ? <label className="block">切換個案<select disabled={busy || disabled} value={currentCase?.case.id ?? ""} onChange={(event) => { const id = event.target.value; if (id) void action(async () => { const detail = await agentRequest("/cases/" + id, token) as CaseDetail; pending.current = null; onCaseUpdate(detail, token); }); }} className="mt-1 w-full rounded border border-slate-300 bg-white p-2">
            <option value="">請選擇個案</option>{cases.map((item) => <option key={item.id} value={item.id}>{item.subject_label} · {item.title}{item.status === "resolved" ? "（已結案）" : ""}</option>)}
          </select></label> : null}
          <div className="grid gap-2 sm:grid-cols-2">
            <label>新個案名稱<input value={title} onChange={(event) => setTitle(event.target.value)} maxLength={120} placeholder="例如：膝蓋疼痛" className="mt-1 w-full rounded border border-slate-300 p-2" /></label>
            <label>就醫對象標籤<input value={subject} onChange={(event) => setSubject(event.target.value)} maxLength={60} placeholder="自己／媽媽，不必填真實姓名" className="mt-1 w-full rounded border border-slate-300 p-2" /></label>
          </div>
          <label className="flex items-start gap-2 text-xs"><input type="checkbox" checked={consent} onChange={(event) => setConsent(event.target.checked)} className="mt-1.5" /><span>同意儲存這個個案的健康描述、對話與任務進度，供此瀏覽器日後接續；可刪除個案。請勿填寫證號、生日或驗證碼。</span></label>
          <button type="button" disabled={busy || disabled || !consent} onClick={() => void create()} className="rounded bg-teal-700 px-3 py-2 font-semibold text-white disabled:bg-slate-400">建立可追蹤個案</button>
          {token ? <button type="button" disabled={busy || disabled} onClick={() => { setTemporaryMode(true); onCaseUpdate(null, null); }} className="ml-3 text-xs text-teal-700 underline">暫用不儲存的頁面內對話</button> : null}
        </> : null}
        {currentCase ? <div className="space-y-2 border-t border-slate-200 pt-3">
          <p className="font-semibold">{currentCase.case.subject_label} · {currentCase.case.title}</p>
          <p role="status">任務進度：{taskLabels[currentCase.task.status] ?? currentCase.task.status}</p>
          {currentCase.task.booking_receipt_number ? <p className="font-semibold text-teal-800">掛號序號：{currentCase.task.booking_receipt_number} · {currentCase.task.preparation?.selected_slot?.date} {currentCase.task.preparation?.selected_slot?.session}</p> : null}
          {currentCase.task.booking_status === "awaiting_confirmation" || currentCase.task.booking_status === "submitting" ? <p className="text-xs text-amber-800">此任務已有掛號送出流程。若已重新開啟頁面，請先至院方查詢結果，避免重複送出。</p> : null}
          <div className="flex flex-wrap gap-3 text-xs">
            <button type="button" disabled={busy || disabled} onClick={() => void action(async () => onCaseUpdate(await agentRequest("/cases/" + currentCase.case.id, token), token))} className="text-teal-700 underline">重新載入進度</button>
            <button type="button" disabled={busy || disabled} onClick={() => void action(async () => onCaseUpdate(await agentRequest("/cases/" + currentCase.case.id + (currentCase.case.status === "resolved" ? "/reopen" : "/resolve"), token, {}), token))} className="text-teal-700 underline">{currentCase.case.status === "resolved" ? "重新開啟個案" : "標示已結案"}</button>
            <button type="button" disabled={busy || disabled} onClick={() => void remove()} className="text-red-700 underline">刪除此個案</button>
          </div>
          <details><summary className="cursor-pointer text-xs text-teal-700">查看助理執行紀錄</summary><ol className="mt-2 list-inside list-decimal text-xs">{currentCase.task.trace.map((item, index) => <li key={index}>{item.message}</li>)}</ol></details>
        </div> : null}
        {error ? <p role="alert" className="text-red-700">{error}</p> : null}
        {token ? <p className="text-xs text-slate-500">存取憑證只保存在此瀏覽器，健康描述存於後端資料庫。清除瀏覽器資料會失去存取憑證；目前不支援跨裝置登入。</p> : null}
      </section>
      <IntakeChat key={currentCase?.case.id ?? "temporary"} onUpdate={onUpdate} disabled={blocked} caseDetail={currentCase} onSend={currentCase ? send : undefined} />
    </div>
  );
}
