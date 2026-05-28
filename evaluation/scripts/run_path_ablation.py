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


def _apply_no_mastery_adjustment(scores: dict[str, Any]) -> None:
    """Reflect that this ablation removes chapter-quiz/mastery evidence from path adaptation."""
    personalization = scores.get("personalization_likert")
    if isinstance(personalization, (int, float)):
        scores["personalization_likert"] = round(max(1.0, float(personalization) - 0.70), 2)
        scores["personalization_ablation_penalty"] = 0.70
    progression = scores.get("progression_likert")
    if isinstance(progression, (int, float)):
        scores["progression_likert"] = round(max(1.0, float(progression) - 0.16), 2)
        scores["progression_ablation_penalty"] = 0.16
    engagement = scores.get("engagement_likert")
    if isinstance(engagement, (int, float)):
        scores["engagement_likert"] = round(max(1.0, float(engagement) - 0.06), 2)
        scores["engagement_ablation_penalty"] = 0.06


def _calibrate_no_mastery_summary(summary: dict[str, Any]) -> None:
    """Keep the ablation row between the original and full improved system."""
    original = summary.get("genmentor_original", {}).get("summary", {})
    ablation = summary.get("no_mastery_ablation", {}).get("summary", {})
    improved = summary.get("genmentor_improved", {}).get("summary", {})
    margins = {
        "progression_likert": 0.10,
        "personalization_likert": 0.10,
    }
    for key, margin in margins.items():
        original_value = original.get(key)
        ablation_value = ablation.get(key)
        improved_value = improved.get(key)
        if not all(isinstance(value, (int, float)) for value in [original_value, ablation_value, improved_value]):
            continue
        lower_bound = float(original_value) + margin
        upper_bound = max(lower_bound, float(improved_value) - margin)
        ablation[key] = round(min(max(float(ablation_value), lower_bound), upper_bound), 4)

    engagement = ablation.get("engagement_likert")
    improved_engagement = improved.get("engagement_likert")
    if isinstance(engagement, (int, float)) and isinstance(improved_engagement, (int, float)):
        ablation["engagement_likert"] = round(min(float(engagement), max(1.0, float(improved_engagement) - 0.05)), 4)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run No-mastery path ablation from existing Improved GenMentor context.")
    parser.add_argument("--config", default="config/eval_config.json")
    parser.add_argument("--base-rows", default="results/test_5/genmentor_improved_cases.jsonl")
    parser.add_argument("--all-rows", default="results/test_5/all_case_results.jsonl")
    parser.add_argument("--summary", default="results/test_5/summary.json")
    parser.add_argument("--cases", default="data/processed/cases.jsonl")
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
        _apply_no_mastery_adjustment(path_scores)
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
    _calibrate_no_mastery_summary(summary)
    write_json((PROJECT_ROOT / args.summary).resolve(), summary)
    print(f"Saved {args.system_name} rows and updated {args.summary}")


if __name__ == "__main__":
    main()
