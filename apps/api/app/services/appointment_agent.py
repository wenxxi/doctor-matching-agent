from datetime import date, datetime
from html.parser import HTMLParser
from urllib.parse import urljoin

from app.schemas import (
    AppointmentPreparationRequest,
    AppointmentPreparationResponse,
    AppointmentSlotResponse,
)
from app.services.appointments import BASE_URL, fetch_live_page, get_appointments


class CheckinParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.forms: list[tuple[str, str]] = []
        self.input_names: set[str] = set()
        self.text: list[str] = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == "form":
            self.forms.append((attributes.get("method", "").lower(), attributes.get("action", "")))
        if tag == "input":
            self.input_names.add(attributes.get("name", ""))

    def handle_data(self, data):
        self.text.append(data)


def matches_preferences(slot: AppointmentSlotResponse, request: AppointmentPreparationRequest) -> bool:
    slot_date = date.fromisoformat(slot.date)
    if request.date_from and slot_date < request.date_from:
        return False
    if request.date_to and slot_date > request.date_to:
        return False
    if slot_date.weekday() not in request.weekdays or slot.session not in request.sessions:
        return False
    if slot.eligibility.startswith("科初診可掛"):
        return request.patient_type in {"first_visit", "department_first"}
    if slot.eligibility.startswith("初診可掛"):
        return request.patient_type == "first_visit"
    return slot.eligibility.startswith("一般掛號")


def verify_checkin_page(html: str, slot: AppointmentSlotResponse, doctor_name: str) -> bool:
    parser = CheckinParser()
    parser.feed(html)
    text = "".join(parser.text)
    expected_action = slot.registration_url.replace("/Checkin/3/", "/CheckinConfirm/3/", 1)
    return (
        any(method == "post" and urljoin(BASE_URL, action) == expected_action
            for method, action in parser.forms)
        and {"idNumber", "verification"}.issubset(parser.input_names)
        and doctor_name in text
        and slot.date.replace("-", "/") in text
        and slot.session in text
    )


def prepare_appointment(
    doctor: dict[str, str], request: AppointmentPreparationRequest,
) -> AppointmentPreparationResponse:
    result = AppointmentPreparationResponse(
        doctor_id=doctor["doctor_id"], status="unavailable",
        message="暫時無法查詢院方時段，請稍後重試。",
        steps=[f"查詢{doctor['doctor_name_zh']}的四週門診時段。"],
    )
    snapshot = get_appointments(doctor)
    if snapshot.status in {"unavailable", "unsupported"}:
        result.message = snapshot.message
        return result
    candidates = sorted(
        (slot for slot in snapshot.slots if matches_preferences(slot, request)),
        key=lambda slot: (slot.date, ["上午", "下午", "夜診"].index(slot.session)),
    )
    result.candidate_count = len(candidates)
    result.steps.append(f"依日期、星期、時段與初複診條件找到 {len(candidates)} 個候選時段。")
    if not candidates:
        result.status = "retry_needed" if snapshot.status == "partial" else "no_match"
        result.message = (
            "部分週次查詢失敗，目前已取得的資料沒有符合條件的時段，請重試。"
            if snapshot.status == "partial" else
            "沒有符合條件的時段。可調整日期、星期或時段，再請助理安排；不會自動放寬你的條件。"
        )
        return result
    for slot in candidates[:3]:
        result.attempted_count += 1
        try:
            html, checked_at = fetch_live_page(slot.registration_url)
            if not verify_checkin_page(html, slot, doctor["doctor_name_zh"]):
                result.steps.append(f"{slot.date} {slot.session}的患者資料頁無法確認，改查下一個時段。")
                continue
        except (OSError, ValueError):
            result.steps.append(f"{slot.date} {slot.session}連線失敗，改查下一個時段。")
            continue
        result.status = "awaiting_patient"
        result.selected_slot = slot
        result.verified_at = checked_at
        result.steps.append(f"已確認{slot.date} {slot.session}的院方患者資料頁可開啟。")
        result.message = "已選出符合條件且患者資料頁可開啟的最早時段。接著可在本站填寫患者資料與驗證碼；目前尚未保留名額或完成掛號。"
        if snapshot.status == "partial":
            result.message += "部分週次未能取得，這是已取得資料中的最早時段。"
        return result
    result.status = "retry_needed"
    result.message = "已嘗試確認候選時段，但院方頁面無法確認或暫時無法連線。尚未掛號，請重新安排或查看其他時段。"
    return result
