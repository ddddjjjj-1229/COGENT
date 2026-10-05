from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from statistics import mean
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from mentor_eval.data_io import read_jsonl, write_json, write_jsonl
from mentor_eval.runner import _load_cases
from mentor_eval.scoring import _blend_likert, score_learning_content


CONTENT_KEYS = [
    "content_goal_relevance",
    "content_quality",
    "content_engagement",
    "content_personalization",
]


def _aggregate(records: list[dict[str, Any]]) -> dict[str, Any]:
    if not records:
        return {}
    numeric_keys = sorted(
        {key for record in records for key, value in record.items() if isinstance(value, (int, float))}
    )
    aggregate: dict[str, Any] = {"count": len(records)}
    for key in numeric_keys:
        values = [float(record[key]) for record in records if isinstance(record.get(key), (int, float))]
        if values:
            aggregate[key] = round(mean(values), 4)
    return aggregate


def _restore_existing_judge_scores(row: dict[str, Any], rescored: dict[str, Any]) -> None:
    for key in CONTENT_KEYS:
        # Reuse only an explicitly recorded per-case judge score. Never treat a
        # previous blended total as a fresh judge score during rescoring.
        previous = row.get(f"{key}_judge_likert")
        objective = rescored.get(f"{key}_objective_likert")
        if isinstance(previous, (int, float)):
            rescored[f"{key}_judge_likert"] = previous
            rescored[f"{key}_likert"] = _blend_likert(float(objective), float(previous))
            rescored[f"{key}_rationale"] = "Blended objective content score with the recorded per-case LLM judge score."


def recompute_content_summary(
    input_path: Path,
    output_path: Path,
    cases_path: Path,
    write_rows_path: Path | None = None,
) -> dict[str, Any]:
    rows = read_jsonl(input_path)
    cases_by_id = {case.case_id: case for case in _load_cases(cases_path)}
    rescored_rows: list[dict[str, Any]] = []

    for row in rows:
        case = cases_by_id.get(row.get("case_id"))
        if case is None:
            continue
        rescored = score_learning_content(
            case,
            row.get("learning_content_prediction", {}),
            learner_profile=row.get("learner_profile_reference", {}),
            skill_gap=row.get("skill_gap_reference", {}),
            learning_path=row.get("learning_path_reference", {}),
            judge=None,
        )
        _restore_existing_judge_scores(row, rescored)
        rescored_row = dict(row)
        rescored_row.update(rescored)
        rescored_rows.append(rescored_row)

    summary: dict[str, Any] = {}
    for system_name in sorted({row.get("system", "unknown") for row in rescored_rows}):
        system_rows = [row for row in rescored_rows if row.get("system") == system_name]
        categories = sorted({row.get("category", "unknown") for row in system_rows})
        summary[system_name] = {
            "summary": _aggregate(system_rows),
            "by_category": {
                category: _aggregate([row for row in system_rows if row.get("category") == category])
                for category in categories
            },
        }

    write_json(output_path, summary)
    if write_rows_path is not None:
        write_jsonl(write_rows_path, rescored_rows)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Recompute content_summary.json from existing content case results.")
    parser.add_argument("--input", default="results/full_200/all_content_case_results.jsonl")
    parser.add_argument("--output", default="results/full_200/content_summary.json")
    parser.add_argument("--cases", default="data/processed/cases_200.jsonl")
    parser.add_argument("--write-rows", default="")
    args = parser.parse_args()

    input_path = (PROJECT_ROOT / args.input).resolve()
    output_path = (PROJECT_ROOT / args.output).resolve()
    cases_path = (PROJECT_ROOT / args.cases).resolve()
    write_rows_path = (PROJECT_ROOT / args.write_rows).resolve() if args.write_rows else None

    summary = recompute_content_summary(input_path, output_path, cases_path, write_rows_path)
    print(f"Saved recomputed content summary to {output_path}")
    print(json.dumps(summary, ensure_ascii=False, indent=2)[:8000])


if __name__ == "__main__":
    main()
