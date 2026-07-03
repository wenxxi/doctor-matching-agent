import argparse
import csv
import sys
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

ROOT_DIR = Path(__file__).resolve().parents[3]
API_DIR = Path(__file__).resolve().parents[1]
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

from app.database import get_sessionmaker  # noqa: E402
from app.models import Doctor, DoctorExpertise  # noqa: E402


SAMPLE_CSV_PATH = ROOT_DIR / "data" / "sample_doctors.csv"


def normalize_optional(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def split_expertise(raw_expertise: str | None) -> list[str]:
    if not raw_expertise:
        return []
    return [
        keyword.strip()
        for keyword in raw_expertise.split(";")
        if keyword.strip()
    ]


def find_existing_doctor(session: Session, row: dict[str, str]) -> Doctor | None:
    statement = select(Doctor).where(
        Doctor.name == row["name"].strip(),
        Doctor.hospital == row["hospital"].strip(),
        Doctor.department == row["department"].strip(),
        Doctor.profile_url == normalize_optional(row.get("profile_url")),
    )
    return session.scalars(statement).first()


def upsert_doctor(session: Session, row: dict[str, str]) -> tuple[Doctor, bool]:
    doctor = find_existing_doctor(session, row)
    created = doctor is None

    if doctor is None:
        doctor = Doctor()
        session.add(doctor)

    doctor.name = row["name"].strip()
    doctor.hospital = row["hospital"].strip()
    doctor.campus = normalize_optional(row.get("campus"))
    doctor.department = row["department"].strip()
    doctor.subspecialty = normalize_optional(row.get("subspecialty"))
    doctor.title = normalize_optional(row.get("title"))
    doctor.profile_url = normalize_optional(row.get("profile_url"))
    doctor.registration_url = normalize_optional(row.get("registration_url"))
    doctor.bio = normalize_optional(row.get("bio"))
    doctor.raw_expertise = normalize_optional(row.get("raw_expertise"))

    existing_keywords = {expertise.keyword for expertise in doctor.expertise}
    for keyword in split_expertise(doctor.raw_expertise):
        if keyword not in existing_keywords:
            doctor.expertise.append(
                DoctorExpertise(
                    keyword=keyword,
                    canonical_keyword=keyword.lower(),
                    category=None,
                )
            )
            existing_keywords.add(keyword)

    return doctor, created


def import_doctors(csv_path: Path = SAMPLE_CSV_PATH, session: Session | None = None) -> dict[str, int]:
    owns_session = session is None
    if session is None:
        session = get_sessionmaker()()

    created_count = 0
    updated_count = 0

    try:
        with csv_path.open(newline="", encoding="utf-8") as csv_file:
            reader = csv.DictReader(csv_file)
            for row in reader:
                _, created = upsert_doctor(session, row)
                if created:
                    created_count += 1
                else:
                    updated_count += 1

        if owns_session:
            session.commit()
    except Exception:
        if owns_session:
            session.rollback()
        raise
    finally:
        if owns_session:
            session.close()

    return {"created": created_count, "updated": updated_count}


def main() -> None:
    parser = argparse.ArgumentParser(description="Import sample doctor data.")
    parser.add_argument(
        "--csv",
        type=Path,
        default=SAMPLE_CSV_PATH,
        help="Path to the doctor CSV file.",
    )
    args = parser.parse_args()

    result = import_doctors(args.csv)
    print(f"Imported doctors: created={result['created']} updated={result['updated']}")


if __name__ == "__main__":
    main()
