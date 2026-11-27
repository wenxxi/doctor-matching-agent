import csv
import json
from functools import lru_cache
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[4]
PROCESSED_DATA_DIR = PROJECT_ROOT / "data" / "processed"


@lru_cache(maxsize=1)
def load_doctors() -> list[dict[str, str]]:
    return _read_csv(PROCESSED_DATA_DIR / "doctors_normalized.csv")


@lru_cache(maxsize=1)
def load_medical_concepts() -> list[dict[str, str]]:
    return _read_csv(PROCESSED_DATA_DIR / "medical_concepts.csv")


@lru_cache(maxsize=1)
def load_doctor_concept_map() -> list[dict[str, str]]:
    return _read_csv(PROCESSED_DATA_DIR / "doctor_concept_map.csv")


@lru_cache(maxsize=1)
def load_provider_metadata() -> dict:
    path = PROCESSED_DATA_DIR / "provider_metadata.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as csv_file:
        return list(csv.DictReader(csv_file))
