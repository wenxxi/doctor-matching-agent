# Processed Doctor Matching Data

These files are generated from:

- `data/raw/cgmh_linkou_orthopedics_doctors.csv`
- `data/raw/cgmh_linkou_neurological_doctors.csv`
- `data/raw/cgmh_linkou_cardiological_doctors.csv`
- `data/raw/cgmh_linkou_chest_doctors.csv`
- `data/raw/cgmh_linkou_endocrinological_doctors.csv`
- `data/raw/cgmh_linkou_gastrointestinal_doctors.csv`
- `data/raw/cgmh_linkou_geriatrics_doctors.csv`
- `data/raw/cgmh_linkou_gynecological_doctors.csv`
- `data/raw/cgmh_linkou_hematological_doctors.csv`
- `data/raw/cgmh_linkou_infectious_doctors.csv`
- `data/raw/cgmh_linkou_nephrological_doctors.csv`
- `data/raw/cgmh_linkou_oncological_doctors.csv`
- `data/raw/cgmh_linkou_rheumatological_doctors.csv`

by:

```bash
python3 scripts/processors/build_orthopedics_concepts.py
```

The goal is an MVP ontology for doctor matching:

patient description -> medical concept -> doctor matching

No OpenAI API, embeddings, scraping, or chat logic is used in this processor.

Current MVP coverage includes orthopedics, neurology, cardiology, chest medicine, endocrinology/metabolism, gastroenterology/hepatology, geriatrics, gynecology/obstetrics, hematology, infectious disease, nephrology, oncology, and rheumatology/immunology.

## Files

### `doctors_normalized.csv`

One row per scraped doctor. The CSV is written with `utf-8-sig` encoding for spreadsheet compatibility.

- Chinese fields: `doctor_name_zh`, `hospital_zh`, `department_zh`, `subdepartment_zh`, `specialty_raw_zh`
- English/system fields: `doctor_id`, `source_url`
- `specialty_raw_zh` preserves the original Chinese specialty text and should not be translated.
- `doctor_id` is stable by source row order, for example `CGMH_LINKOU_ORTHO_001`, `CGMH_LINKOU_NEURO_001`, or `CGMH_LINKOU_CARDIO_001`.

### `medical_concepts.csv`

Reusable medical concepts for doctor matching. The CSV is written with `utf-8-sig` encoding.

- English/system fields: `concept_id`, `canonical_name_en`, `category`, `parent_concept_id`, `synonyms_en`, `source`
- Chinese display/review fields: `canonical_name_zh`, `synonyms_zh`, `lay_terms_zh`, `description_zh`
- `concept_id` uses stable uppercase English IDs.
- `canonical_name_zh` is the main display name for Taiwanese users.
- `category` is an English enum such as `disease_or_condition`, `symptom`, `anatomy`, `procedure`, `procedure_modifier`, `subspecialty`, `imaging_or_test`, or `non_clinical`.

### `doctor_concept_map.csv`

Many-to-many mapping from doctors to medical concepts. The CSV is written with `utf-8-sig` encoding.

- Chinese fields: `doctor_name_zh`, `concept_name_zh`, `source_phrase_zh`
- English/system fields: `doctor_id`, `concept_id`, `match_type`, `confidence`
- `match_type` is rule-based: `exact_keyword`, `synonym_keyword`, `inferred_from_phrase`, or `manual_seed`.
- The processor still prints the count of internally flagged review mappings. Review rows where `match_type` is `inferred_from_phrase` first.

## Manual Review Workflow

1. Open `doctor_concept_map.csv`.
2. Filter `match_type` to `inferred_from_phrase`.
3. Check whether `source_phrase_zh` really supports the mapped `concept_name_zh`.
4. If a mapping is too broad, update the rule in `scripts/processors/build_orthopedics_concepts.py`.
5. Re-run the processor and review the quality-check output.

## Evaluation Cases

`data/evaluation/recommendation_eval_cases.csv` is a simple regression test set. Each row contains a patient-style query, expected department, and expected concept IDs. The backend test suite uses these cases with OpenAI disabled, so running them does not consume tokens. The file is stored as plain UTF-8.

Run the evaluation tests from `apps/api`:

```bash
uv run pytest tests/test_recommendation_eval_cases.py
```

The recommendation ranker weights matched evidence by concept category and rule match type. More specific `disease_or_condition` and `procedure` concepts score higher than broad `anatomy` or `subspecialty` concepts, and `inferred_from_phrase` mappings score lower than direct keyword matches.

The recommendation endpoint also detects a soft department intent from explicit department words and matched concept prefixes. The intent is returned in the API response and used as a ranking adjustment, not a hard filter.

## Adding a New Concept

1. Add a new row to the `CONCEPTS` list in `scripts/processors/build_orthopedics_concepts.py`.
2. Use a stable English `concept_id`, for example `ORTHO_SPINE_DISC_HERNIATION`, `NEURO_EPILEPSY`, `CARDIO_ARRHYTHMIA`, `GI_GERD`, or `NEPHRO_CKD`.
3. Add Chinese display names and synonyms.
4. Add one or more keyword rules to `MANUAL_RULES`.
5. Re-run the processor.

## Re-Run

From the project root:

```bash
python3 scripts/processors/build_orthopedics_concepts.py
```

The generated CSV files are deterministic and can be regenerated after editing the concept or rule tables.
