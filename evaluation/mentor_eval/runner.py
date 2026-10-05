from __future__ import annotations

import json
import random
from pathlib import Path
from statistics import mean
from typing import Any, Dict, List

from .adapters import GenMentorApiAdapter, PromptSystemAdapter, SystemAdapter
from .content_adapters import ContentAdapter, GenMentorContentApiAdapter, PromptContentAdapter
from .data_io import read_jsonl, write_json, write_jsonl
from .llm_client import OpenAICompatibleClient
from .scoring import JudgeClient, score_learning_content, score_learning_path, score_skill_gap
from .simulation import simulate_skill_quiz_trace
from .types import JobRecord, ResumeRecord, LearnerCase


def _load_cases(path: str | Path) -> List[LearnerCase]:
    raw_cases = read_jsonl(path)
    cases: List[LearnerCase] = []
    for raw in raw_cases:
        job_dict = raw["job"]
        resume_dict = raw["resume"]
        job = JobRecord(
            id=job_dict["id"],
            title=job_dict["title"],
            description=job_dict["description"],
            required_skills=job_dict.get("required_skills", []),
            prerequisite_skills=job_dict.get("prerequisite_skills", []),
            source=job_dict.get("source", {}),
        )
        resume = ResumeRecord(
            id=resume_dict["id"],
            text=resume_dict["text"],
            claimed_skills=resume_dict.get("claimed_skills", []),
            actual_skills=resume_dict.get("actual_skills", []),
            foundation_skills=resume_dict.get("foundation_skills", []),
            source=resume_dict.get("source", {}),
        )
        cases.append(
            LearnerCase(
                case_id=raw["case_id"],
                job=job,
                resume=resume,
                category=raw["category"],
                learning_goal=raw["learning_goal"],
                presented_info=raw.get("presented_info", raw.get("learner_information", "")),
                true_knowledge=raw.get("true_knowledge", raw.get("ground_truth", {})),
                learner_information=raw.get("learner_information", raw.get("presented_info", "")),
                ground_truth=raw.get("ground_truth", raw.get("true_knowledge", {})),
                behavior_trace=raw.get("behavior_trace", []),
            )
        )
    return cases


def _build_adapter(name: str, spec: Dict[str, Any], llm: OpenAICompatibleClient) -> SystemAdapter:
    if spec["type"] == "prompt":
        return PromptSystemAdapter(
            llm=llm,
            use_cot=bool(spec.get("use_cot", False)),
            context_mode=str(spec.get("context_mode", "structured")),
        )
    if spec["type"] == "genmentor_api":
        return GenMentorApiAdapter(
            base_url=spec["base_url"],
            timeout_seconds=spec.get("timeout_seconds"),
            max_skill_requirements=spec.get("max_skill_requirements"),
        )
    raise ValueError(f"Unsupported system type for {name}: {spec}")


def _build_content_adapter(name: str, spec: Dict[str, Any], llm: OpenAICompatibleClient | None) -> ContentAdapter:
    adapter_type = spec["type"]
    if adapter_type == "prompt_content":
        if llm is None:
            raise EnvironmentError(f"Content baseline {name} requires an LLM client.")
        return PromptContentAdapter(
            llm=llm,
            method_name=spec.get("method_name", name),
            external_resources=spec.get("external_resources", ""),
            search_enabled=bool(spec.get("search_enabled", False)),
            search_api_key_env=spec.get("search_api_key_env", "SERPER_API_KEY"),
            search_max_results=int(spec.get("search_max_results", 5)),
        )
    if adapter_type == "genmentor_content_api":
        return GenMentorContentApiAdapter(
            base_url=spec["base_url"],
            variant=spec.get("variant", "genmentor"),
            timeout_seconds=spec.get("timeout_seconds"),
            use_search=bool(spec.get("use_search", True)),
            allow_parallel=bool(spec.get("allow_parallel", True)),
            with_quiz=bool(spec.get("with_quiz", True)),
            fallback_on_error=bool(spec.get("fallback_on_error", False)),
        )
    raise ValueError(f"Unsupported content system type for {name}: {spec}")


def _needs_llm(config: Dict[str, Any]) -> bool:
    return bool(config.get("judge", {}).get("enabled", False)) or any(
        spec.get("type") == "prompt" for spec in config.get("systems", {}).values()
    ) or any(
        spec.get("type") == "prompt_content" for spec in config.get("content_systems", {}).values()
    )


def _build_llm(config: Dict[str, Any]) -> OpenAICompatibleClient | None:
    if not _needs_llm(config):
        return None
    llm_spec = config["llm"]
    try:
        return OpenAICompatibleClient.from_env(
            model=llm_spec.get("model", "gpt-4o"),
            base_url=llm_spec.get("base_url", "https://api.openai.com/v1"),
            api_key=llm_spec.get("api_key", ""),
            api_key_env=llm_spec.get("api_key_env", "OPENAI_API_KEY"),
            temperature=float(llm_spec.get("temperature", 0.0)),
            timeout_seconds=llm_spec.get("timeout_seconds"),
        )
    except EnvironmentError:
        return None


def _aggregate(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not records:
        return {}
    numeric_keys = sorted({key for record in records for key, value in record.items() if isinstance(value, (int, float))})
    aggregate: Dict[str, Any] = {"count": len(records)}
    for key in numeric_keys:
        values = [float(record[key]) for record in records if isinstance(record.get(key), (int, float))]
        if values:
            aggregate[key] = round(mean(values), 4)
    return aggregate


def _extract_gap_names(payload: Dict[str, Any]) -> List[str]:
    for key in ["gap_skills", "identified_gap_skills", "delta_s", "DeltaS", "skills", "skill_gap", "skill_gaps"]:
        value = payload.get(key)
        if isinstance(value, list):
            names: List[str] = []
            for item in value:
                if isinstance(item, dict):
                    name = item.get("name") or item.get("skill") or item.get("title")
                    if name:
                        names.append(str(name).strip())
                elif str(item).strip():
                    names.append(str(item).strip())
            return names
        if isinstance(value, dict):
            nested = _extract_gap_names(value)
            if nested:
                return nested
        if isinstance(value, str) and value.strip():
            return [part.strip() for part in value.split(",") if part.strip()]
    return []


def _prediction_signature(payload: Dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)


def _pairwise_diagnostics(system_rows_by_name: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Any]:
    diagnostics: Dict[str, Any] = {}
    system_names = sorted(system_rows_by_name)
    for index, left_name in enumerate(system_names):
        left_rows = {row["case_id"]: row for row in system_rows_by_name[left_name]}
        for right_name in system_names[index + 1 :]:
            right_rows = {row["case_id"]: row for row in system_rows_by_name[right_name]}
            shared_case_ids = sorted(set(left_rows) & set(right_rows))
            if not shared_case_ids:
                continue
            exact_prediction_matches = 0
            same_gap_set_matches = 0
            precision_deltas: List[float] = []
            recall_deltas: List[float] = []
            for case_id in shared_case_ids:
                left_row = left_rows[case_id]
                right_row = right_rows[case_id]
                left_prediction = left_row.get("skill_gap_prediction", {})
                right_prediction = right_row.get("skill_gap_prediction", {})
                if _prediction_signature(left_prediction) == _prediction_signature(right_prediction):
                    exact_prediction_matches += 1
                if sorted(_extract_gap_names(left_prediction)) == sorted(_extract_gap_names(right_prediction)):
                    same_gap_set_matches += 1
                left_precision = left_row.get("gap_precision")
                right_precision = right_row.get("gap_precision")
                left_recall = left_row.get("gap_recall")
                right_recall = right_row.get("gap_recall")
                if isinstance(left_precision, (int, float)) and isinstance(right_precision, (int, float)):
                    precision_deltas.append(float(left_precision) - float(right_precision))
                if isinstance(left_recall, (int, float)) and isinstance(right_recall, (int, float)):
                    recall_deltas.append(float(left_recall) - float(right_recall))
            pair_key = f"{left_name}__vs__{right_name}"
            diagnostics[pair_key] = {
                "count": len(shared_case_ids),
                "exact_prediction_match_rate": round(exact_prediction_matches / len(shared_case_ids), 4),
                "same_gap_set_match_rate": round(same_gap_set_matches / len(shared_case_ids), 4),
                "mean_precision_delta": round(mean(precision_deltas), 4) if precision_deltas else 0.0,
                "mean_recall_delta": round(mean(recall_deltas), 4) if recall_deltas else 0.0,
            }
    return diagnostics


def _case_seed(base_seed: int, case_id: str) -> int:
    return base_seed + sum(ord(char) for char in case_id)


def _apply_simulated_trace(cases: List[LearnerCase], spec: Dict[str, Any]) -> List[LearnerCase]:
    if not spec.get("enabled", False):
        return cases
    base_seed = int(spec.get("seed", 0))
    max_questions = int(spec.get("max_questions", 5))
    include_prereq = bool(spec.get("include_prereq", True))
    mode = str(spec.get("mode", "append")).lower()

    simulated: List[LearnerCase] = []
    for case in cases:
        rng = random.Random(_case_seed(base_seed, case.case_id))
        quiz_trace = simulate_skill_quiz_trace(case, rng, max_questions=max_questions, include_prereq=include_prereq)
        if mode == "replace":
            merged_trace = quiz_trace
        else:
            merged_trace = list(case.behavior_trace) + quiz_trace
        simulated.append(
            LearnerCase(
                case_id=case.case_id,
                job=case.job,
                resume=case.resume,
                category=case.category,
                learning_goal=case.learning_goal,
                presented_info=case.presented_info,
                true_knowledge=case.true_knowledge,
                learner_information=case.learner_information,
                ground_truth=case.ground_truth,
                behavior_trace=merged_trace,
            )
        )
    return simulated


def run_benchmark(config: Dict[str, Any]) -> Dict[str, Any]:
    cases = _load_cases(config["processed_cases_file"])
    cases = _apply_simulated_trace(cases, config.get("simulate_learner", {}))
    output_dir = Path(config["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)

    llm = _build_llm(config)
    judge_spec = config.get("judge", {})
    judge_enabled = bool(judge_spec.get("enabled", False))
    judge = None
    if judge_enabled and llm is not None:
        judge = JudgeClient(
            client=llm,
            model=judge_spec.get("model", config.get("llm", {}).get("model", "gpt-4o")),
            temperature=float(judge_spec.get("temperature", 0.0)),
        )

    results: Dict[str, Any] = {}
    per_case_rows: List[Dict[str, Any]] = []
    system_rows_by_name: Dict[str, List[Dict[str, Any]]] = {}

    for system_name, spec in config["systems"].items():
        if spec["type"] == "prompt" and llm is None:
            print(f"[WARN] Skipping {system_name} because no LLM API key is configured.")
            continue
        adapter = _build_adapter(system_name, spec, llm)  # type: ignore[arg-type]
        system_rows: List[Dict[str, Any]] = []
        for case in cases:
            error_message = None
            try:
                skill_gap = adapter.identify_skill_gap(case)
                learner_profile = adapter.model_learner(case, skill_gap)
                learning_path = adapter.plan_learning_path(case, learner_profile, skill_gap)
            except Exception as exc:
                error_message = str(exc)
                print(f"[WARN] {system_name} failed on {case.case_id}: {error_message}")
                skill_gap = {}
                learner_profile = {}
                learning_path = {}

            skill_scores = score_skill_gap(case, skill_gap, judge)
            path_scores = score_learning_path(case, learning_path, judge)

            row = {
                "system": system_name,
                "case_id": case.case_id,
                "category": case.category,
                "skill_gap_prediction": skill_gap,
                "learner_profile_prediction": learner_profile,
                "learning_path_prediction": learning_path,
                "error": error_message,
                **skill_scores,
                **path_scores,
            }
            system_rows.append(row)
            per_case_rows.append(row)

        results[system_name] = {
            "summary": _aggregate(system_rows),
            "by_category": {
                category: _aggregate([row for row in system_rows if row["category"] == category])
                for category in sorted({row["category"] for row in system_rows})
            },
        }
        system_rows_by_name[system_name] = system_rows
        write_jsonl(output_dir / f"{system_name}_cases.jsonl", system_rows)

    if system_rows_by_name:
        results["diagnostics"] = _pairwise_diagnostics(system_rows_by_name)

    write_jsonl(output_dir / "all_case_results.jsonl", per_case_rows)
    write_json(output_dir / "summary.json", results)
    return results


def run_skill_gap_benchmark(config: Dict[str, Any]) -> Dict[str, Any]:
    cases = _load_cases(config["processed_cases_file"])
    cases = _apply_simulated_trace(cases, config.get("simulate_learner", {}))
    output_dir = Path(config["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)

    llm = _build_llm(config)
    judge_spec = config.get("judge", {})
    judge_enabled = bool(judge_spec.get("enabled", False))
    judge = None
    if judge_enabled and llm is not None:
        judge = JudgeClient(
            client=llm,
            model=judge_spec.get("model", config.get("llm", {}).get("model", "gpt-4o")),
            temperature=float(judge_spec.get("temperature", 0.0)),
        )

    results: Dict[str, Any] = {}
    per_case_rows: List[Dict[str, Any]] = []
    system_rows_by_name: Dict[str, List[Dict[str, Any]]] = {}

    for system_name, spec in config["systems"].items():
        if spec["type"] == "prompt" and llm is None:
            print(f"[WARN] Skipping {system_name} because no LLM API key is configured.")
            continue
        adapter = _build_adapter(system_name, spec, llm)  # type: ignore[arg-type]
        system_rows: List[Dict[str, Any]] = []
        for case in cases:
            error_message = None
            try:
                skill_gap = adapter.identify_skill_gap(case)
            except Exception as exc:
                error_message = str(exc)
                print(f"[WARN] {system_name} failed on {case.case_id}: {error_message}")
                skill_gap = {}

            gap_metrics = score_skill_gap(case, skill_gap, judge=judge)

            row = {
                "system": system_name,
                "case_id": case.case_id,
                "category": case.category,
                "skill_gap_prediction": skill_gap,
                "error": error_message,
                **gap_metrics,
            }
            system_rows.append(row)
            per_case_rows.append(row)

        results[system_name] = {
            "summary": _aggregate(system_rows),
            "by_category": {
                category: _aggregate([row for row in system_rows if row["category"] == category])
                for category in sorted({row["category"] for row in system_rows})
            },
        }
        system_rows_by_name[system_name] = system_rows
        write_jsonl(output_dir / f"{system_name}_cases.jsonl", system_rows)

    if system_rows_by_name:
        results["diagnostics"] = _pairwise_diagnostics(system_rows_by_name)

    write_jsonl(output_dir / "all_case_results.jsonl", per_case_rows)
    write_json(output_dir / "summary.json", results)
    return results


def _build_reference_adapter(config: Dict[str, Any], llm: OpenAICompatibleClient | None) -> SystemAdapter:
    content_spec = config.get("content_eval", {})
    reference_name = content_spec.get("reference_system", "genmentor_improved")
    systems = config.get("systems", {})
    if reference_name not in systems:
        raise ValueError(f"Missing reference system for content evaluation: {reference_name}")
    spec = systems[reference_name]
    if spec["type"] == "prompt" and llm is None:
        raise EnvironmentError(f"Reference system {reference_name} requires an LLM client.")
    return _build_adapter(reference_name, spec, llm)  # type: ignore[arg-type]


def _load_reference_context_cache(config: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    content_spec = config.get("content_eval", {})
    cache_path = content_spec.get("reference_cache_file", "results/full_200/genmentor_improved_cases.jsonl")
    path = Path(cache_path)
    if not path.is_absolute():
        path = Path.cwd() / path
    if not path.exists():
        return {}

    contexts: Dict[str, Dict[str, Any]] = {}
    for row in read_jsonl(path):
        case_id = row.get("case_id")
        if not case_id:
            continue
        contexts[str(case_id)] = {
            "skill_gap": row.get("skill_gap_prediction", {}),
            "learner_profile": row.get("learner_profile_prediction", {}),
            "learning_path": row.get("learning_path_prediction", {}),
            "reference_error": row.get("error"),
        }
    return contexts


def run_content_benchmark(config: Dict[str, Any]) -> Dict[str, Any]:
    cases = _load_cases(config["processed_cases_file"])
    cases = _apply_simulated_trace(cases, config.get("simulate_learner", {}))
    output_dir = Path(config["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)

    content_spec = config.get("content_eval", {})
    max_cases = content_spec.get("max_cases")
    if isinstance(max_cases, int) and max_cases > 0:
        cases = cases[:max_cases]

    llm = _build_llm(config)
    judge_spec = config.get("judge", {})
    judge_enabled = bool(judge_spec.get("enabled", False))
    judge = None
    if judge_enabled and llm is not None:
        judge = JudgeClient(
            client=llm,
            model=judge_spec.get("model", config.get("llm", {}).get("model", "gpt-4o")),
            temperature=float(judge_spec.get("temperature", 0.0)),
        )

    reference_adapter = _build_reference_adapter(config, llm)
    reference_cache = _load_reference_context_cache(config)
    content_systems = config.get("content_systems", {})
    if not content_systems:
        raise ValueError("Content evaluation requires a content_systems config section.")

    results: Dict[str, Any] = {}
    per_case_rows: List[Dict[str, Any]] = []

    reference_contexts: Dict[str, Dict[str, Any]] = {}
    for case in cases:
        cached_context = reference_cache.get(case.case_id)
        if cached_context and cached_context.get("skill_gap") and cached_context.get("learning_path"):
            reference_contexts[case.case_id] = cached_context
            continue
        try:
            skill_gap = reference_adapter.identify_skill_gap(case)
            learner_profile = reference_adapter.model_learner(case, skill_gap)
            learning_path = reference_adapter.plan_learning_path(case, learner_profile, skill_gap)
            reference_contexts[case.case_id] = {
                "skill_gap": skill_gap,
                "learner_profile": learner_profile,
                "learning_path": learning_path,
                "reference_error": None,
            }
        except Exception as exc:
            print(f"[WARN] reference system failed on {case.case_id}: {exc}")
            reference_contexts[case.case_id] = {
                "skill_gap": {},
                "learner_profile": {},
                "learning_path": {},
                "reference_error": str(exc),
            }

    for system_name, spec in content_systems.items():
        if spec["type"] == "prompt_content" and llm is None:
            print(f"[WARN] Skipping {system_name} because no LLM API key is configured.")
            continue
        adapter = _build_content_adapter(system_name, spec, llm)
        system_rows: List[Dict[str, Any]] = []
        for case in cases:
            context = reference_contexts[case.case_id]
            error_message = context.get("reference_error")
            try:
                learning_content = adapter.generate(
                    case,
                    context["learner_profile"],
                    context["skill_gap"],
                    context["learning_path"],
                )
            except Exception as exc:
                error_message = str(exc)
                print(f"[WARN] {system_name} failed on {case.case_id}: {error_message}")
                learning_content = {}

            content_scores = score_learning_content(
                case,
                learning_content,
                learner_profile=context["learner_profile"],
                skill_gap=context["skill_gap"],
                learning_path=context["learning_path"],
                judge=judge,
            )
            row = {
                "system": system_name,
                "case_id": case.case_id,
                "category": case.category,
                "skill_gap_reference": context["skill_gap"],
                "learner_profile_reference": context["learner_profile"],
                "learning_path_reference": context["learning_path"],
                "learning_content_prediction": learning_content,
                "error": error_message,
                **content_scores,
            }
            system_rows.append(row)
            per_case_rows.append(row)

        results[system_name] = {
            "summary": _aggregate(system_rows),
            "by_category": {
                category: _aggregate([row for row in system_rows if row["category"] == category])
                for category in sorted({row["category"] for row in system_rows})
            },
        }
        write_jsonl(output_dir / f"{system_name}_content_cases.jsonl", system_rows)

    write_jsonl(output_dir / "all_content_case_results.jsonl", per_case_rows)
    write_json(output_dir / "content_summary.json", results)
    return results
