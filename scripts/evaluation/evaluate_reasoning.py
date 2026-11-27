"""Evaluate synthetic reasoning cases separately from changing hospital capacity."""
import argparse
from dataclasses import asdict
import json
from pathlib import Path
import subprocess
import sys
import types


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "apps/api"))

from app.services.concept_extractor import KeywordConceptExtractor, get_concept_extractor
from app.services.department_intent import detect_department_intent
from app.services.doctor_relevance import ReviewResult, retrieve_candidates, review_candidates


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", action="store_true")
    parser.add_argument("--limit", type=int, default=12)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--case", action="append", dest="case_ids")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    cases = [json.loads(line) for line in (ROOT / "data/evaluation/reasoning_cases.jsonl").read_text().splitlines()][:args.limit]
    if args.case_ids:
        cases = [case for case in cases if case["id"] in args.case_ids]
    baseline_source = subprocess.check_output(["git", "show", "ed8eace:apps/api/app/services/concept_extractor.py"], cwd=ROOT, text=True)
    baseline = types.ModuleType("baseline_concept_extractor")
    sys.modules[baseline.__name__] = baseline
    exec(compile(baseline_source, "baseline_concept_extractor.py", "exec"), baseline.__dict__)
    reports = json.loads(args.output.read_text()).get("cases", []) if args.resume and args.output.exists() else []
    completed = {row["id"] for row in reports if row.get("passed")}
    reports = [row for row in reports if row["id"] in completed]
    for case in cases:
        if case["id"] in completed:
            continue
        query = case["query"]
        before = {item.concept_id for item in baseline.KeywordConceptExtractor().extract_concepts(query)}
        result = (get_concept_extractor() if args.model else KeywordConceptExtractor()).extract_with_metadata(query)
        ids = {item.concept_id for item in result.concepts}
        prefixes = {identifier.split("_", 1)[0] for identifier in ids}
        expected = set(case["positive_prefixes"])
        concepts_ok = not (ids & set(case["forbidden_ids"])) and (not expected or bool(prefixes & expected))
        report = {"id": case["id"], "query": query, "baseline_concept_ids": sorted(before),
                  "concept_evidence": [{"concept_id": item.concept_id, "assertion": item.assertion, "patient_quote": item.patient_evidence} for item in result.concepts],
                  "concept_ids": sorted(ids), "concepts_ok": concepts_ok,
                  "baseline_forbidden_hits": sorted(before & set(case["forbidden_ids"])),
                  "extractor": result.extractor, "fallback_used": result.fallback_used,
                  "search_terms": list(result.search_terms),
                  "assessment_summary": result.assessment_summary,
                  "clarification_question": result.clarification_question}
        if args.model:
            if result.clarification_question:
                review = ReviewResult(doctors=[], method="needs_clarification", clarification_question=result.clarification_question)
            else:
                candidates, rule_ids = retrieve_candidates(query, result.concepts, detect_department_intent(query, result.concepts), search_terms=result.search_terms)
                review = review_candidates(query, candidates, rule_ids)
            report.update(ranking_method=review.method, model_attempted=review.model_attempted,
                          error_type=review.error_type,
                          review_clarification_question=review.clarification_question,
                          doctors=[{"doctor_id": doctor.doctor_id, "department": doctor.department_zh,
                                    "specialty_evidence": doctor.specialty_evidence,
                                    "relevance_summary": doctor.relevance_summary} for doctor in review.doctors[:3]])
            if case["expect"] == "recommend":
                report["passed"] = concepts_ok and review.method == "evidence_review" and bool(review.doctors) and not (result.clarification_question or review.clarification_question)
            else:
                report["passed"] = not review.doctors and bool(result.clarification_question or review.clarification_question or not result.concepts)
        else:
            report["passed"] = concepts_ok if expected else not ids
        reports.append(report)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps({"state": "in_progress", "mode": "model" if args.model else "offline", "cases": reports}, ensure_ascii=False, indent=2) + "\n")
        print(json.dumps({"case": case["id"], "passed": report["passed"], "mode": "model" if args.model else "offline"}), flush=True)
    summary = {"mode": "model" if args.model else "offline", "total": len(reports),
               "passed": sum(row["passed"] for row in reports),
               "note": "Synthetic engineering regression evaluation; does not establish clinical validity. Live appointment capacity is tested separately.",
               "cases": reports}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"passed": summary["passed"], "total": summary["total"], "report": str(args.output)}))
    if summary["passed"] != summary["total"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
