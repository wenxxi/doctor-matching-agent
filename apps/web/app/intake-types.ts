export type IntakeState = {
  clinical_query: string;
  hospital: string;
  patient_type: "first_visit" | "department_first" | "returning" | "unknown" | null;
  date_from: string | null;
  date_to: string | null;
  date_range_known: boolean;
  sessions: ("上午" | "下午" | "夜診")[] | null;
  weekdays: number[];
};

export type IntakeResponse = {
  state: IntakeState;
  reply: string;
  question: string | null;
  quick_replies: string[];
  ready: boolean;
  extraction_method: string;
};

export type IntakePreferences = {
  hospital: "林口長庚" | "台北榮總" | "兩院皆可";
  patient_type: NonNullable<IntakeState["patient_type"]>;
  date_window: "any" | "next_week" | "two_weeks";
  sessions: NonNullable<IntakeState["sessions"]>;
};

export type IntakeFeedback = { reply: string; quick_replies: string[] };

export const defaultPreferences: IntakePreferences = {
  hospital: "林口長庚", patient_type: "unknown", date_window: "any", sessions: ["上午", "下午", "夜診"],
};

export const patientLabels = {
  first_visit: "全院初診",
  department_first: "科初診",
  returning: "複診",
  unknown: "不確定初複診",
};

export const weekdayLabels = ["一", "二", "三", "四", "五", "六", "日"];
