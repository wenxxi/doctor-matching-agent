"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { englishMessages, chineseMessages } from "./translations";

export type Locale = "zh-TW" | "en";

export function displayUserMessage(text: string, locale: Locale): string {
  if (locale !== "en") return text;
  const preparation = text.match(/^請助理安排(.+)醫師的門診時段。$/);
  if (!preparation) return text;
  return preparation[1] === "所選" ? "Please arrange an appointment with the selected doctor." : `Please arrange an appointment with Dr. ${preparation[1]}.`;
}

export function translate(text: string | null | undefined, locale: Locale): string {
  if (text == null) return "";
  if (locale === "zh-TW") return Object.prototype.hasOwnProperty.call(chineseMessages, text) ? chineseMessages[text] : text;
  if (Object.prototype.hasOwnProperty.call(englishMessages, text)) return englishMessages[text];
  const prefixes = ["已更新這次條件。", "我還需要確認一項資訊。", "已清除這次對話的條件。"];
  const review = text.match(/^語意評估 (\d+) 位候選；(\d+) 位通過患者與醫師專長原文證據檢查。$/);
  if (review) return `Reviewed ${review[1]} candidates; ${review[2]} passed patient and original specialty evidence checks.`;
  const recall = text.match(/^概念與原始專長文字召回 (\d+) 位候選；文字相似度不直接決定推薦。$/);
  if (recall) return `Retrieved ${recall[1]} candidates using concepts and specialty text. Text similarity does not determine recommendations.`;
  const capacity = text.match(/^確認 (\d+) 位醫師具有符合條件的可掛號患者資料頁；未保留名額。$/);
  if (capacity) return `Verified matching patient forms for ${capacity[1]} doctor(s). No appointment is reserved.`;
  const interpretation = text.match(/^以 (.+) 理解患者描述；得到 (\d+) 個可稽核概念，保留疑似／歷史狀態。$/);
  if (interpretation) return `Interpreted the description with ${interpretation[1]}; retained ${interpretation[2]} auditable concepts with uncertainty and history preserved.`;
  for (const prefix of prefixes) {
    if (text.startsWith(prefix)) return translate(prefix, locale) + translate(text.slice(prefix.length), locale);
  }
  const count = text.match(/^目前確認 (\d+) 位相關醫師有符合條件的掛號時段；其餘未確認可掛號的醫師已排除。$/);
  if (count) return `${count[1]} relevant doctor(s) have verified matching appointments. Unverified doctors are excluded.`;
  const found = text.match(/^依日期、星期、時段與初複診條件找到 (\d+) 個候選時段。$/);
  if (found) return `Found ${found[1]} candidate appointment(s) matching your dates, weekdays, sessions, and patient type.`;
  const checked = text.match(/^已確認(\d{4}-\d{2}-\d{2}) (上午|下午|夜診)的院方患者資料頁可開啟。$/);
  if (checked) return `Verified the hospital patient form for ${checked[1]}, ${translate(checked[2], locale)}.`;
  const lookup = text.match(/^查詢(.+)的四週門診時段。$/);
  if (lookup) return `Checking four weeks of appointments for ${lookup[1]}.`;
  if (text.startsWith("符合概念：")) return "Matched expertise: " + text.slice("符合概念：".length);
  if (text.startsWith("初診可掛")) return "First hospital visit only (never attended this hospital)";
  if (text.startsWith("科初診可掛")) return "First departmental visit (not seen in this department in the past six months)";
  if (text.startsWith("一般掛號")) return "General registration (eligibility is confirmed by the hospital)";
  // Compose known status sentences without rewriting arbitrary patient text.
  const sentences = text.split(/(?<=。)/).filter((part) => part.trim());
  if (sentences.length > 1) return sentences.map((part) => translate(part.trim(), locale)).join(" ");
  return text;
}

type LanguageContext = { locale: Locale; setLocale: (locale: Locale) => void; t: (text: string | null | undefined) => string };
const Context = createContext<LanguageContext>({ locale: "zh-TW", setLocale: () => {}, t: (text) => text ?? "" });

export function LocaleProvider({ children }: { children: React.ReactNode }) {
  const [locale, setLanguage] = useState<Locale>("zh-TW");
  useEffect(() => {
    try { if (window.localStorage.getItem("doctorAgentLanguage") === "en") setLanguage("en"); } catch {}
  }, []);
  useEffect(() => { document.documentElement.lang = locale === "en" ? "en" : "zh-Hant"; }, [locale]);
  const setLocale = useCallback((next: Locale) => {
    setLanguage(next);
    try { window.localStorage.setItem("doctorAgentLanguage", next); } catch {}
  }, []);
  const t = useCallback((text: string | null | undefined) => translate(text, locale), [locale]);
  return <Context.Provider value={{ locale, setLocale, t }}>{children}</Context.Provider>;
}

export function useLocale() { return useContext(Context); }

export function LanguageSwitch() {
  const { locale, setLocale } = useLocale();
  return <button type="button" onClick={() => setLocale(locale === "en" ? "zh-TW" : "en")}
    aria-label={locale === "en" ? "切換為繁體中文" : "Switch to English"}
    className="self-start rounded-md border border-teal-700 bg-white px-4 py-2 text-sm font-semibold text-teal-800 hover:bg-teal-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-teal-700">
    {locale === "en" ? "繁體中文" : "English"}
  </button>;
}
