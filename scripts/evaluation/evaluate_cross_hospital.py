"""Run synthetic end-to-end recommendation checks with real models and read-only schedules."""
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from time import monotonic

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "apps/api"))
from app.routers.recommendations import recommend_doctors
from app.schemas import RecommendationRequest, AppointmentPreparationRequest
from app.services.hospitals import matches_hospital

CASES = [
    ("tpvgh_knee", "台北榮總", "45歲患者，膝蓋疼痛，想找膝關節相關醫師，尚未確診。", True),
    ("both_hospitals_knee", "兩院皆可", "爸爸有糖尿病，但我是打球後膝蓋疼痛，想找膝部運動傷害醫師。", True),
    ("tpvgh_gi_english", "台北榮總", "I am a 40-year-old adult with bloating after meals and want a gastroenterologist.", True),
    ("tpvgh_vague", "台北榮總", "請幫我推薦一位適合的醫師", False),
]


def main():
    rows = []
    output = ROOT / "docs/evaluation/cross-hospital-model-live.json"
    for name, hospital, query, expected in CASES:
        start = monotonic()
        result = recommend_doctors(RecommendationRequest(query=query, hospital=hospital,
            preferences=AppointmentPreparationRequest(patient_type="returning")))
        doctors = result.recommended_doctors
        passed = (bool(doctors) and all(matches_hospital(doctor.model_dump(), hospital) and doctor.availability
                    and doctor.specialty_evidence for doctor in doctors)
                  and result.ranking_method in {"evidence_review", "mixed_evidence_and_rules"}) if expected else (not doctors and bool(result.clarification_question))
        rows.append({"id": name, "passed": bool(passed), "elapsed_seconds": round(monotonic() - start, 2),
                     "hospital": hospital, "query": query, "response": result.model_dump(mode="json")})
        report = {"checked_at": datetime.now(timezone.utc).isoformat(), "passed": sum(row["passed"] for row in rows),
                  "total": len(rows), "registration_submitted": False, "cases": rows}
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"case": name, "passed": bool(passed), "elapsed_seconds": rows[-1]["elapsed_seconds"]}), flush=True)
    return 0 if all(row["passed"] for row in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
