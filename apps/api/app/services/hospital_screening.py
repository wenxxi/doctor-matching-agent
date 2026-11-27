"""Fixed-target integration screening, not a booking API. Never accepts patient data."""
from datetime import date, datetime, timezone
from functools import lru_cache
from html.parser import HTMLParser
from http.cookiejar import CookieJar
import re
import ssl
from threading import Lock
from time import time
from urllib.error import HTTPError
from urllib.parse import urlencode, urljoin, urlsplit
from urllib.request import Request, build_opener, HTTPSHandler, HTTPCookieProcessor, HTTPRedirectHandler
from zoneinfo import ZoneInfo

import certifi

from app.services.provider_diagnostics import response_evidence

USER_AGENT = "DoctorMatchingAgent/0.1 (read-only source check)"
CANDIDATES = {
    "mmh_taipei_orthopedics": {"hospital": "台北馬偕", "hosts": {"www.mmh.org.tw"},
        "url": "https://www.mmh.org.tw/register_single_doctor.php?area=tp&depid=52&did=1459"},
    "ntuh_orthopedics": {"hospital": "台大總院", "hosts": {"registration.ntuh.gov.tw", "reg.ntuh.gov.tw"},
        "url": "https://registration.ntuh.gov.tw/WebReg/WebReg/RegDeptSchedule?ampmCode=A&realSubDeptCode=02&showBlock=B&vDeptCode=ORTH&vHospCode=T0"},
    "femh_orthopedics": {"hospital": "亞東醫院", "hosts": {"www.femh.org.tw"},
        "url": "https://www.femh.org.tw/webregs/RegSec1.aspx?ID=0287"},
    "skh_registration": {"hospital": "新光醫院", "hosts": {"www.skh.org.tw"},
        "url": "https://www.skh.org.tw/skh_regis/index.html"},
}
LOCKS = {key: Lock() for key in CANDIDATES}


class Inspection(HTMLParser):
    def __init__(self, html):
        super().__init__(convert_charrefs=True)
        self.text, self.inputs, self.forms, self.links = [], [], [], []
        self.anchor = None
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "input":
            self.inputs.append(attrs)
        elif tag == "form":
            self.forms.append(attrs)
        elif tag == "a":
            self.anchor = [attrs, []]

    def handle_endtag(self, tag):
        if tag == "a" and self.anchor is not None:
            attrs, pieces = self.anchor
            self.links.append((attrs, "".join(pieces).strip()))
            self.anchor = None

    def handle_data(self, data):
        self.text.append(data)
        if self.anchor is not None:
            self.anchor[1].append(data)

    def plain(self):
        return re.sub(r"\s+", " ", " ".join(self.text)).strip()


def allowed_url(url, hosts):
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.netloc not in hosts:
        raise ValueError("Unexpected screening destination")
    return url


class HospitalRedirects(HTTPRedirectHandler):
    def __init__(self, hosts):
        self.hosts = hosts

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        allowed_url(newurl, self.hosts)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class PublicNavigation:
    def __init__(self, spec):
        self.spec = spec
        self.opener = build_opener(HTTPSHandler(context=ssl.create_default_context(cafile=certifi.where())),
                                  HTTPCookieProcessor(CookieJar()), HospitalRedirects(spec["hosts"]))

    def page(self, url, public_selection=None, referer=None):
        allowed_url(url, self.spec["hosts"])
        if public_selection is not None:
            # Only the public selection form is navigated. Patient submission endpoints are never used.
            if (urlsplit(url).path not in {"/register_firstaction.php", "/register_action.php"}
                    or set(public_selection) != {"workflag", "area", "regdate", "schap", "dept", "dr"}):
                raise ValueError("Unsupported public navigation")
        headers = {"User-Agent": USER_AGENT}
        if referer:
            headers["Referer"] = allowed_url(referer, self.spec["hosts"])
        payload = urlencode(public_selection).encode() if public_selection is not None else None
        request = Request(url, data=payload, headers=headers)
        try:
            response = self.opener.open(request, timeout=12)
        except HTTPError as error:
            response = error
        with response:
            body = response.read(2_000_000)
            status = response.code
            evidence = response_evidence(response.headers, body)
            final_path = urlsplit(response.url).path  # Never persist selection/CSRF tokens from query strings.
        return status, body.decode("utf-8-sig", errors="replace"), evidence, final_path


def mmh_choices(html, today):
    result = []
    for attrs, label in Inspection(html).links:
        if ("可掛" not in label or "regbtn" not in attrs.get("class", "").split()
                or "disabled" in attrs or attrs.get("aria-disabled") == "true"
                or "disabled" in attrs.get("class", "").split()):
            continue
        match = re.fullmatch(r"\s*registergo\('(\d{4}-\d{2}-\d{2})',([123]),'(\d+)','(\d+)','([^']*)','(first|second)'\);\s*return false;\s*", attrs.get("onclick", ""))
        if not match:
            continue
        day, session, department, doctor, special, visit = match.groups()
        try:
            parsed = date.fromisoformat(day)
        except ValueError:
            continue
        if parsed <= today or department != "52" or special not in {"", "Array"}:
            continue
        result.append({"date": day, "session": {"1":"上午", "2":"下午", "3":"夜診"}[session],
                       "session_code": session, "department_code": department, "doctor_code": doctor,
                       "visit_type": visit})
    return sorted(result, key=lambda row: (row["date"], row["session_code"], row["visit_type"]))


def mmh_patient_verified(html, choice, doctor_name):
    page = Inspection(html)
    values = {item.get("name"): item.get("value", "") for item in page.inputs}
    return (any(form.get("action") == "registerdone.php" and form.get("method", "").lower() == "post" for form in page.forms)
            and {"txtID", "txtBirth", "txtwebword"}.issubset(values)
            and values.get("strSchdate") == choice["date"].replace("-", "/")
            and values.get("strDr") == choice["doctor_code"] and values.get("strDept") == choice["department_code"]
            and values.get("strSchap") == choice["session_code"] and doctor_name in page.plain())


def run_screening(candidate_id):
    spec = CANDIDATES[candidate_id]
    result = {"candidate_id": candidate_id, "hospital": spec["hospital"], "source_url": spec["url"],
              "checked_at": datetime.now(timezone.utc).isoformat(), "registration_submitted": False,
              "http_accessible": False, "schedule_verified": False, "patient_form_verified": False,
              "patient_entries": [], "status": "unavailable", "note": "Research only; not yet added to recommendations."}
    client = PublicNavigation(spec)
    try:
        status, html, evidence, _ = client.page(spec["url"])
        result.update(http_status=status, response_evidence=evidence)
        if status != 200 or evidence["classification"] == "cloudflare_challenge":
            result["status"] = "blocked_or_http_error"
            return result
        result["http_accessible"] = True
        result["status"] = "entry_page_only"
        today = datetime.now(ZoneInfo("Asia/Taipei")).date()
        if candidate_id == "mmh_taipei_orthopedics":
            heading = re.search(r"<h2\b[^>]*class=['\"]event-hed-title['\"][^>]*>(.*?)</h2>", html, re.S)
            name = Inspection(heading[1]).plain() if heading else ""
            choices = mmh_choices(html, today)
            result.update(doctor_name=name, open_choice_count=len(choices), schedule_verified=bool(name and choices and "台北院區 - 骨科" in Inspection(html).plain()))
            if not result["schedule_verified"]:
                return result
            for visit in ("first", "second"):
                choice = next((row for row in choices if row["visit_type"] == visit), None)
                if choice is None:
                    continue
                public = {"workflag":"register", "area":"", "regdate":choice["date"], "schap":choice["session_code"],
                          "dept":choice["department_code"], "dr":choice["doctor_code"]}
                target = "https://www.mmh.org.tw/" + ("register_firstaction.php" if visit == "first" else "register_action.php")
                code, entry, ev, path = client.page(target, public, spec["url"])
                verified = code == 200 and ev["classification"] != "cloudflare_challenge" and mmh_patient_verified(entry, choice, name)
                result["patient_entries"].append({"date":choice["date"], "session":choice["session"], "visit_type":visit,
                    "http_status":code, "entry_path":path, "verified":verified, "response_evidence":ev,
                    "requirements":["患者證件號碼", "出生日期", "院方網路密碼（依院方規則）"]})
            result["patient_form_verified"] = bool(result["patient_entries"]) and all(row["verified"] for row in result["patient_entries"])
        elif candidate_id == "ntuh_orthopedics":
            links = [attrs["href"] for attrs, _ in Inspection(html).links if attrs.get("href", "").startswith("RegForm?newx=") and "avaliable" in attrs]
            if links:
                code, entry, ev, path = client.page(urljoin(spec["url"], links[-1]), referer=spec["url"])
                page = Inspection(entry)
                names = {item.get("name") for item in page.inputs}
                date_match = re.search(r"看診時間\s*(\d{3})\.(\d{1,2})\.(\d{1,2})", page.plain())
                day = date(int(date_match[1])+1911, int(date_match[2]), int(date_match[3])) if date_match else None
                verified = (code == 200 and ev["classification"] != "cloudflare_challenge" and day is not None and day > today
                            and "總院-骨科部" in page.plain()
                            and {"txtInputID", "txtBirthday_Year", "txtBirthday_Month", "txtBirthday_Day", "txtVerifyCode"}.issubset(names))
                result["schedule_verified"] = bool(verified)
                result["patient_form_verified"] = bool(verified)
                result["patient_entries"] = [{"date":day.isoformat() if day else None, "http_status":code, "entry_path":path,
                    "verified":bool(verified), "response_evidence":ev, "requirements":["患者證件號碼", "出生日期", "院方驗證碼", "頁面含 reCAPTCHA 機制"]}]
        elif candidate_id == "femh_orthopedics":
            result["note"] = "Only HTML access checked. Hidden example content must not be mistaken for real available slots; dynamic schedule analysis pending."
        else:
            result["note"] = "Only SPA entry HTML checked; dynamic schedule and patient-form access not yet verified."
        if result["patient_form_verified"]:
            result["status"] = "public_schedule_and_patient_entry_verified"
    except (OSError, ValueError) as error:
        result.update(status="unavailable", error_type=type(error).__name__)
    return result


@lru_cache(maxsize=32)
def cached_screening(candidate_id, window):
    return run_screening(candidate_id)


def screen_candidate(candidate_id):
    with LOCKS[candidate_id]:
        return cached_screening(candidate_id, int(time() // 600))
