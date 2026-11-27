import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from functools import lru_cache
from html.parser import HTMLParser
from time import time
from threading import Lock
from urllib.parse import urljoin
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from app.schemas import AppointmentsResponse, AppointmentSlotResponse


BASE_URL = "https://register.cgmh.org.tw"
REGISTRATION_URL = f"{BASE_URL}/Register/3"
DEPARTMENT_ALIASES = {
    "骨科部": ("骨科",),
    "神經內科": ("腦神經內科",),
    "神經外科": ("腦神經外科",),
    "胸腔內科": ("呼吸胸腔科",),
    "胸腔外科": ("胸腔及食道外科",),
    "心臟血管外科": ("心臟外科", "動靜脈血管外科"),
    "新陳代謝科": ("內分泌暨新陳代謝科",),
    "風濕免疫科": ("風濕過敏免疫科及關節炎門診",),
    "血液科": ("血液病及淋巴瘤門診",),
    "肝臟移植外科": ("肝臟及器官移植門診",),
    "兒科": ("兒童內科",),
    "婦產科": ("婦產科", "不孕症門診"),
}
SESSION_NAMES = {"1": "上午", "2": "下午", "3": "夜診"}
PAGE_LOCKS = tuple(Lock() for _ in range(32))


class LinkParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links: list[tuple[str, str, str]] = []
        self.current: tuple[str, str] | None = None
        self.parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            attributes = dict(attrs)
            self.current = (attributes.get("href", ""), attributes.get("class", ""))
            self.parts = []

    def handle_data(self, data):
        if self.current is not None:
            self.parts.append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self.current is not None:
            href, classes = self.current
            self.links.append((href, "".join(self.parts).strip(), classes))
            self.current = None


def parse_links(html: str) -> list[tuple[str, str, str]]:
    parser = LinkParser()
    parser.feed(html)
    return parser.links


def registration_url_for(doctor: dict[str, str]) -> str | None:
    if doctor["doctor_id"].startswith("TPVGH_MAIN_"):
        from app.services.tpvgh import timetable_url
        return timetable_url(doctor)
    if doctor["doctor_id"].startswith("CGMH_LINKOU_"):
        return REGISTRATION_URL
    return None


@lru_cache(maxsize=128)
def cached_page(url: str, cache_window: int) -> tuple[str, datetime]:
    return fetch_live_page(url)


def fetch_page(url: str, cache_window: int) -> tuple[str, datetime]:
    # Concurrent checks for doctors in one department share the same schedule.
    with PAGE_LOCKS[hash(url) % len(PAGE_LOCKS)]:
        return cached_page(url, cache_window)


def fetch_live_page(url: str) -> tuple[str, datetime]:
    request = Request(url, headers={"User-Agent": "DoctorMatchingAgent/0.1"})
    with urlopen(request, timeout=8) as response:
        html = response.read(2_000_000).decode("utf-8-sig")
    if "看診" not in html or "掛號" not in html:
        raise ValueError("Unexpected hospital page")
    return html, datetime.now(timezone.utc)


def parse_slots(html: str, doctor_name: str, today: str) -> list[AppointmentSlotResponse]:
    slots = []
    for href, label, classes in parse_links(html):
        match = re.fullmatch(r"/Checkin/3/[A-Za-z0-9]+/(\d{8})/(\d+)/(\d)", href)
        name = re.match(r"^\d+\s+([^\s(（]+)", label)
        if not match or not name or name[1] != doctor_name or "state-full" in classes:
            continue
        date_text, _, session = match.groups()
        try:
            date = datetime.strptime(date_text, "%Y%m%d").date().isoformat()
        except ValueError:
            continue
        if date < today or session not in SESSION_NAMES or "停診" in label:
            continue
        if "科初診可掛" in label:
            eligibility = "科初診可掛（半年內未看過該科）"
        elif "初診可掛" in label:
            eligibility = "初診可掛（從未在本院看診）"
        elif "額滿" in label:
            continue
        else:
            eligibility = "一般掛號（資格以院方確認為準）"
        slots.append(AppointmentSlotResponse(
            date=date, session=SESSION_NAMES[session], eligibility=eligibility,
            registration_url=urljoin(BASE_URL, href),
        ))
    return slots


def get_appointments(doctor: dict[str, str]) -> AppointmentsResponse:
    if doctor["doctor_id"].startswith("TPVGH_MAIN_"):
        from app.services.tpvgh import get_appointments as tpvgh_appointments
        return tpvgh_appointments(doctor)
    registration_url = registration_url_for(doctor)
    result = AppointmentsResponse(
        doctor_id=doctor["doctor_id"], status="unsupported", registration_url=registration_url,
        schedule_urls=[], checked_at=None, slots=[], message="目前僅支援林口長庚公開掛號資訊。",
    )
    if registration_url is None:
        return result
    result.status = "unavailable"
    result.message = "暫時無法取得院方時段，請前往官方掛號頁查詢。"
    cache_window = int(time() // 120)
    try:
        index, _ = fetch_page(REGISTRATION_URL, cache_window)
        names = DEPARTMENT_ALIASES.get(doctor["department_zh"], (doctor["department_zh"],))
        departments = sorted({urljoin(BASE_URL, href) for href, label, _ in parse_links(index)
                              if label in names and re.fullmatch(r"/Department_WEEK/3/[A-Za-z0-9]+", href)})
        if not departments:
            return result
        result.schedule_urls = departments
        urls = [f"{department}?WEEK={week}" for department in departments for week in range(1, 5)]
        today = datetime.now(ZoneInfo("Asia/Taipei")).date().isoformat()
        failures = 0
        timestamps = []
        unique_slots = {}
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = [executor.submit(fetch_page, url, cache_window) for url in urls]
            for future in futures:
                try:
                    html, checked_at = future.result()
                    if "看診醫師時間表" not in html:
                        raise ValueError("Unexpected schedule page")
                    timestamps.append(checked_at)
                    for slot in parse_slots(html, doctor["doctor_name_zh"], today):
                        unique_slots[slot.registration_url] = slot
                except (OSError, ValueError):
                    failures += 1
        result.checked_at = min(timestamps) if timestamps else None
        result.slots = sorted(unique_slots.values(), key=lambda slot: (
            slot.date, list(SESSION_NAMES.values()).index(slot.session), slot.registration_url,
        ))
        if failures == len(urls):
            return result
        if failures:
            result.status = "partial"
            result.message = "部分週次查詢失敗；以下僅列出已取得的時段，可至官網確認完整資訊。"
        elif result.slots:
            result.status = "available"
            result.message = "以下為院方未來四週頁面提供的掛號入口；名額與初診資格以院方確認為準。"
        else:
            result.status = "no_slots"
            result.message = "院方未來四週頁面未找到這位醫師的可掛號入口；可能額滿、未排診或尚未開放，請至官網確認。"
    except (OSError, ValueError):
        pass
    return result
