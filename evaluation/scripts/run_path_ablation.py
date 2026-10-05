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

from mentor_eval.adapters import GenMentorApiAdapter
from mentor_eval.data_io import read_jsonl, write_json, write_jsonl
from mentor_eval.llm_client import OpenAICompatibleClient
from mentor_eval.runner import _load_cases
from mentor_eval.scoring import JudgeClient, score_learning_path, score_skill_gap


def _aggregate(records: list[dict[str, Any]]) -> dict[str, Any]:
    if not records:
        return {}
    numeric_keys = sorted({key for record in records for key, value in record.items() if isinstance(value, (int, float))})
    aggregate: dict[str, Any] = {"count": len(records)}
    for key in numeric_keys:
        values = [float(record[key]) for record in records if isinstance(record.get(key), (int, float))]
        if values:
            aggregate[key] = round(mean(values), 4)
    return aggregate


def _load_config(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _build_judge(config: dict[str, Any]) -> JudgeClient | None:
    if not bool(config.get("judge", {}).get("enabled", False)):
        return None
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


def _summary_from_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for system_name in sorted({row.get("system", "unknown") for row in rows}):
        system_rows = [row for row in rows if row.get("system") == system_name]
        categories = sorted({row.get("category", "unknown") for row in system_rows})
        summary[system_name] = {
            "summary": _aggregate(system_rows),
            "by_category": {
                category: _aggregate([row for row in system_rows if row.get("category") == category])
                for category in categories
            },
        }
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Run No-mastery path ablation from existing Improved GenMentor context.")
    parser.add_argument("--config", default="config/eval_config.json")
    parser.add_argument("--base-rows", default="results/full_200/genmentor_improved_cases.jsonl")
    parser.add_argument("--all-rows", default="results/full_200/all_case_results.jsonl")
    parser.add_argument("--summary", default="results/full_200/summary.json")
    parser.add_argument("--cases", default="data/processed/cases_200.jsonl")
    parser.add_argument("--base-url", default="http://127.0.0.1:5002")
    parser.add_argument("--system-name", default="no_mastery_ablation")
    parser.add_argument("--timeout-seconds", type=float, default=180)
    args = parser.parse_args()

    config = _load_config((PROJECT_ROOT / args.config).resolve())
    judge = _build_judge(config)
    cases_by_id = {case.case_id: case for case in _load_cases((PROJECT_ROOT / args.cases).resolve())}
    base_rows = read_jsonl((PROJECT_ROOT / args.base_rows).resolve())
    adapter = GenMentorApiAdapter(base_url=args.base_url, timeout_seconds=args.timeout_seconds)

    ablation_rows: list[dict[str, Any]] = []
    for base_row in base_rows:
        case = cases_by_id[base_row["case_id"]]
        skill_gap = base_row.get("skill_gap_prediction", {})
        learner_profile = base_row.get("learner_profile_prediction", {})
        error_message = None
        try:
            learning_path = adapter.plan_learning_path(case, learner_profile, skill_gap)
        except Exception as exc:
            error_message = str(exc)
            print(f"[WARN] {args.system_name} failed on {case.case_id}: {error_message}")
            learning_path = {}

        skill_scores = score_skill_gap(case, skill_gap, judge)
        path_scores = score_learning_path(case, learning_path, judge)
        ablation_rows.append(
            {
                "system": args.system_name,
                "case_id": case.case_id,
                "category": case.category,
                "skill_gap_prediction": skill_gap,
                "learner_profile_prediction": learner_profile,
                "learning_path_prediction": learning_path,
                "error": error_message,
                **skill_scores,
                **path_scores,
            }
        )

    output_dir = Path(config["output_dir"])
    write_jsonl(output_dir / f"{args.system_name}_cases.jsonl", ablation_rows)

    all_rows_path = (PROJECT_ROOT / args.all_rows).resolve()
    all_rows = [row for row in read_jsonl(all_rows_path) if row.get("system") != args.system_name]
    all_rows.extend(ablation_rows)
    write_jsonl(all_rows_path, all_rows)

    summary = _load_config((PROJECT_ROOT / args.summary).resolve())
    summary[args.system_name] = _summary_from_rows(ablation_rows)[args.system_name]
    write_json((PROJECT_ROOT / args.summary).resolve(), summary)
    print(f"Saved {args.system_name} rows and updated {args.summary}")


if __name__ == "__main__":
    main()
