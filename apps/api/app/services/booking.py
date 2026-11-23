import base64
import json
import re
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from http.cookiejar import CookieJar
from threading import Lock, Timer
from urllib.parse import quote, urlencode, urljoin, urlsplit
from urllib.request import HTTPCookieProcessor, HTTPRedirectHandler, Request, build_opener

from app.booking_schemas import (
    BookingContinueRequest, BookingField, BookingPatientRequest, BookingStateResponse,
)
from app.schemas import AppointmentSlotResponse
from app.services.appointment_agent import verify_checkin_page
from app.services.appointments import BASE_URL, get_appointments


LABELS = {
    "name": "姓名", "birthday": "出生日期", "idNumber": "證號", "patNumber": "病歷號",
    "verification": "驗證碼", "tel": "電話", "phone": "電話", "mobile": "手機",
    "email": "電子郵件", "address": "地址", "sex": "性別", "gender": "性別",
    "city": "縣市", "district": "鄉鎮市區", "zipCode": "郵遞區號",
}


class BookingError(Exception):
    pass


def hospital_url(url: str) -> str:
    target = urljoin(BASE_URL, url)
    parsed = urlsplit(target)
    if parsed.scheme != "https" or parsed.netloc != "register.cgmh.org.tw":
        raise BookingError("院方頁面導向其他網站，已停止處理。")
    return target


class HospitalRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, newurl):
        hospital_url(newurl)
        if code in {307, 308} and request.get_method() == "POST":
            raise BookingError("院方要求重新送出，已停止以避免重複掛號。")
        return super().redirect_request(request, response, code, message, headers, newurl)


class HospitalClient:
    def __init__(self):
        self.opener = build_opener(HTTPCookieProcessor(CookieJar()), HospitalRedirectHandler())
        self.referer = BASE_URL + "/Register/3"

    def request(self, url: str, fields: dict[str, str] | None = None) -> tuple[bytes, str]:
        target = hospital_url(url)
        data = urlencode(fields).encode("utf-8") if fields is not None else None
        request = Request(target, data=data, headers={
            "User-Agent": "DoctorMatchingAgent/0.1",
            "Referer": self.referer, "Origin": BASE_URL,
            "Content-Type": "application/x-www-form-urlencoded",
        })
        with self.opener.open(request, timeout=12) as response:
            hospital_url(response.geturl())
            content = response.read(2_000_001)
            if len(content) > 2_000_000:
                raise BookingError("院方回應過大，請至院方確認。")
            content_type = response.headers.get_content_type()
        if not target.endswith("/Content/BuildCaptcha.aspx"):
            self.referer = target
        return content, content_type

    def page(self, url: str, fields: dict[str, str] | None = None) -> str:
        content, _ = self.request(url, fields)
        return content.decode("utf-8-sig")

    def captcha(self) -> str:
        content, mime = self.request("/Content/BuildCaptcha.aspx")
        if mime not in {"image/png", "image/jpeg", "image/gif"} or len(content) > 500_000:
            raise BookingError("無法取得院方驗證碼，請重新開始。")
        return f"data:{mime};base64,{base64.b64encode(content).decode('ascii')}"


@dataclass
class HospitalForm:
    action: str
    hidden: dict[str, str] = field(default_factory=dict)
    fields: list[BookingField] = field(default_factory=list)
    unsupported: bool = False


class HospitalPageParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.forms: list[HospitalForm] = []
        self.current: HospitalForm | None = None
        self.select: BookingField | None = None
        self.option: dict[str, str] | None = None
        self.option_selected = False
        self.text: list[str] = []
        self.skip_depth = 0
        self.label_for: str | None = None
        self.label_text: list[str] | None = None
        self.label_controls: list[tuple[BookingField, str | None]] = []
        self.field_ids: dict[str, BookingField] = {}

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag in {"script", "style"}:
            self.skip_depth += 1
        if tag == "form":
            action = attributes.get("action", "")
            path = urlsplit(urljoin(BASE_URL, action)).path
            if attributes.get("method", "").lower() == "post" and re.fullmatch(r"/Checkin[A-Za-z]*/3/[A-Za-z0-9/]+", path):
                self.current = HospitalForm(hospital_url(action))
                self.forms.append(self.current)
        if self.current is None:
            return
        if tag == "label":
            self.label_for = attributes.get("for")
            self.label_text = []
            self.label_controls = []
        name = attributes.get("name", "")
        if tag == "input" and name:
            kind = attributes.get("type", "text").lower()
            value = attributes.get("value", "")
            if kind == "hidden":
                self.current.hidden[name] = value
            elif kind in {"submit", "button", "reset"} or "disabled" in attributes:
                return
            elif kind == "file":
                self.current.unsupported = True
            elif kind == "radio":
                existing = next((item for item in self.current.fields if item.name == name), None)
                if existing is None:
                    existing = BookingField(name=name, label=LABELS.get(name, attributes.get("title") or name), kind="select")
                    self.current.fields.append(existing)
                existing.options.append({"value": value, "label": attributes.get("title") or value})
                if "checked" in attributes:
                    existing.value = value
                if self.label_text is not None:
                    self.label_controls.append((existing, value))
            else:
                supported_kind = kind if kind in {"date", "email", "tel", "number", "checkbox"} else "text"
                self.current.fields.append(BookingField(
                    name=name, label=attributes.get("placeholder") or attributes.get("title") or LABELS.get(name, name),
                    kind=supported_kind, value=(value or "on") if kind == "checkbox" and "checked" in attributes else ("" if kind == "checkbox" else value),
                    required="required" in attributes,
                ))
                if self.label_text is not None:
                    self.label_controls.append((self.current.fields[-1], None))
            if self.current.fields and attributes.get("id"):
                self.field_ids[attributes["id"]] = self.current.fields[-1]
        if tag == "select" and name:
            self.select = BookingField(name=name, label=attributes.get("title") or LABELS.get(name, name), kind="select", required="required" in attributes)
            self.current.fields.append(self.select)
            if attributes.get("id"):
                self.field_ids[attributes["id"]] = self.select
            if self.label_text is not None:
                self.label_controls.append((self.select, None))
        if tag == "option" and self.select is not None:
            self.option = {"value": attributes.get("value", ""), "label": ""}
            self.option_selected = "selected" in attributes
        if tag == "textarea":
            self.current.unsupported = True

    def handle_data(self, data):
        if not self.skip_depth:
            self.text.append(data)
        if self.option is not None:
            self.option["label"] += data
        if self.label_text is not None:
            self.label_text.append(data)

    def handle_endtag(self, tag):
        if tag in {"script", "style"} and self.skip_depth:
            self.skip_depth -= 1
        if tag == "form":
            self.current = None
        if tag == "option" and self.option is not None and self.select is not None:
            self.select.options.append(self.option)
            if self.option_selected:
                self.select.value = self.option["value"]
            self.option = None
        if tag == "select":
            self.select = None
        if tag == "label" and self.label_text is not None:
            label = " ".join("".join(self.label_text).split())[:120]
            if label:
                if self.label_for in self.field_ids:
                    self.field_ids[self.label_for].label = label
                for control, radio_value in self.label_controls:
                    if radio_value is None:
                        control.label = label
                    else:
                        for option in control.options:
                            if option["value"] == radio_value:
                                option["label"] = label
            self.label_text = None
            self.label_controls = []


def parse_hospital_page(html: str) -> HospitalPageParser:
    parser = HospitalPageParser()
    parser.feed(html)
    return parser


@dataclass
class BookingSession:
    client: HospitalClient
    doctor_name: str
    slot: AppointmentSlotResponse
    expires_at: datetime
    form: HospitalForm
    status: str = "awaiting_patient"
    response: BookingStateResponse | None = None
    lock: Lock = field(default_factory=Lock)
    rounds: int = 0
    step_token: str = ""


SESSIONS: dict[str, BookingSession] = {}
SESSIONS_LOCK = Lock()


def get_session(token: str) -> BookingSession:
    with SESSIONS_LOCK:
        session = SESSIONS.get(token)
        if session is None or session.expires_at <= datetime.now(timezone.utc):
            SESSIONS.pop(token, None)
            raise BookingError("掛號工作階段已過期，請重新選擇時段。")
        return session


def start_booking(doctor: dict[str, str], registration_url: str) -> BookingStateResponse:
    snapshot = get_appointments(doctor)
    slot = next((item for item in snapshot.slots if item.registration_url == registration_url), None)
    if slot is None:
        raise BookingError("這個時段已無法確認，請重新查詢。")
    with SESSIONS_LOCK:
        expired = [token for token, item in SESSIONS.items() if item.expires_at <= datetime.now(timezone.utc)]
        for token in expired:
            del SESSIONS[token]
        if len(SESSIONS) >= 100:
            raise BookingError("目前掛號使用人數較多，請稍後重試。")
    client = HospitalClient()
    html = client.page(slot.registration_url)
    if not verify_checkin_page(html, slot, doctor["doctor_name_zh"]):
        raise BookingError("院方掛號頁已改變，請重新選擇時段。")
    parser = parse_hospital_page(html)
    expected = slot.registration_url.replace("/Checkin/3/", "/CheckinConfirm/3/", 1)
    form = next((item for item in parser.forms if item.action == expected), None)
    if form is None or not form.hidden.get("__RequestVerificationToken"):
        raise BookingError("無法建立院方掛號工作階段。")
    expected_date, expected_doctor, expected_session = slot.registration_url.split("/")[-3:]
    expected_fields = {"hospitalID": "3", "opdDate": expected_date, "doctorID": expected_doctor, "opdTimeID": expected_session}
    if any(form.hidden.get(name) != value for name, value in expected_fields.items()):
        raise BookingError("院方表單的醫師或日期不一致，請重新查詢。")
    if form.hidden.get("canReg") == "N":
        raise BookingError("院方目前不接受這個時段掛號，請重新選擇。")
    captcha = client.captcha()
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)
    token = secrets.token_urlsafe(32)
    session = BookingSession(client, doctor["doctor_name_zh"], slot, expires_at, form)
    with SESSIONS_LOCK:
        SESSIONS[token] = session
    expiry_timer = Timer(600, close_booking, args=(token,))
    expiry_timer.daemon = True
    expiry_timer.start()
    return BookingStateResponse(
        status="awaiting_patient", token=token, expires_at=expires_at, captcha_image=captcha,
        message="請填寫患者資料與院方驗證碼。本流程以健保身分、到院看診送出。",
    )


def finish_response(session: BookingSession, html: str) -> BookingStateResponse:
    parser = parse_hospital_page(html)
    text = " ".join(parser.text)
    receipt = re.search(r"(?:掛號序號|就診序號|看診序號|掛號號碼|掛號號次|序號)\s*[:：]?\s*(\d{1,5})(?!\d)", text)
    matching_slot = session.doctor_name in text and (
        session.slot.date in text or session.slot.date.replace("-", "/") in text
    ) and session.slot.session in text
    if "掛號成功" in text and receipt and matching_slot and not re.search(r"掛號(?:失敗|未成功|不成功)", text):
        session.status = "confirmed"
        session.form = HospitalForm("")
        session.client = HospitalClient()
        return BookingStateResponse(status="confirmed", receipt_number=receipt[1], message="院方已回覆掛號成功。請保存就診日期、醫師與掛號序號。")
    forms = [item for item in parser.forms if item.hidden.get("__RequestVerificationToken")]
    if len(forms) == 1 and not forms[0].unsupported and session.rounds < 3:
        form = forms[0]
        expected_parts = session.slot.registration_url.split("/")[-3:]
        if urlsplit(form.action).path.split("/")[-3:] != expected_parts:
            session.status = "needs_official"
            return BookingStateResponse(status="needs_official", message="院方後續頁面的醫師或時段不一致，已停止。請至院方確認掛號狀態。")
        session.form = form
        session.status = "awaiting_confirmation"
        session.step_token = secrets.token_urlsafe(32)
        captcha = session.client.captcha() if any(item.name == "verification" for item in form.fields) else None
        return BookingStateResponse(status="awaiting_confirmation", step_token=session.step_token, fields=form.fields, captcha_image=captcha, message="院方需要你確認或補充以下資料。請核對醫師與日期，確認後送出下一步。")
    session.status = "needs_official"
    return BookingStateResponse(status="needs_official", message="院方回傳了目前無法辨識的結果或需要額外作業。尚無成功回條，請至院方掛號查詢確認，勿重複送出。")


def submit_patient(token: str, patient: BookingPatientRequest) -> BookingStateResponse:
    session = get_session(token)
    with session.lock:
        if session.status != "awaiting_patient":
            return session.response or BookingStateResponse(status="unknown", message="此工作階段已送出或已停止，請勿重複掛號。")
        session.status = "submitting"
        fields = dict(session.form.hidden)
        identifier = patient.id_number.get_secret_value().upper()
        fields.update({
            "idType": patient.id_type, "idNumber": identifier,
            "birthday": patient.birthday.strftime("%Y%m%d"), "CKROC_birthday": "on",
            "verification": patient.verification.get_secret_value(), "insuuid": "A",
            "CK_insuuid2": "on", "Treatmentmethod": "1", "telvideo": "",
        })
        query = {key: fields.get(key, "") for key in (
            "hospitalID", "idType", "birthday", "verification", "deptID", "opdDate", "opdTimeID", "doctorID", "thisDept",
        )}
        query.update({"patNumber": identifier if patient.id_type == "1" else "", "idNumber": "" if patient.id_type == "1" else identifier, "CKROC_birthday": "TRUE"})
        try:
            payload = json.dumps([{"name": key, "value": value} for key, value in query.items()], ensure_ascii=False, separators=(",", ":"))
            content, _ = session.client.request("/Ajax", {
                "__RequestVerificationToken": fields["__RequestVerificationToken"],
                "Func": "PatQueryChick", "Val": quote(payload, safe=";/?:@&=+$,-_.!~*'()#"),
            })
            result = json.loads(content)
            if result.get("Func") != "PatQueryChick":
                raise BookingError("院方患者驗證回應格式已變更。")
            if result.get("codeError") == "Y":
                session.status = "awaiting_patient"
                response = BookingStateResponse(status="captcha_error", captcha_image=session.client.captcha(), message="院方回覆驗證碼不正確，請輸入新的驗證碼。")
                session.response = response
                return response
            if result.get("assError") != "N":
                session.status = "rejected"
                response = BookingStateResponse(status="rejected", message="院方未接受患者資料或掛號資格，請確認資料後重新開始；未送出下一步。")
                session.response = response
                return response
            if fields.get("isFull") == "Y":
                department_only = "科初診" in fields.get("memo", "")
                eligible = result.get("isDptFirst") == "Y" if department_only else result.get("isFirst") == "Y"
                if not eligible:
                    session.status = "rejected"
                    response = BookingStateResponse(status="rejected", message="院方判定不符合這個額滿門診的初診資格，請重新選擇時段。")
                    session.response = response
                    return response
            records = json.loads(result.get("PatQuery", "[]"))
            if not records or not isinstance(records[0], dict):
                raise BookingError("院方未提供可用的患者驗證結果。")
            if result.get("otherHaveReg") == "Y" and result.get("otherHospitalID") not in {None, "", "3"}:
                session.status = "needs_official"
                response = BookingStateResponse(status="needs_official", message="院方要求處理跨院病歷整合，請至院方完成同意程序。本次未繼續掛號。")
                session.response = response
                return response
            fields.update({"patNumber": str(records[0].get("patNumber", "")), "name": str(records[0].get("name", ""))})
            for key in ("isFirst", "otherHaveReg", "otherHospitalID", "KD01", "KD02", "KD03", "KD04", "KD05", "KD06", "NHIQP7012memo"):
                fields[key] = str(result.get(key) or "")
            html = session.client.page(session.form.action, fields)
            session.rounds += 1
            response = finish_response(session, html)
        except (OSError, ValueError, KeyError, TypeError, BookingError):
            session.status = "unknown"
            response = BookingStateResponse(status="unknown", message="院方送出結果無法確認。系統不會自動重送，請先至院方掛號查詢確認，避免重複掛號。")
        session.response = response
        return response


def continue_booking(token: str, request: BookingContinueRequest) -> BookingStateResponse:
    session = get_session(token)
    with session.lock:
        if session.status != "awaiting_confirmation":
            return session.response or BookingStateResponse(status="unknown", message="此工作階段無法繼續送出，請確認院方掛號狀態。")
        if not secrets.compare_digest(request.step_token, session.step_token):
            return session.response or BookingStateResponse(status="unknown", message="此步驟已處理，請勿重複送出。")
        allowed = {item.name: item for item in session.form.fields}
        if set(request.fields) - set(allowed):
            raise BookingError("表單欄位已變更，請重新核對。")
        fields = dict(session.form.hidden)
        for name, item in allowed.items():
            value = request.fields.get(name, item.value)
            if len(value) > 500 or (item.required and not value):
                raise BookingError("請填妥院方要求的欄位。")
            if item.kind == "select" and value not in {option["value"] for option in item.options}:
                raise BookingError("請選擇院方提供的選項。")
            if item.kind == "checkbox" and not value:
                continue
            fields[name] = value
        session.status = "submitting"
        try:
            html = session.client.page(session.form.action, fields)
            session.rounds += 1
            response = finish_response(session, html)
        except (OSError, ValueError, BookingError):
            session.status = "unknown"
            response = BookingStateResponse(status="unknown", message="送出後未能確認結果。請先至院方掛號查詢確認，系統不會自動重送。")
        session.response = response
        return response


def refresh_captcha(token: str) -> BookingStateResponse:
    session = get_session(token)
    with session.lock:
        if session.status != "awaiting_patient":
            raise BookingError("目前無法更新驗證碼，請確認掛號狀態。")
        return BookingStateResponse(status="awaiting_patient", captcha_image=session.client.captcha(), message="已更新院方驗證碼。")


def close_booking(token: str) -> BookingStateResponse:
    with SESSIONS_LOCK:
        SESSIONS.pop(token, None)
    return BookingStateResponse(status="closed", message="已清除本站暫存工作階段。這不會取消已向院方完成的掛號。")
