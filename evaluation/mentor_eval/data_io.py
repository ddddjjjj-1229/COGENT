from __future__ import annotations

import csv
import json
import random
from pathlib import Path
from typing import Any, Dict, Iterable, List

from .types import JobRecord, ResumeRecord






def _as_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                return [str(item).strip() for item in parsed if str(item).strip()]
        except json.JSONDecodeError:
            pass
        separators = [";", "|", ",", "、"]
        for separator in separators:
            if separator in text:
                parts = [part.strip() for part in text.split(separator)]
                return [part for part in parts if part]
        return [text]
    return [str(value).strip()]


def _first_non_empty(record: Dict[str, Any], keys: Iterable[str], default: str = "") -> str:
    for key in keys:
        value = record.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return default


def _normalize_record_id(record: Dict[str, Any], prefix: str, index: int) -> str:
    value = _first_non_empty(record, ["id", "ID", "uuid", "name", "title"], "")
    if value:
        return value
    return f"{prefix}_{index:04d}"


def _looks_like_placeholder_skill(value: str) -> bool:
    text = str(value).strip()
    return not text or text.isdigit()


def _pick_skill_labels(seed_parts: List[str], pool: List[str], count: int) -> List[str]:
    unique_pool = [item for item in pool if item and item not in seed_parts]
    if count <= 0:
        return []
    if len(unique_pool) <= count:
        return unique_pool[:count]
    rng = random.Random("|".join(seed_parts + unique_pool[:5]))
    return rng.sample(unique_pool, count)


def _build_resume_summary(record: Dict[str, Any], claimed: List[str], actual: List[str], foundation: List[str]) -> str:
    age = _first_non_empty(record, ["age"], "")
    education = _first_non_empty(record, ["education_level"], "")
    university = _first_non_empty(record, ["university_tier"], "")
    experience_years = _first_non_empty(record, ["experience_years"], "")
    internships = _first_non_empty(record, ["internships"], "0")
    projects = _first_non_empty(record, ["projects"], "0")
    languages = _first_non_empty(record, ["programming_languages"], "0")
    certifications = _first_non_empty(record, ["certifications"], "0")
    company_type = _first_non_empty(record, ["company_type"], "")
    soft_skills = _first_non_empty(record, ["soft_skills_score"], "")
    skills_score = _first_non_empty(record, ["skills_score"], "")

    lines = [
        "Professional Summary:",
        f"{age}-year-old {education or 'candidate'} with experience spanning {experience_years or '0'} years and a background from {university or 'an unspecified university tier'}.",
        f"Has completed {internships or '0'} internships and {projects or '0'} projects, with exposure to {languages or '0'} programming languages and {certifications or '0'} certifications.",
        f"Recent work context includes {company_type or 'mixed environments'} and a skills profile score of {skills_score or 'N/A'} with soft-skills score {soft_skills or 'N/A'}.",
        "",
        "Core Skills:",
        ", ".join(claimed[:6]) if claimed else "General problem solving, communication, and analytical thinking",
        "",
        "Supported Strengths:",
        ", ".join(actual[:6]) if actual else "Analytical thinking, teamwork, and documentation",
    ]
    if foundation:
        lines.extend(["", "Foundation Skills:", ", ".join(foundation[:5])])
    return "\n".join(line for line in lines if line is not None)


def _infer_resume_skill_sets(record: Dict[str, Any]) -> tuple[List[str], List[str], List[str]]:
    explicit_claimed = _as_list(
        record.get("claimed_skills")
        or record.get("skills")
        or record.get("reported_skills")
    )
    explicit_actual = _as_list(
        record.get("actual_skills")
        or record.get("ground_truth_skills")
        or record.get("verified_skills")
    )
    explicit_foundation = _as_list(
        record.get("foundation_skills")
        or record.get("base_skills")
        or record.get("prerequisite_skills")
    )

    claimed = [skill for skill in explicit_claimed if not _looks_like_placeholder_skill(skill)]
    actual = [skill for skill in explicit_actual if not _looks_like_placeholder_skill(skill)]
    foundation = [skill for skill in explicit_foundation if not _looks_like_placeholder_skill(skill)]

    generic_programming = ["Python", "SQL", "Java", "JavaScript", "R", "Scala", "Go", "C++"]
    generic_data = ["data analysis", "dashboarding", "ETL", "model evaluation", "feature engineering", "reporting"]
    generic_cloud = ["AWS", "Azure", "GCP", "Docker", "Kubernetes", "Linux"]
    generic_soft = ["communication", "stakeholder management", "problem solving", "teamwork", "ownership", "documentation"]
    generic_ml = ["machine learning", "A/B testing", "statistics", "deep learning", "LLM applications", "experimentation"]

    if not claimed:
        language_count = int(float(_first_non_empty(record, ["programming_languages"], "0") or 0))
        certification_count = int(float(_first_non_empty(record, ["certifications"], "0") or 0))
        project_count = int(float(_first_non_empty(record, ["projects"], "0") or 0))
        claimed = []
        claimed.extend(_pick_skill_labels([], generic_programming, max(1, min(2, language_count or 1))))
        claimed.extend(_pick_skill_labels(claimed, generic_data + generic_ml, max(1, min(2, project_count or 1))))
        if certification_count:
            claimed.extend(_pick_skill_labels(claimed, generic_cloud, 1))
        claimed = list(dict.fromkeys(claimed))

    if not actual:
        actual = list(dict.fromkeys(claimed[:2] + _pick_skill_labels(claimed, generic_soft + generic_data, 2)))

    if not foundation:
        foundation = _pick_skill_labels(claimed + actual, generic_soft + generic_cloud, 2)

    return claimed, actual, foundation


def load_table(path: str | Path) -> List[Dict[str, Any]]:
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"Input file not found: {file_path}")
    suffix = file_path.suffix.lower()
    if suffix == ".jsonl":
        records: List[Dict[str, Any]] = []
        with file_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                text = line.strip()
                if not text:
                    continue
                records.append(json.loads(text))
        return records
    if suffix == ".json":
        with file_path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        if isinstance(payload, list):
            return payload
        if isinstance(payload, dict):
            for key in ["data", "items", "records"]:
                value = payload.get(key)
                if isinstance(value, list):
                    return value
        raise ValueError(f"Unsupported JSON structure in {file_path}")
    if suffix == ".csv":
        with file_path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            return list(reader)
    raise ValueError(f"Unsupported file type: {file_path.suffix}")


def load_jobs(path: str | Path) -> List[JobRecord]:
    records = load_table(path)
    jobs: List[JobRecord] = []
    for index, record in enumerate(records, start=1):
        category = _first_non_empty(record, ["job_category", "category", "job_type", "title_classification"], "General")
        jobs.append(
            JobRecord(
                id=_normalize_record_id(record, "job", index),
                title=_first_non_empty(record, ["job_title", "title", "business_title", "position", "role"], f"Job {index}"),
                description=_first_non_empty(record, ["job_description", "description", "text", "summary"], ""),
                required_skills=_as_list(record.get("required_skills") or record.get("skills") or record.get("job_skills")),
                prerequisite_skills=_as_list(record.get("prerequisite_skills") or record.get("foundation_skills") or record.get("base_skills")),
                source={**record, "_category": category},
            )
        )
    return jobs


def load_resumes(path: str | Path) -> List[ResumeRecord]:
    records = load_table(path)
    resumes: List[ResumeRecord] = []
    for index, record in enumerate(records, start=1):
        claimed, actual, foundation = _infer_resume_skill_sets(record)
        resume_text = _first_non_empty(record, ["text", "resume", "summary", "content", "bio"], "")
        if not resume_text:
            resume_text = _build_resume_summary(record, claimed, actual, foundation)
        resumes.append(
            ResumeRecord(
                id=_normalize_record_id(record, "resume", index),
                text=resume_text,
                claimed_skills=claimed,
                actual_skills=actual,
                foundation_skills=foundation,
                source=record,
            )
        )
    return resumes


def _numeric_source_value(source: Dict[str, Any], key: str) -> float:
    try:
        return float(source.get(key) or 0)
    except (TypeError, ValueError):
        return 0.0


def filter_resumes_for_cs_ai_background(resumes: List[ResumeRecord]) -> List[ResumeRecord]:
    """Select original resumes with evidence of CS/AI/computing study background."""
    filtered: List[ResumeRecord] = []
    for resume in resumes:
        source = resume.source
        programming_languages = _numeric_source_value(source, "programming_languages")
        projects = _numeric_source_value(source, "projects")
        certifications = _numeric_source_value(source, "certifications")
        hackathons = _numeric_source_value(source, "hackathons")
        research_papers = _numeric_source_value(source, "research_papers")
        skills_score = _numeric_source_value(source, "skills_score")

        has_computing_coursework_signal = (
            programming_languages >= 3
            and projects >= 2
            and skills_score >= 12
        )
        has_ai_practice_signal = (
            programming_languages >= 2
            and projects >= 2
            and (certifications >= 1 or hackathons >= 1 or research_papers >= 1)
            and skills_score >= 10
        )
        if has_computing_coursework_signal or has_ai_practice_signal:
            filtered.append(resume)
    return filtered

def write_jsonl(path: str | Path, records: Iterable[Dict[str, Any]]) -> None:
    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    with file_path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def read_jsonl(path: str | Path) -> List[Dict[str, Any]]:
    file_path = Path(path)
    if not file_path.exists():
        return []
    records: List[Dict[str, Any]] = []
    with file_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            text = line.strip()
            if text:
                records.append(json.loads(text))
    return records


def write_json(path: str | Path, payload: Dict[str, Any]) -> None:
    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    with file_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)

