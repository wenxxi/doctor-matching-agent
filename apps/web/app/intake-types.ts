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

export const patientLabels = {
  first_visit: "全院初診",
  department_first: "科初診",
  returning: "複診",
  unknown: "不確定初複診",
};

export const weekdayLabels = ["一", "二", "三", "四", "五", "六", "日"];
