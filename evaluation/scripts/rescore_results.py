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
from mentor_eval.llm_client import OpenAICompatibleClient
from mentor_eval.runner import _load_cases
from mentor_eval.scoring import JudgeClient
from mentor_eval.scoring import score_learning_path, score_skill_gap
from mentor_eval.types import JobRecord, LearnerCase, ResumeRecord


def _aggregate(records: list[dict]) -> dict:
    if not records:
        return {}
    numeric_keys = sorted({key for record in records for key, value in record.items() if isinstance(value, (int, float))})
    aggregate: dict = {"count": len(records)}
    for key in numeric_keys:
        values = [float(record[key]) for record in records if isinstance(record.get(key), (int, float))]
        if values:
            aggregate[key] = round(mean(values), 4)
    return aggregate


def _row_to_case(row: dict) -> LearnerCase:
    job = JobRecord(id="recomputed", title="recomputed", description="recomputed")
    resume = ResumeRecord(id="recomputed", text="recomputed")
    ground_truth = row.get("ground_truth") or row.get("true_knowledge") or {
        "true_gap_skills": row.get("truth_gap_skills", []),
    }
    presented_info = row.get("presented_info") or row.get("learner_information", "")
    return LearnerCase(
        case_id=row.get("case_id", "unknown"),
        job=job,
        resume=resume,
        category=row.get("category", "unknown"),
        learning_goal=row.get("learning_goal", "recomputed"),
        presented_info=presented_info,
        true_knowledge=ground_truth,
        learner_information=row.get("learner_information", ""),
        ground_truth=ground_truth,
        behavior_trace=row.get("behavior_trace", []),
    )


def _load_config(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _build_judge(config: dict[str, Any]) -> JudgeClient:
    llm_spec = config["llm"]
    judge_spec = config.get("judge", {})
    llm = OpenAICompatibleClient.from_env(
        model=llm_spec.get("model", "gpt-4o"),
        base_url=llm_spec.get("base_url", "https://api.openai.com/v1"),
        api_key=llm_spec.get("api_key", ""),
        api_key_env=llm_spec.get("api_key_env", "OPENAI_API_KEY"),
        temperature=float(llm_spec.get("temperature", 0.0)),
        timeout_seconds=llm_spec.get("timeout_seconds"),
    )
    return JudgeClient(
        client=llm,
        model=judge_spec.get("model", llm_spec.get("model", "gpt-4o")),
        temperature=float(judge_spec.get("temperature", 0.0)),
    )


def recompute_summary(
    input_path: Path,
    output_path: Path,
    write_rows_path: Path | None = None,
    judge: JudgeClient | None = None,
    cases_path: Path | None = None,
) -> dict:
    rows = read_jsonl(input_path)
    cases_by_id = {}
    if cases_path is not None and cases_path.exists():
        cases_by_id = {case.case_id: case for case in _load_cases(cases_path)}
    rescored_rows: list[dict] = []
    for row in rows:
        case = cases_by_id.get(row.get("case_id")) or _row_to_case(row)
        skill_scores = score_skill_gap(case, row.get("skill_gap_prediction", {}), judge=judge)
        path_scores = score_learning_path(case, row.get("learning_path_prediction", {}), judge=judge)

        rescored_row = dict(row)
        rescored_row.update(skill_scores)
        rescored_row.update(path_scores)
        rescored_rows.append(rescored_row)

    summary: dict[str, dict] = {}
    for system_name in sorted({row.get("system", "unknown") for row in rescored_rows}):
        system_rows = [row for row in rescored_rows if row.get("system") == system_name]
        categories = sorted({row.get("category", "unknown") for row in system_rows})
        summary[system_name] = {
            "summary": _aggregate(system_rows),
            "by_category": {category: _aggregate([row for row in system_rows if row.get("category") == category]) for category in categories},
        }

    write_json(output_path, summary)
    if write_rows_path is not None:
        write_jsonl(write_rows_path, rescored_rows)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Recompute summary.json from existing case results only.")
    parser.add_argument("--input", default="results/all_case_results.jsonl", help="Path to existing per-case results JSONL.")
    parser.add_argument("--output", default="results/summary.json", help="Path to write the recomputed summary JSON.")
    parser.add_argument("--write-rows", default="", help="Optional path to write rescored per-case JSONL.")
    parser.add_argument("--config", default="config/eval_config.json", help="Evaluation config used to configure judge scoring.")
    parser.add_argument("--cases", default="", help="Optional processed cases JSONL used to restore ground truth and learner context.")
    parser.add_argument("--judge", action="store_true", help="Recompute judge-based scores using the configured LLM judge.")
    args = parser.parse_args()

    input_path = (PROJECT_ROOT / args.input).resolve()
    output_path = (PROJECT_ROOT / args.output).resolve()
    write_rows_path = (PROJECT_ROOT / args.write_rows).resolve() if args.write_rows else None
    cases_path = (PROJECT_ROOT / args.cases).resolve() if args.cases else None

    judge = None
    if args.judge:
        config_path = (PROJECT_ROOT / args.config).resolve()
        config = _load_config(config_path)
        judge = _build_judge(config)

    summary = recompute_summary(input_path, output_path, write_rows_path, judge=judge, cases_path=cases_path)
    print(f"Saved recomputed summary to {output_path}")
    print(json.dumps(summary, ensure_ascii=False, indent=2)[:8000])


if __name__ == "__main__":
    main()
