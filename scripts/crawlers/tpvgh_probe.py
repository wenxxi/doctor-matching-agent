#!/usr/bin/env python3
"""Read-only access check. Never solve a challenge or submit a patient form."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import ssl
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


URLS = (
    "https://www.vghtpe.gov.tw/Teacher.action?tid=807",
    "https://www6.vghtpe.gov.tw/reg/home.do",
    "https://www6.vghtpe.gov.tw/reg/sectList.do?type=return",
)


def classify_page(status, html):
    if any(marker in html.lower() for marker in ("cf-chl", "challenge-platform", "正在執行安全驗證")):
        return "blocked_by_verification"
    if status != 200:
        return "http_error"
    if "臺北榮" not in html:
        return "unexpected_page"
    return "reachable_not_availability_verified"


def probe(url):
    try:
        # Use the project's CA bundle when available; never disable TLS validation.
        try:
            import certifi
            context = ssl.create_default_context(cafile=certifi.where())
        except ImportError:
            context = ssl.create_default_context()
        request = Request(url, headers={"User-Agent": "DoctorMatchingAgent/0.1 (read-only source check)"})
        try:
            response = urlopen(request, timeout=10, context=context)
        except HTTPError as error:
            response = error
        with response:
            html = response.read(2_000_000).decode("utf-8", errors="replace")
            status = response.code
        return {"url": url, "http_status": status, "status": classify_page(status, html)}
    except (URLError, OSError) as error:
        return {"url": url, "status": "connection_failed", "error_type": type(error).__name__}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rows = [probe(url) for url in URLS]
    report = {"checked_at": datetime.now(timezone.utc).isoformat(), "results": rows,
              "live_availability_verified": False, "registration_submitted": False}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    return 0 if all(row["status"] == "reachable_not_availability_verified" for row in rows) else 2


if __name__ == "__main__":
    raise SystemExit(main())
