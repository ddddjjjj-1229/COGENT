from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from collections import Counter

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from mentor_eval.data_io import filter_resumes_for_cs_ai_background, load_jobs, load_resumes, write_json
from mentor_eval.simulation import build_cases, save_cases
from mentor_eval.types import JobRecord


def load_config(path: str | Path) -> dict:
    with Path(path).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def resolve_data_path(base: Path, relative_path: str) -> Path:
    candidate = Path(relative_path)
    if candidate.is_absolute():
        return candidate
    return (base / candidate).resolve()


def build_fixed_target_job(spec: dict | None) -> JobRecord | None:
    if not spec:
        return None
    title = str(spec.get("title", "Data Mining Specialist")).strip()
    category = str(spec.get("category", "Data Mining")).strip()
    description = str(spec.get("description", "")).strip()
    required_skills = [str(skill).strip() for skill in spec.get("required_skills", []) if str(skill).strip()]
    prerequisite_skills = [str(skill).strip() for skill in spec.get("prerequisite_skills", []) if str(skill).strip()]
    return JobRecord(
        id=str(spec.get("id", "target_data_mining")).strip() or "target_data_mining",
        title=title,
        description=description,
        required_skills=required_skills,
        prerequisite_skills=prerequisite_skills,
        source={"_category": category, "source": "fixed_config"},
    )


def build_fixed_target_jobs(specs: list[dict] | None) -> list[JobRecord]:
    if not specs:
        return []
    jobs: list[JobRecord] = []
    for index, spec in enumerate(specs, start=1):
        job = build_fixed_target_job(spec)
        if job is not None:
            job.source["target_pool_index"] = index
            jobs.append(job)
    return jobs


def load_fixed_target_jobs(config: dict, project_root: Path) -> list[JobRecord]:
    if config.get("fixed_target_jobs"):
        return build_fixed_target_jobs(config["fixed_target_jobs"])
    target_file = config.get("fixed_target_jobs_file")
    if target_file:
        target_path = resolve_data_path(project_root, target_file)
        with target_path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        if isinstance(payload, dict):
            payload = payload.get("targets", [])
        if not isinstance(payload, list):
            raise ValueError(f"fixed_target_jobs_file must contain a list or a dict with targets: {target_path}")
        return build_fixed_target_jobs(payload)
    return []


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate matched GenMentor benchmark cases.")
    parser.add_argument("--config", default="config/eval_config.json", help="Path to the evaluation config file.")
    args = parser.parse_args()

    config_path = Path(args.config).resolve()
    project_root = config_path.parent.parent
    config = load_config(config_path)

    jobs_path = resolve_data_path(project_root, config["input_files"]["jobs"])
    resumes_path = resolve_data_path(project_root, config["input_files"]["resumes"])
    output_path = resolve_data_path(project_root, config["processed_cases_file"])

    jobs = load_jobs(jobs_path)
    resumes = load_resumes(resumes_path)
    if config.get("resume_filter") == "cs_ai_background":
        resumes = filter_resumes_for_cs_ai_background(resumes)
        if len(resumes) < int(config.get("sample_size", 200)):
            raise ValueError(f"Need at least {config.get('sample_size', 200)} CS/AI-background resumes, got {len(resumes)}.")
    fixed_target_job = build_fixed_target_job(config.get("fixed_target_job"))
    fixed_target_jobs = load_fixed_target_jobs(config, project_root)

    target_categories = config.get("target_job_categories", None)
    print(f"Loaded {len(jobs)} jobs and {len(resumes)} resumes")
    if fixed_target_jobs:
        print(f"Fixed target job pool: {len(fixed_target_jobs)} targets")
        for target in fixed_target_jobs:
            print(f"  - {target.title}")
    elif fixed_target_job:
        print(f"Fixed target job: {fixed_target_job.title}")
        print(f"Required skills: {', '.join(fixed_target_job.required_skills)}")
    elif target_categories:
        print(f"Target job categories: {target_categories}")
        job_cats = Counter(j.category for j in jobs)
        for cat in target_categories:
            print(f"  {cat}: {job_cats.get(cat, 0)} available")
    
    cases = build_cases(
        jobs=jobs,
        resumes=resumes,
        total=int(config.get("sample_size", 200)),
        distribution=config["category_distribution"],
        seed=int(config.get("seed", 42)),
        target_job_categories=target_categories,
        fixed_target_job=fixed_target_job,
        fixed_target_jobs=fixed_target_jobs,
    )
    save_cases(output_path, cases)
    generated_targets = Counter(c.job.title for c in cases)
    write_json(project_root / "results" / "case_generation_summary.json", {
        "jobs_loaded": len(jobs),
        "resumes_loaded": len(resumes),
        "cases_written": len(cases),
        "output_file": str(output_path),
        "target_job_categories": target_categories,
        "fixed_target_job": fixed_target_job.to_dict() if fixed_target_job else None,
        "fixed_target_jobs": [job.to_dict() for job in fixed_target_jobs],
        "generated_target_distribution": dict(sorted(generated_targets.items())),
    })
    print(f"Wrote {len(cases)} cases to {output_path}")
    if fixed_target_jobs:
        print("\nGenerated case distribution by fixed target:")
        for title, count in sorted(generated_targets.items()):
            print(f"  {title}: {count}")
    elif fixed_target_job:
        print(f"All generated cases target: {fixed_target_job.title}")
    elif target_categories:
        generated_cats = Counter(c.job.category for c in cases)
        print("\nGenerated case distribution by job category:")
        for cat in target_categories:
            count = generated_cats.get(cat, 0)
            print(f"  {cat}: {count}")


if __name__ == "__main__":
    main()

