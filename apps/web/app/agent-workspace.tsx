"use client";

import { useLocale } from "./i18n";

import { useEffect, useRef, useState } from "react";
import IntakeChat from "./intake-chat";
import type { IntakeState, IntakePreferences, IntakeFeedback } from "./intake-types";
import { agentRequest, AgentRequestError, CaseDetail, CaseSummary, taskLabels } from "./agent-types";

const tokenKey = "doctorAgentAccess";
const caseKey = "doctorAgentActiveCase";

export default function AgentWorkspace({ currentCase, onCaseUpdate, onUpdate, disabled }: {
  currentCase: CaseDetail | null;
  onCaseUpdate: (detail: CaseDetail | null, token: string | null) => void;
  onUpdate: (state: IntakeState | null, ready: boolean) => Promise<IntakeFeedback | void>;
  disabled: boolean;
}) {
  const { locale, t } = useLocale();
  const [token, setToken] = useState<string | null>(null);
  const [cases, setCases] = useState<CaseSummary[]>([]);
  const [available, setAvailable] = useState(false);
  const [initialized, setInitialized] = useState(false);
  const [connectionAttempt, setConnectionAttempt] = useState(0);
  const [connectionFailed, setConnectionFailed] = useState(false);
  const [slowConnection, setSlowConnection] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [title, setTitle] = useState("");
  const [subject, setSubject] = useState("");
  const [consent, setConsent] = useState(false);
  const [temporaryMode, setTemporaryMode] = useState(false);
  const pending = useRef<{ caseId: string; message: string; preferences: string; id: string; version: number } | null>(null);

  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    setInitialized(false);
    setConnectionFailed(false);
    setSlowConnection(false);
    setError(null);
    const slowTimer = setTimeout(() => { if (active) setSlowConnection(true); }, 8_000);
    const deadline = setTimeout(() => controller.abort(), 75_000);
    async function restore() {
      try {
        const status = await agentRequest("/status", null, undefined, undefined, { signal: controller.signal });
        if (!active) return;
        setAvailable(status.available);
        const savedToken = window.localStorage.getItem(tokenKey);
        if (!status.available || !savedToken) return;
        setToken(savedToken);
        const list = await agentRequest("/cases", savedToken, undefined, undefined, { signal: controller.signal }) as CaseSummary[];
        if (!active) return;
        setCases(list);
        const savedCase = window.localStorage.getItem(caseKey);
        const target = list.find((item) => item.id === savedCase) ?? list[0];
        if (target) {
          const detail = await agentRequest("/cases/" + target.id, savedToken, undefined, undefined, { signal: controller.signal }) as CaseDetail;
          if (active) onCaseUpdate(detail, savedToken);
        }
      } catch (error) {
        if (active) {
          if (error instanceof AgentRequestError && error.status === 401) {
            window.localStorage.removeItem(tokenKey);
            window.localStorage.removeItem(caseKey);
            setToken(null);
            setCases([]);
            onCaseUpdate(null, null);
            return;
          }
          setConnectionFailed(true);
          setError(controller.signal.aborted ? "服務啟動時間較長，連線等待已逾時。請稍後按「重新連線」。" : "暫時無法載入個案，請檢查網路後按「重新連線」。");
        }
      } finally {
        clearTimeout(slowTimer);
        clearTimeout(deadline);
        if (active) setInitialized(true);
      }
    }
    void restore();
    return () => { active = false; clearTimeout(slowTimer); clearTimeout(deadline); controller.abort(); };
  }, [onCaseUpdate, connectionAttempt]);

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
      const detail = await agentRequest("/cases", access, { title: title.trim() || (locale === "en" ? "New care case" : "新的就醫個案"), subject_label: subject.trim() || (locale === "en" ? "Me" : "自己"), consent: true }) as CaseDetail;
      pending.current = null;
      setTemporaryMode(false);
      onCaseUpdate(detail, access);
      setTitle("");
      setConsent(false);
    });
  }

  async function send(message: string, intakePreferences?: IntakePreferences) {
    if (!currentCase || !token) return;
    const preferences = JSON.stringify(intakePreferences ?? null);
    if (!pending.current || pending.current.message !== message || pending.current.preferences !== preferences || pending.current.caseId !== currentCase.case.id) {
      pending.current = { caseId: currentCase.case.id, message, preferences, id: crypto.randomUUID(), version: currentCase.task.version };
    }
    const operation = pending.current;
    setBusy(true);
    try {
      const detail = await agentRequest("/cases/" + currentCase.case.id + "/messages", token, {
        message, intake_preferences: intakePreferences, operation_id: operation.id, expected_version: operation.version,
      }) as CaseDetail;
      pending.current = null;
      onCaseUpdate(detail, token);
    } finally { setBusy(false); }
  }

  async function remove() {
    if (!currentCase || !token || !window.confirm(t("刪除此個案的對話、任務與記憶？這不會取消院方已完成的掛號。"))) return;
    await action(async () => {
      await agentRequest("/cases/" + currentCase.case.id, token, undefined, "DELETE");
      const list = cases.filter((item) => item.id !== currentCase.case.id);
      setCases(list);
      window.localStorage.removeItem(caseKey);
      onCaseUpdate(null, null);
      pending.current = null;
    });
  }

  async function loadOlder() {
    if (!currentCase?.messages_cursor || !token) return;
    await action(async () => {
      const page = await agentRequest("/cases/" + currentCase.case.id + "/messages?before=" + encodeURIComponent(currentCase.messages_cursor! as string), token) as { messages: CaseDetail["messages"]; next_cursor: string | null };
      const known = new Set(currentCase.messages.map((item) => item.id));
      onCaseUpdate({ ...currentCase, messages: [...page.messages.filter((item) => !known.has(item.id)), ...currentCase.messages], messages_cursor: page.next_cursor }, token);
    });
  }

  const blocked = !initialized || disabled || busy || Boolean(token && !currentCase && !temporaryMode) || currentCase?.case.status === "resolved";
  return (
    <div className="space-y-4">
      <section className="space-y-3 rounded-lg border border-teal-200 bg-white p-4 text-sm leading-6">
        <h2 className="font-semibold">{t("我的就醫個案")}</h2>
        {!initialized ? <p role="status">{t(slowConnection ? "服務啟動中，首次開啟可能需要約一分鐘，請稍候…" : "正在確認個案記憶服務…")}</p> : !available && !connectionFailed ? <p className="text-slate-600">{t("持久個案記憶尚未連接資料庫，目前仍可使用下方頁面內對話。")}</p> : null}
        {connectionFailed ? <button type="button" disabled={busy || disabled} onClick={() => setConnectionAttempt((previous) => previous + 1)} className="text-teal-700 underline">{t("重新連線")}</button> : null}
        {available ? <>
          {cases.length ? <label className="block">{t("切換個案")}<select disabled={busy || disabled} value={currentCase?.case.id ?? ""} onChange={(event) => { const id = event.target.value; if (id) void action(async () => { const detail = await agentRequest("/cases/" + id, token) as CaseDetail; pending.current = null; onCaseUpdate(detail, token); }); }} className="mt-1 w-full rounded border border-slate-300 bg-white p-2">
            <option value="">{t("請選擇個案")}</option>{cases.map((item) => <option key={item.id} value={item.id}>{item.subject_label} · {item.title}{t(item.status === "resolved" ? "（已結案）" : "")}</option>)}
          </select></label> : null}
          <div className="grid gap-2 sm:grid-cols-2">
            <label>{t("新個案名稱")}<input value={title} onChange={(event) => setTitle(event.target.value)} maxLength={120} placeholder={t("例如：膝蓋疼痛")} className="mt-1 w-full rounded border border-slate-300 p-2" /></label>
            <label>{t("就醫對象標籤")}<input value={subject} onChange={(event) => setSubject(event.target.value)} maxLength={60} placeholder={t("自己／媽媽，不必填真實姓名")} className="mt-1 w-full rounded border border-slate-300 p-2" /></label>
          </div>
          <label className="flex items-start gap-2 text-xs"><input type="checkbox" checked={consent} onChange={(event) => setConsent(event.target.checked)} className="mt-1.5" /><span>{t("同意儲存這個個案的健康描述、對話與任務進度，供此瀏覽器日後接續；可刪除個案。請勿填寫證號、生日或驗證碼。")}</span></label>
          <button type="button" disabled={busy || disabled || !consent} onClick={() => void create()} className="rounded bg-teal-700 px-3 py-2 font-semibold text-white disabled:bg-slate-400">{t("建立可追蹤個案")}</button>
          {token ? <button type="button" disabled={busy || disabled} onClick={() => { setTemporaryMode(true); onCaseUpdate(null, null); }} className="ml-3 text-xs text-teal-700 underline">{t("暫用頁面內對話（不建立個案）")}</button> : null}
        </> : null}
        {currentCase ? <div className="space-y-2 border-t border-slate-200 pt-3">
          <p className="font-semibold">{currentCase.case.subject_label} · {currentCase.case.title}</p>
          <p role="status">{t("任務進度：")}{t(taskLabels[currentCase.task.status] ?? currentCase.task.status)}</p>
          {currentCase.task.booking_receipt_number ? <p className="font-semibold text-teal-800">{t("掛號序號：")}{currentCase.task.booking_receipt_number} · {currentCase.task.preparation?.selected_slot?.date} {t(currentCase.task.preparation?.selected_slot?.session)}</p> : null}
          {currentCase.task.booking_status === "awaiting_confirmation" || currentCase.task.booking_status === "submitting" ? <p className="text-xs text-amber-800">{t("此任務已有掛號送出流程。若已重新開啟頁面，請先至院方查詢結果，避免重複送出。")}</p> : null}
          <div className="flex flex-wrap gap-3 text-xs">
            <button type="button" disabled={busy || disabled} onClick={() => void action(async () => onCaseUpdate(await agentRequest("/cases/" + currentCase.case.id, token), token))} className="text-teal-700 underline">{t("重新載入進度")}</button>
            <button type="button" disabled={busy || disabled} onClick={() => void action(async () => onCaseUpdate(await agentRequest("/cases/" + currentCase.case.id + (currentCase.case.status === "resolved" ? "/reopen" : "/resolve"), token, {}), token))} className="text-teal-700 underline">{t(currentCase.case.status === "resolved" ? "重新開啟個案" : "標示已結案")}</button>
            <button type="button" disabled={busy || disabled} onClick={() => void remove()} className="text-red-700 underline">{t("刪除此個案")}</button>
          </div>
          <details><summary className="cursor-pointer text-xs text-teal-700">{t("查看助理執行紀錄")}</summary><ol className="mt-2 list-inside list-decimal text-xs">{currentCase.task.trace.map((item, index) => <li key={index}>{t(item.message)}</li>)}</ol></details>
        </div> : null}
        {error ? <p role="alert" className="text-red-700">{t(error)}</p> : null}
        {token ? <p className="text-xs text-slate-500">{t("存取憑證只保存在此瀏覽器，健康描述存於後端資料庫。清除瀏覽器資料會失去存取憑證；目前不支援跨裝置登入。")}</p> : null}
      </section>
      <p className="text-xs leading-6 text-slate-500">{t("個案於最後更新 30 天後自動刪除；既有資料於政策啟用 30 天後才開始清理。刪除個案不會取消院方掛號。")}</p>
      <IntakeChat key={currentCase?.case.id ?? "temporary"} onUpdate={onUpdate} disabled={blocked} caseDetail={currentCase} onSend={currentCase ? send : undefined} onLoadOlder={loadOlder} />
    </div>
  );
}
