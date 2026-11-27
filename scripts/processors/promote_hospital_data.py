#!/usr/bin/env python3
"""Promote a verified TPVGH crawl, preserving existing CGMH identity and mapping data."""
import argparse
import csv
import json
from pathlib import Path
import shutil

from build_orthopedics_concepts import ROOT_DIR, DOCTOR_COLUMNS, build_doctor_concept_map, write_csv


def read(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        return reader.fieldnames, list(reader)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    args = parser.parse_args()
    processed = ROOT_DIR / "data/processed"
    fields, existing = read(processed / "doctors_normalized.csv")
    incoming_fields, incoming = read(args.source / "doctors.csv")
    if fields != DOCTOR_COLUMNS or incoming_fields != fields or not incoming:
        raise ValueError("Doctor schemas must match")
    if any(not row["doctor_id"].startswith("TPVGH_MAIN_") for row in incoming):
        raise ValueError("Only TPVGH records are accepted")
    doctors = [row for row in existing if not row["doctor_id"].startswith("TPVGH_MAIN_")] + incoming
    if len({row["doctor_id"] for row in doctors}) != len(doctors):
        raise ValueError("Duplicate doctor identities")
    map_fields, old_map = read(processed / "doctor_concept_map.csv")
    mappings = [{key: row[key] for key in map_fields} for row in build_doctor_concept_map(doctors)]
    if ([row for row in mappings if row["doctor_id"].startswith("CGMH_")]
            != [row for row in old_map if row["doctor_id"].startswith("CGMH_")]):
        raise ValueError("CGMH mapping changed unexpectedly")
    metadata = json.loads((args.source / "provider_metadata.json").read_text(encoding="utf-8"))
    if set(metadata) != {row["doctor_id"] for row in incoming}:
        raise ValueError("Missing source metadata")
    raw = ROOT_DIR / "data/raw/tpvgh"
    raw.mkdir(parents=True, exist_ok=True)
    for name in ("doctors.csv", "provider_metadata.json", "coverage.json"):
        shutil.copyfile(args.source / name, raw / name)
    write_csv(processed / "doctors_normalized.csv", doctors, fields)
    write_csv(processed / "doctor_concept_map.csv", mappings, map_fields)
    (processed / "provider_metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"active_doctors": len(doctors), "tpvgh_department_records": len(incoming), "mappings": len(mappings)}))


if __name__ == "__main__":
    main()
