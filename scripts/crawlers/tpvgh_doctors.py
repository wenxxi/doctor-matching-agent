#!/usr/bin/env python3
"""Fetch public TPVGH profiles into the shared normalized schema. No booking POSTs."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys
from time import time
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "apps/api"))
sys.path.insert(0, str(ROOT / "scripts/processors"))
from app.services.tpvgh import fetch_public, parse_profile
from build_orthopedics_concepts import DOCTOR_COLUMNS, doctor_scope, write_csv

# These are official profile-directory labels, mapped to the existing canonical departments.
DEPARTMENTS = {
    "骨科部": ["骨科部"], "神經內科": ["神經內科"], "神經外科": ["神經外科"],
    "心臟內科": ["心臟內科"], "胸腔內科": ["胸腔部"], "胃腸肝膽科": ["胃腸肝膽科"],
    "新陳代謝科": ["新陳代謝科"], "腎臟科": ["腎臟科"], "風濕免疫科": ["過敏免疫風濕科"],
    "感染醫學科": ["感染科"], "血液科": ["血液科"], "腫瘤科": ["腫瘤醫學部"],
    "一般外科": ["一般外科"], "大腸直腸肛門外科": ["大腸直腸外科"],
    "胸腔外科": ["胸腔外科"], "心臟血管外科": ["心臟血管外科"],
    "泌尿科": ["泌尿部"], "整形外科": ["整形外科"], "肝臟移植外科": ["移植外科"],
    "婦產科": ["婦女醫學部"], "兒科": ["兒童醫學部"], "眼科": ["眼科部"],
    "耳鼻喉頭頸外科": ["耳鼻喉頭頸醫學部"], "皮膚科": ["皮膚部"],
    "精神科": ["精神醫學部"], "復健科": ["復健醫學部"],
    "家庭醫學科": ["家庭醫學部"], "高齡醫學科": ["高齡醫學中心"],
    # Emergency/trauma is deliberately excluded pending a distinct outpatient equivalence review.
}


def crawl(departments, cache_dir):
    metadata, doctors, coverage = {}, [], []
    cache_dir.mkdir(parents=True, exist_ok=True)

    def profile(tid):
        path = cache_dir / (tid + ".html")
        if path.exists() and time() - path.stat().st_mtime < 86400:
            html = path.read_text(encoding="utf-8")
        else:
            html, _ = fetch_public("https://www.vghtpe.gov.tw/Teacher.action?tid=" + tid)
            path.write_text(html, encoding="utf-8")
        return parse_profile(html)

    for canonical in departments:
        records, failures = {}, []
        for source_department in DEPARTMENTS[canonical]:
            index_url = "https://www.vghtpe.gov.tw/docsearch.action?" + urlencode({"more": source_department, "q": source_department})
            html, _ = fetch_public(index_url)
            body = html.split('<div class="doctors photolist">', 1)[-1].split("</form>", 1)[0]
            tids = sorted(set(re.findall(r"Teacher\.action\?tid=(\d+)", body)))
            if len(tids) > 180:
                raise ValueError("Unexpectedly broad department result")
            # Two concurrent GETs; cache a profile once even if it belongs to several departments.
            with ThreadPoolExecutor(max_workers=2) as executor:
                futures = [(tid, executor.submit(profile, tid)) for tid in tids]
                for tid, future in futures:
                    try:
                        name, specialty, registration_id = future.result()
                    except (OSError, ValueError) as error:
                        failures.append({"profile_id": tid, "error_type": type(error).__name__})
                        continue
                    if canonical == "肝臟移植外科" and "肝" not in specialty:
                        failures.append({"profile_id": tid, "error_type": "NoLiverSpecialtyEvidence"})
                        continue
                    identifier = "TPVGH_MAIN_" + doctor_scope("", canonical) + "_T" + tid
                    records[identifier] = {"doctor_id": identifier, "doctor_name_zh": name,
                        "hospital_zh": "臺北榮民總醫院", "department_zh": canonical,
                        "subdepartment_zh": source_department, "specialty_raw_zh": specialty,
                        "source_url": "https://www.vghtpe.gov.tw/Teacher.action?tid=" + tid}
                    metadata[identifier] = {"hospital_id": "TPVGH", "campus_id": "MAIN", "provider_profile_id": tid,
                        "registration_doctor_id": registration_id, "source_department": source_department,
                        "directory_url": index_url, "profile_checked_at": datetime.fromtimestamp((cache_dir / (tid + ".html")).stat().st_mtime, timezone.utc).isoformat(),
                        "booking_mode": "official_handoff", "license_url": "https://www.vghtpe.gov.tw/Fpage.action?fid=2573"}
        doctors.extend(records.values())
        coverage.append({"canonical_department": canonical, "profiles": len(records), "failures": failures})
        print(json.dumps(coverage[-1], ensure_ascii=False), flush=True)
    return sorted(doctors, key=lambda row: row["doctor_id"]), metadata, coverage


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--department", action="append", choices=DEPARTMENTS)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "data/staging/tpvgh")
    parser.add_argument("--cache-dir", type=Path, default=Path("/tmp/tpvgh-profile-cache"))
    args = parser.parse_args()
    doctors, metadata, coverage = crawl(args.department or list(DEPARTMENTS), args.cache_dir)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(args.output_dir / "doctors.csv", doctors, DOCTOR_COLUMNS)
    for name, value in (("provider_metadata", metadata), ("coverage", coverage)):
        (args.output_dir / (name + ".json")).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0 if doctors else 1


if __name__ == "__main__":
    raise SystemExit(main())
