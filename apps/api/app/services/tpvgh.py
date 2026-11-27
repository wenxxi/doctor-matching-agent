"""Taipei Veterans public profile/schedule adapter. GET only; registration stays at hospital."""
from datetime import datetime, timezone
from functools import lru_cache
from html.parser import HTMLParser
import re
import ssl
import logging
from threading import Lock
from time import time, monotonic
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from zoneinfo import ZoneInfo

import certifi
from app.services.security import provider_request

from app.schemas import AppointmentsResponse, AppointmentSlotResponse, AppointmentPreparationResponse
from app.services.processed_data import load_provider_metadata
from app.services.provider_diagnostics import response_evidence, SAMPLE_LIMIT

PROFILE_BASE = "https://www.vghtpe.gov.tw/"
REG_BASE = "https://www6.vghtpe.gov.tw/reg/"
LOCKS = tuple(Lock() for _ in range(32))
logger = logging.getLogger(__name__)
BLOCKED_UNTIL = 0.0
BLOCKED_EVIDENCE = {}
BLOCK_LOCK = Lock()
BLOCKED_MESSAGE = "台北榮總目前限制本站查詢，暫時無法驗證該院時段；這不代表沒有名額。可保留條件稍後重試，或自行選擇改查林口長庚。"


class Markup(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.text = []
        self.inputs = []
        self.forms = []

    def handle_data(self, value):
        self.text.append(value)

    def handle_starttag(self, tag, attrs):
        if tag == "input":
            self.inputs.append(dict(attrs))
        elif tag == "form":
            self.forms.append(dict(attrs))


def markup(html):
    parser = Markup()
    parser.feed(html)
    return parser


def plain(html):
    return re.sub(r"\s+", " ", " ".join(markup(html).text)).strip()


def fetch_public(url):
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.netloc not in {"www.vghtpe.gov.tw", "www6.vghtpe.gov.tw"}:
        raise ValueError("Unexpected hospital origin")
    request = Request(url, headers={"User-Agent": "DoctorMatchingAgent/0.1 (read-only source check)"})
    with provider_request("tpvgh"), urlopen(request, timeout=10, context=ssl.create_default_context(cafile=certifi.where())) as response:
        if urlsplit(response.url).netloc != parsed.netloc:
            raise ValueError("Unexpected redirect")
        html = response.read(2_000_000).decode("utf-8-sig")
    if "challenge-platform" in html or "cf-chl" in html or "臺北榮" not in html:
        raise ValueError("Hospital page unavailable or verification required")
    return html, datetime.now(timezone.utc)


@lru_cache(maxsize=256)
def cached_public(url, window):
    return fetch_public(url)


def public_page(url):
    with LOCKS[hash(url) % len(LOCKS)]:
        return cached_public(url, int(time() // 120))


def timetable_url(doctor, patient_type="returning"):
    provider_id = load_provider_metadata().get(doctor["doctor_id"], {}).get("registration_doctor_id", "")
    if not re.fullmatch(r"DOC[A-Za-z0-9]+", provider_id):
        return None
    return REG_BASE + "docTimetable.do?" + urlencode({"docid": provider_id, "type": "first" if patient_type == "first_visit" else "return"})


def parse_profile(html):
    html = re.sub(r"<!--.*?-->", lambda match: match[0] if re.search(r"醫療專長|證照", match[0]) else "", html, flags=re.S)
    body = html.split("<main>", 1)[-1]
    heading = re.search(r"<h2\b[^>]*>(.*?)</h2>", body, re.S)
    section = re.search(r"<!--\s*醫療專長\s*-->(.*?)<!--\s*證照\s*-->", body, re.S)
    if not heading or not section:
        raise ValueError("Profile lacks name or specialty section")
    name = re.sub(r"\s+", "", re.split(r"\s*[（(]", plain(heading[1]), 1)[0])
    listing = re.search(r"<(?:ol|ul)\b[^>]*>(.*?)</(?:ol|ul)>", section[1], re.S)
    specialties = [plain(item) for item in re.findall(r"<li\b[^>]*>(.*?)</li>", listing[1] if listing else "", re.S)]
    ids = set(re.findall(r"docTimetable\.do\?docid=(DOC[A-Za-z0-9]+)", body))
    if not re.fullmatch(r"[\u4e00-\u9fff·．]{2,8}", name) or not specialties or len(ids) > 1:
        raise ValueError("Ambiguous profile identity")
    return name, "；".join(specialties), next(iter(ids), "")


def parse_slots(html, doctor_name, url, patient_type, today):
    page = markup(html)
    input_names = {item.get("name") for item in page.inputs}
    visit_types = {item.get("value") for item in page.inputs if item.get("name") == "type"}
    # This page contains both the live choices and patient entry form.
    if (not any(form.get("name") == "oregForm" for form in page.forms)
            or not {"pid", "pbirth_mm", "pbirth_dd"}.issubset(input_names)
            or visit_types != {"first" if patient_type == "first_visit" else "return"}):
        raise ValueError("Missing patient entry form")
    results = {}
    for row in re.findall(r"<tr\b[^>]*>(.*?)</tr>", html, re.S):
        parsed = markup(row)
        inputs = {item.get("name"): item for item in parsed.inputs}
        choice = inputs.get("regKey", {})
        key = choice.get("value", "")
        name = re.sub(r"\s+", "", inputs.get("regDocName", {}).get("value", ""))
        date_label = inputs.get("regDate", {}).get("value", "")
        if (choice.get("type", "").lower() != "radio" or "disabled" in choice
                or not re.fullmatch(r"\d{13}", key) or name != doctor_name
                or "可掛號" not in plain(row)
                or re.search(r"額滿|休診|已逾|停診|關診", plain(row))):
            continue
        try:
            date = datetime.strptime(key[:8], "%Y%m%d").date().isoformat()
        except ValueError:
            continue
        session = next((value for value in ("上午", "下午", "夜診") if value in date_label), None)
        if session is None and re.search(r"晚|夜", date_label):
            session = "夜診"
        if not session or date < today or date not in date_label:
            continue
        # The link opens the doctor's live table; the user must select this date there.
        results[key] = AppointmentSlotResponse(date=date, session=session,
            eligibility="初診可掛（從未在本院看診）" if patient_type == "first_visit" else "一般掛號（本院複診）",
            registration_url=url, provider_slot_id=key, booking_mode="official_handoff")
    return sorted(results.values(), key=lambda slot: (slot.date, ["上午", "下午", "夜診"].index(slot.session), slot.provider_slot_id))


def get_appointments(doctor, patient_type="returning", fresh=False):
    global BLOCKED_UNTIL, BLOCKED_EVIDENCE
    url = timetable_url(doctor, patient_type)
    result = AppointmentsResponse(doctor_id=doctor["doctor_id"], status="unavailable", registration_url=url,
        schedule_urls=[url] if url else [], checked_at=None, slots=[], message="暫時無法確認榮總門診，請稍後重試。")
    if not url:
        result.message = "尚未確認這位醫師的院方掛號識別碼，暫不提供時段。"
        return result
    with BLOCK_LOCK:
        if monotonic() < BLOCKED_UNTIL:
            result.failure_code, result.provider_http_status = "provider_http_error", 403
            result.message = BLOCKED_MESSAGE
            result.failure_evidence = {**BLOCKED_EVIDENCE, "evidence_origin": "cached_denial"}
            return result
    try:
        html, checked = fetch_public(url) if fresh else public_page(url)
        result.slots = parse_slots(html, doctor["doctor_name_zh"], url, patient_type,
                                   datetime.now(ZoneInfo("Asia/Taipei")).date().isoformat())
        result.checked_at = checked
        result.status = "available" if result.slots else "no_slots"
        result.message = "榮總公開門診表目前可選的時段；需至院方選取日期並完成身分驗證，尚未保留名額。" if result.slots else "院方未顯示這位醫師可選的門診，可能額滿、休診或尚未開放。"
    except HTTPError as error:
        result.failure_code = "provider_http_error"
        result.provider_http_status = error.code
        body = b""
        try:
            if error.fp is not None:
                body = error.read(SAMPLE_LIMIT)
        except OSError:
            pass
        finally:
            error.close()
        result.failure_evidence = response_evidence(error.headers, body)
        if error.code == 403:
            with BLOCK_LOCK:
                BLOCKED_UNTIL = monotonic() + 300
                BLOCKED_EVIDENCE = dict(result.failure_evidence)
    except URLError as error:
        result.failure_code = "provider_tls_error" if isinstance(error.reason, ssl.SSLCertVerificationError) else "provider_network_error"
    except TimeoutError:
        result.failure_code = "provider_timeout"
    except (OSError, ValueError) as error:
        result.failure_code = "provider_format_error" if isinstance(error, ValueError) else "provider_network_error"
    if result.failure_code:
        # No URL, query, credentials, patient data, or raw upstream exception text.
        logger.warning("TPVGH read-only check failed: code=%s http_status=%s", result.failure_code, result.provider_http_status)
    if result.provider_http_status == 403:
        result.message = BLOCKED_MESSAGE
    return result


def prepare(doctor, request):
    from app.services.appointment_agent import matches_preferences
    result = AppointmentPreparationResponse(doctor_id=doctor["doctor_id"], status="unavailable",
        message="榮總需要先確認全院初診或複診；科初診與不確定尚不足以確認資格。", booking_mode="official_handoff")
    if request.patient_type not in {"first_visit", "returning"}:
        return result
    snapshot = get_appointments(doctor, request.patient_type, fresh=True)
    result.steps = ["唯讀核對榮總醫師識別碼、門診可選狀態與患者資料欄位。"]
    if snapshot.status == "unavailable":
        result.message = snapshot.message
        result.failure_code = snapshot.failure_code
        result.provider_http_status = snapshot.provider_http_status
        return result
    result.verified_at = snapshot.checked_at
    matching = [slot for slot in snapshot.slots if matches_preferences(slot, request)]
    result.candidate_count = len(matching)
    result.attempted_count = 1
    if not matching:
        result.status = "no_match"
        result.message = "沒有符合目前日期、星期、時段與初複診條件的時段。"
        return result
    result.status = "official_handoff"
    result.selected_slot = matching[0]
    result.verified_at = snapshot.checked_at
    result.message = "已找到符合條件且院方目前可選的最早時段。請至榮總醫師掛號頁選取相同日期與時段，完成患者資料及院方驗證；本站未保留名額，也未完成掛號。"
    return result
