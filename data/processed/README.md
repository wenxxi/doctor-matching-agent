# Orthopedics Processed Data

These files are generated from `data/raw/cgmh_linkou_orthopedics_doctors.csv` by:

```bash
python3 scripts/processors/build_orthopedics_concepts.py
```

The goal is an MVP ontology for doctor matching:

patient description -> medical concept -> doctor matching

No OpenAI API, embeddings, scraping, or chat logic is used in this processor.

## Files

### `doctors_normalized.csv`

One row per scraped doctor.

- Chinese fields: `doctor_name_zh`, `hospital_zh`, `department_zh`, `subdepartment_zh`, `specialty_raw_zh`, `notes`
- English/system fields: `doctor_id`, `source_url`
- `specialty_raw_zh` preserves the original Chinese specialty text and should not be translated.
- `doctor_id` is stable by source row order, for example `CGMH_LINKOU_ORTHO_001`.

### `medical_concepts.csv`

Reusable medical concepts for orthopedics matching.

- English/system fields: `concept_id`, `canonical_name_en`, `category`, `parent_concept_id`, `synonyms_en`, `is_patient_facing`, `source`
- Chinese display/review fields: `canonical_name_zh`, `synonyms_zh`, `lay_terms_zh`, `description_zh`
- `concept_id` uses stable uppercase English IDs.
- `canonical_name_zh` is the main display name for Taiwanese users.
- `category` is an English enum such as `disease_or_condition`, `symptom`, `anatomy`, `procedure`, `procedure_modifier`, `subspecialty`, `imaging_or_test`, or `non_clinical`.

### `doctor_concept_map.csv`

Many-to-many mapping from doctors to medical concepts.

- Chinese fields: `doctor_name_zh`, `concept_name_zh`, `source_phrase_zh`
- English/system fields: `doctor_id`, `concept_id`, `match_type`, `confidence`, `needs_review`
- `match_type` is rule-based: `exact_keyword`, `synonym_keyword`, `inferred_from_phrase`, or `manual_seed`.
- `needs_review=true` means the mapping is reasonable but should be manually checked before production use.

## Manual Review Workflow

1. Open `doctor_concept_map.csv`.
2. Filter `needs_review` to `true`.
3. Check whether `source_phrase_zh` really supports the mapped `concept_name_zh`.
4. If a mapping is too broad, update the rule in `scripts/processors/build_orthopedics_concepts.py`.
5. Re-run the processor and review the quality-check output.

## Adding a New Concept

1. Add a new row to the `CONCEPTS` list in `scripts/processors/build_orthopedics_concepts.py`.
2. Use a stable English `concept_id`, for example `ORTHO_SPINE_DISC_HERNIATION`.
3. Add Chinese display names and synonyms.
4. Add one or more keyword rules to `MANUAL_RULES`.
5. Re-run the processor.

## Re-Run

From the project root:

```bash
python3 scripts/processors/build_orthopedics_concepts.py
```

The generated CSV files are deterministic and can be regenerated after editing the concept or rule tables.
