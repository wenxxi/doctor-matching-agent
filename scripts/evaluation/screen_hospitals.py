"""Screen fixed public hospital flows; never submit a patient registration.

Run from apps/api: uv run python ../../scripts/evaluation/screen_hospitals.py ...
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from urllib.request import Request, urlopen
import ssl

import certifi

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "apps/api"))
from app.services.hospital_screening import CANDIDATES, run_screening


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--environment", choices=("local", "render"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rows = []
    for candidate in CANDIDATES:
        if args.environment == "local":
            row = run_screening(candidate)
        else:
            url = "https://doctor-matching-agent-api.onrender.com/api/integrations/hospital-screening/" + candidate
            with urlopen(Request(url, headers={"User-Agent": "DoctorMatchingAgent/0.1 (integration acceptance)"}),
                         context=ssl.create_default_context(cafile=certifi.where()), timeout=120) as response:
                row = json.load(response)
        rows.append(row)
        print(json.dumps({key: row.get(key) for key in ("hospital", "http_status", "status", "schedule_verified", "patient_form_verified", "error_type")}, ensure_ascii=False), flush=True)
    report = dict(environment=args.environment, collected_at=datetime.now(timezone.utc).isoformat(),
                  scope="Public schedule and unfilled patient entry only; no final registration submitted", hospitals=rows)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()
