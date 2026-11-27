import csv
import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def module_at(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


builder = module_at("hospital_concept_builder", ROOT / "scripts/processors/build_orthopedics_concepts.py")
probe = module_at("hospital_readonly_probe", ROOT / "scripts/crawlers/tpvgh_probe.py")


def read(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def test_department_scoped_concepts_do_not_depend_on_hospital_id():
    specialty = "膝關節、人工關節置換、骨質疏鬆"
    rows = [{"doctor_id": identifier, "doctor_name_zh": "測試", "department_zh": "骨科部", "specialty_raw_zh": specialty}
            for identifier in ("CGMH_LINKOU_ORTHO_001", "TPVGH_MAIN_ORTHO_T807")]
    mappings = builder.build_doctor_concept_map(rows)
    first = {row["concept_id"] for row in mappings if row["doctor_id"] == rows[0]["doctor_id"]}
    second = {row["concept_id"] for row in mappings if row["doctor_id"] == rows[1]["doctor_id"]}
    assert first and first == second


def test_generalization_preserves_all_active_doctor_concept_mappings():
    doctors = read(ROOT / "data/processed/doctors_normalized.csv")
    expected = read(ROOT / "data/processed/doctor_concept_map.csv")
    # The checked-in runtime CSV omits the builder's review-only metadata column.
    rebuilt = [{key: row[key] for key in expected[0]} for row in builder.build_doctor_concept_map(doctors)]
    assert rebuilt == expected


def test_hospital_data_has_shared_schema_and_unique_identities():
    active = read(ROOT / "data/processed/doctors_normalized.csv")
    pilot = read(ROOT / "data/raw/tpvgh/doctors.csv")
    assert set(pilot[0]) == set(active[0])
    assert {row["doctor_id"] for row in pilot} <= {row["doctor_id"] for row in active}
    assert len({row["doctor_id"] for row in pilot}) == len(pilot)


def test_verification_and_http_errors_never_count_as_hospital_availability():
    assert probe.classify_page(200, "<script src='/cdn-cgi/challenge-platform/x'></script>") == "blocked_by_verification"
    assert probe.classify_page(403, "denied") == "http_error"
    assert probe.classify_page(200, "maintenance") == "unexpected_page"
    assert probe.classify_page(200, "臺北榮民總醫院") == "reachable_not_availability_verified"
