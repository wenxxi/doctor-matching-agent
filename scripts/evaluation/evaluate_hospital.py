#!/usr/bin/env python3
"""Synthetic, read-only TPVGH live gate. Does not submit patient data."""
import argparse
import csv
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "apps/api"))
from app.services import tpvgh
from app.schemas import AppointmentPreparationRequest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--all-departments", action="store_true")
    args = parser.parse_args()
    metadata = json.loads((args.data_dir / "provider_metadata.json").read_text(encoding="utf-8"))
    tpvgh.load_provider_metadata = lambda: metadata
    with (args.data_dir / "doctors.csv").open(encoding="utf-8-sig", newline="") as stream:
        doctors = list(csv.DictReader(stream))
    targets = [row for row in doctors if row["doctor_id"] in {"TPVGH_MAIN_ORTHO_T807", "TPVGH_MAIN_ORTHO_T670"}]
    cases = []
    for doctor in targets:
        for patient_type in ("first_visit", "returning"):
            response = tpvgh.prepare(doctor, AppointmentPreparationRequest(patient_type=patient_type))
            cases.append({"doctor_id": doctor["doctor_id"], "patient_type": patient_type,
                          "result": response.model_dump(mode="json"),
                          "passed": response.verified_at is not None and response.status in {"official_handoff", "no_match"}})
    department_checks = []
    if args.all_departments:
        def check_department(department):
            eligible = [row for row in doctors if row["department_zh"] == department and metadata[row["doctor_id"]]["registration_doctor_id"]]
            attempts = []
            for doctor in eligible[:2]:
                result = tpvgh.get_appointments(doctor, "returning", fresh=True)
                attempts.append({"doctor_id": doctor["doctor_id"], "status": result.status,
                                 "checked_at": result.checked_at.isoformat() if result.checked_at else None,
                                 "slots_count": len(result.slots), "sample_slot": result.slots[0].model_dump() if result.slots else None})
                if result.checked_at and result.status in {"available", "no_slots"}:
                    return {"department": department, "passed": True, "attempts": attempts}
            return {"department": department, "passed": False, "attempts": attempts}
        with ThreadPoolExecutor(max_workers=3) as executor:
            department_checks = list(executor.map(check_department, sorted({row["department_zh"] for row in doctors})))
    passed = len(cases) == 4 and all(row["passed"] for row in cases) and any(row["result"]["selected_slot"] for row in cases)
    passed = passed and all(row["passed"] for row in department_checks)
    report = {"checked_at": datetime.now(timezone.utc).isoformat(), "passed": passed,
              "registration_submitted": False, "note": "Live capacity is a snapshot; no slot was reserved. Provider identity and patient-form fields were checked.", "cases": cases, "department_checks": department_checks}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"passed": passed, "cases": len(cases), "departments": len(department_checks), "registration_submitted": False}))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
