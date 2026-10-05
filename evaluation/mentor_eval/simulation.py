from __future__ import annotations

import random
from pathlib import Path
from typing import Any, Dict, List, Sequence

from .data_io import write_jsonl
from .types import JobRecord, LearnerCase, ResumeRecord


CATEGORY_ALIASES = {
    "honest": "consistent",
    "over_claimed": "overestimation",
    "under_stated": "underestimation",
    "vague": "underestimation",
    "gap_blind": "overestimation",
}


def _normalize_category(category: str) -> str:
    value = str(category).strip().lower()
    return CATEGORY_ALIASES.get(value, value)


def _dedupe(items: Sequence[str]) -> List[str]:
    seen = set()
    result: List[str] = []
    for item in items:
        value = str(item).strip()
        if value and value.lower() not in seen:
            seen.add(value.lower())
            result.append(value)
    return result


def _collect_skill_pool(jobs: Sequence[JobRecord], resumes: Sequence[ResumeRecord]) -> List[str]:
    pool: List[str] = []
    for job in jobs:
        pool.extend(job.required_skills)
        pool.extend(job.prerequisite_skills)
    for resume in resumes:
        pool.extend(resume.claimed_skills)
        pool.extend(resume.actual_skills)
        pool.extend(resume.foundation_skills)
    pool.extend(["communication", "problem solving", "teamwork", "python", "sql", "statistics", "data analysis", "documentation"])
    return _dedupe(pool)


def _pick_distinct(rng: random.Random, items: Sequence[str], count: int) -> List[str]:
    unique = _dedupe(items)
    if not unique or count <= 0:
        return []
    if len(unique) <= count:
        return list(unique)
    return rng.sample(list(unique), count)


def _target_counts(total: int, distribution: Dict[str, float]) -> Dict[str, int]:
    raw = {name: int(round(total * ratio)) for name, ratio in distribution.items()}
    diff = total - sum(raw.values())
    keys = list(distribution.keys())
    index = 0
    while diff != 0 and keys:
        key = keys[index % len(keys)]
        if diff > 0:
            raw[key] += 1
            diff -= 1
        else:
            if raw[key] > 0:
                raw[key] -= 1
                diff += 1
        index += 1
    return raw


def _stratified_sample_by_category(
    jobs: Sequence[JobRecord],
    target_per_category: int,
    target_categories: Sequence[str],
    rng: random.Random,
) -> List[JobRecord]:
    """Sample jobs stratified by category to ensure balanced coverage."""
    jobs_by_category: Dict[str, List[JobRecord]] = {}
    for job in jobs:
        category = job.category
        if category not in jobs_by_category:
            jobs_by_category[category] = []
        jobs_by_category[category].append(job)
    
    sampled: List[JobRecord] = []
    for category in target_categories:
        if category in jobs_by_category:
            available = jobs_by_category[category]
            take = min(target_per_category, len(available))
            sampled.extend(rng.sample(available, take))
    
    return sampled


def _select_skill_gap(job: JobRecord, resume: ResumeRecord, skill_pool: Sequence[str], category: str, rng: random.Random) -> Dict[str, Any]:
    category = _normalize_category(category)
    required = _dedupe(job.required_skills)
    prerequisites = _dedupe(job.prerequisite_skills)
    claimed = _dedupe(resume.claimed_skills)
    actual = _dedupe(resume.actual_skills or resume.claimed_skills)

    if not actual:
        actual = _pick_distinct(rng, skill_pool, max(2, min(4, len(skill_pool))))
    if not claimed:
        claimed = list(actual)

    # Make each simulated learner partially prepared for the target goal.
    # Otherwise most generated cases have "all target skills are gaps", which
    # lets simple prompt baselines score perfectly by listing every requirement.
    if required:
        if len(required) == 1:
            mastered_count = 1
        else:
            mastered_count = min(len(required) - 1, rng.randint(2, min(5, len(required))))
        mastered_required = _pick_distinct(rng, required, mastered_count)
        background_actual = [skill for skill in actual if skill.lower() not in {item.lower() for item in required}]
        actual = _dedupe(mastered_required + background_actual[:3])
        if category == "consistent":
            claimed = list(actual)

    actual_set = {item.lower() for item in actual}
    claimed_set = {item.lower() for item in claimed}

    if category == "consistent":
        true_gap = [skill for skill in required if skill.lower() not in actual_set]
        return {
            "claimed_skills": claimed,
            "actual_skills": actual,
            "true_gap_skills": _dedupe(true_gap),
            "overclaimed_skills": [],
            "understated_skills": [],
            "foundation_gaps": [],
        }

    if category == "overestimation":
        false_skill = next((skill for skill in required if skill.lower() not in actual_set), None)
        if false_skill is None:
            false_skill = next((skill for skill in skill_pool if skill.lower() not in actual_set), "advanced reporting")
        claimed = list(actual)
        claimed_set = {item.lower() for item in claimed}
        if false_skill.lower() not in claimed_set:
            claimed = claimed + [false_skill]
        true_gap = [skill for skill in required if skill.lower() not in actual_set]
        return {
            "claimed_skills": _dedupe(claimed),
            "actual_skills": actual,
            "true_gap_skills": _dedupe(true_gap),
            "overclaimed_skills": [false_skill],
            "understated_skills": [],
            "foundation_gaps": [],
        }

    if category == "underestimation":
        hidden_skill = next((skill for skill in actual if skill.lower() not in claimed_set), None)
        if hidden_skill is None:
            hidden_skill = next((skill for skill in required if skill.lower() not in claimed_set), None)
        if hidden_skill is None:
            hidden_skill = next((skill for skill in skill_pool if skill.lower() not in claimed_set), "stakeholder communication")
        claimed = [skill for skill in actual if skill.lower() != hidden_skill.lower()]
        claimed_set = {item.lower() for item in claimed}
        true_gap = [skill for skill in required if skill.lower() not in actual_set]
        return {
            "claimed_skills": _dedupe(claimed),
            "actual_skills": actual,
            "true_gap_skills": _dedupe(true_gap),
            "overclaimed_skills": [],
            "understated_skills": [hidden_skill],
            "foundation_gaps": [],
        }

    foundation_source = prerequisites or required
    foundation_gaps = _pick_distinct(rng, foundation_source, min(2, len(foundation_source)))
    if not foundation_gaps:
        foundation_gaps = _pick_distinct(rng, skill_pool, 2)
    true_gap = [skill for skill in required if skill.lower() not in actual_set]
    for skill in foundation_gaps:
        if skill.lower() not in {item.lower() for item in true_gap}:
            true_gap.append(skill)
    advanced_claim = next((skill for skill in required if skill.lower() not in {item.lower() for item in foundation_gaps}), None)
    if advanced_claim and advanced_claim.lower() not in claimed_set:
        claimed = claimed + [advanced_claim]
    return {
        "claimed_skills": _dedupe(claimed),
        "actual_skills": actual,
        "true_gap_skills": _dedupe(true_gap),
        "overclaimed_skills": [advanced_claim] if advanced_claim else [],
        "understated_skills": [],
        "foundation_gaps": _dedupe(foundation_gaps),
    }


def _simulate_trace(category: str, gap_bundle: Dict[str, Any], job: JobRecord, resume: ResumeRecord, rng: random.Random) -> List[Dict[str, Any]]:
    trace: List[Dict[str, Any]] = []
    confidence = 3
    engagement = 3
    fatigue = 1
    claimed = gap_bundle["claimed_skills"]
    actual = gap_bundle["actual_skills"]
    true_gap = gap_bundle["true_gap_skills"]
    hidden = gap_bundle.get("understated_skills", [])
    overclaimed = gap_bundle.get("overclaimed_skills", [])
    foundation = gap_bundle.get("foundation_gaps", [])

    trace.append(
        {
            "turn": 1,
            "event": "intake",
            "message": f"I am applying for {job.title}. My resume highlights: {', '.join(claimed[:6]) or 'general experience'}.",
            "observed_skill_signals": claimed[:4],
            "latent_state": {"confidence": confidence, "engagement": engagement, "fatigue": fatigue},
        }
    )

    if overclaimed:
        skill = overclaimed[0]
        trace.append(
            {
                "turn": 2,
                "event": "diagnostic_question",
                "message": f"Asked for a concrete example showing mastery of {skill}.",
                "learner_response": "The answer becomes vague and partially incorrect.",
                "updated_state": {"confidence": confidence - 1, "engagement": engagement, "fatigue": fatigue + 1},
            }
        )
        confidence -= 1
        fatigue += 1
        trace.append(
            {
                "turn": 3,
                "event": "confirmation",
                "message": f"After probing, the learner admits limited practical use of {skill}.",
                "learner_response": "Acknowledges the gap and accepts follow-up practice.",
                "updated_state": {"confidence": confidence, "engagement": engagement, "fatigue": fatigue},
            }
        )
    elif hidden:
        skill = hidden[0]
        trace.append(
            {
                "turn": 2,
                "event": "diagnostic_question",
                "message": f"Asked about experience with {skill}.",
                "learner_response": "Initially says it was not mentioned on the resume, then provides an example.",
                "updated_state": {"confidence": confidence + 1, "engagement": engagement + 1, "fatigue": fatigue},
            }
        )
        confidence += 1
        engagement += 1
        trace.append(
            {
                "turn": 3,
                "event": "evidence_reveal",
                "message": f"The learner explains a concrete project using {skill}.",
                "learner_response": "Shows practical evidence that had been understated.",
                "updated_state": {"confidence": confidence, "engagement": engagement, "fatigue": fatigue},
            }
        )
    elif foundation:
        skill = foundation[0]
        trace.append(
            {
                "turn": 2,
                "event": "diagnostic_question",
                "message": f"Asked a basic question about {skill}.",
                "learner_response": "Shows uncertainty on the underlying concept.",
                "updated_state": {"confidence": confidence - 1, "engagement": engagement, "fatigue": fatigue + 1},
            }
        )
        confidence -= 1
        fatigue += 1
        trace.append(
            {
                "turn": 3,
                "event": "remediation_acceptance",
                "message": f"Learner accepts a short remedial lesson on {skill} as a prerequisite.",
                "learner_response": "Agrees that the foundation needs reinforcement.",
                "updated_state": {"confidence": confidence, "engagement": engagement + 1, "fatigue": fatigue},
            }
        )
        engagement += 1
    else:
        focus = true_gap[0] if true_gap else (actual[0] if actual else job.title)
        trace.append(
            {
                "turn": 2,
                "event": "diagnostic_question",
                "message": f"Asked a targeted question about {focus}.",
                "learner_response": "Answers consistently and asks for the next step.",
                "updated_state": {"confidence": confidence + 1, "engagement": engagement + 1, "fatigue": fatigue},
            }
        )
        confidence += 1
        engagement += 1

    trace.append(
        {
            "turn": 4,
            "event": "learning_follow_up",
            "message": f"Learner attempts a short practice task tied to {job.title}.",
            "learner_response": "Completes the task with manageable difficulty.",
            "updated_state": {"confidence": confidence, "engagement": engagement, "fatigue": fatigue},
        }
    )
    trace.append(
        {
            "turn": 5,
            "event": "summary",
            "message": "Session closes with a compact action plan and feedback summary.",
            "learner_response": "Accepts the plan and the next learning milestone.",
            "updated_state": {"confidence": confidence, "engagement": engagement, "fatigue": fatigue},
        }
    )
    return trace


def build_cases(
    jobs: Sequence[JobRecord],
    resumes: Sequence[ResumeRecord],
    total: int,
    distribution: Dict[str, float],
    seed: int,
    target_job_categories: Sequence[str] | None = None,
    fixed_target_job: JobRecord | None = None,
    fixed_target_jobs: Sequence[JobRecord] | None = None,
) -> List[LearnerCase]:
    rng = random.Random(seed)

    if fixed_target_jobs:
        sampled_jobs = []
        while len(sampled_jobs) < total:
            sampled_jobs.extend(fixed_target_jobs)
        sampled_jobs = sampled_jobs[:total]
        rng.shuffle(sampled_jobs)
    elif fixed_target_job is not None:
        sampled_jobs = [fixed_target_job] * total
    elif target_job_categories:
        target_per_category = max(1, total // len(target_job_categories))
        sampled_jobs = _stratified_sample_by_category(jobs, target_per_category, target_job_categories, rng)
        if len(sampled_jobs) < total:
            remaining = total - len(sampled_jobs)
            all_other_jobs = [j for j in jobs if j.category not in target_job_categories]
            if all_other_jobs:
                sampled_jobs.extend(rng.sample(all_other_jobs, min(remaining, len(all_other_jobs))))
        if len(sampled_jobs) > total:
            sampled_jobs = rng.sample(sampled_jobs, total)
    else:
        if len(jobs) < total:
            raise ValueError(f"Need at least {total} jobs, got {len(jobs)} jobs.")
        sampled_jobs = rng.sample(list(jobs), total)
    
    if len(resumes) < total:
        raise ValueError(f"Need at least {total} resumes, got {len(resumes)} resumes.")
    sampled_resumes = rng.sample(list(resumes), total)
    rng.shuffle(sampled_resumes)

    # Build learner-condition order from the configured distribution.
    category_counts = _target_counts(total, distribution or {"consistent": 1.0})
    category_order: List[str] = []
    for label, cnt in category_counts.items():
        category_order.extend([label] * cnt)
    rng.shuffle(category_order)

    skill_pool = _collect_skill_pool(sampled_jobs, sampled_resumes)
    cases: List[LearnerCase] = []
    for index, (job, resume, category_label) in enumerate(zip(sampled_jobs, sampled_resumes, category_order), start=1):
        category_label = _normalize_category(category_label)
        gap_bundle = _select_skill_gap(job, resume, skill_pool, category_label, rng)
        trace = _simulate_trace(category_label, gap_bundle, job, resume, rng)
        learning_goal = f"{job.title}: {job.description}".strip()
        presented_info = resume.text or "; ".join(gap_bundle["claimed_skills"])
        if resume.claimed_skills:
            presented_info = f"{presented_info}\nClaimed skills: {', '.join(gap_bundle['claimed_skills'])}"
        true_knowledge = {
            "job_required_skills": _dedupe(job.required_skills),
            "job_prerequisites": _dedupe(job.prerequisite_skills),
            "claimed_skills": gap_bundle["claimed_skills"],
            "actual_skills": gap_bundle["actual_skills"],
            "true_gap_skills": gap_bundle["true_gap_skills"],
            "overclaimed_skills": gap_bundle.get("overclaimed_skills", []),
            "understated_skills": gap_bundle.get("understated_skills", []),
            "foundation_gaps": gap_bundle.get("foundation_gaps", []),
            "category": category_label,
        }
        # Backwards-compatible: set learner_information and ground_truth
        learner_information = presented_info
        ground_truth = dict(true_knowledge)
        cases.append(
            LearnerCase(
                case_id=f"case_{index:04d}",
                job=job,
                resume=resume,
                category=category_label,
                learning_goal=learning_goal,
                presented_info=presented_info,
                true_knowledge=true_knowledge,
                learner_information=learner_information,
                ground_truth=ground_truth,
                behavior_trace=trace,
            )
        )
    return cases


def save_cases(path: str | Path, cases: Sequence[LearnerCase]) -> None:
    write_jsonl(path, [case.to_dict() for case in cases])


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    if value < low:
        return low
    if value > high:
        return high
    return value


def _category_family(category: str) -> str:
    category = _normalize_category(category)
    if category == "overestimation":
        return "overestimation"
    if category == "underestimation":
        return "underestimation"
    return "consistent"


def _simulate_answer_for_skill(
    category: str,
    skill: str,
    actual_set: set[str],
    claimed_set: set[str],
    rng: random.Random,
) -> Dict[str, Any]:
    family = _category_family(category)
    has_actual = skill.lower() in actual_set
    has_claimed = skill.lower() in claimed_set

    if has_actual:
        base = 0.92
        if family == "underestimation":
            base = 0.84
        elif family == "overestimation":
            base = 0.78
    else:
        base = 0.08
        if has_claimed:
            base = 0.2
            if family == "overestimation":
                base = 0.15

    correct = rng.random() < base
    if correct:
        confidence = rng.uniform(0.7, 0.95)
        response = f"Provides a clear, correct explanation of {skill}."
    else:
        if has_claimed and family == "overestimation":
            confidence = rng.uniform(0.6, 0.85)
            response = f"Gives a confident but incorrect answer about {skill}."
        else:
            confidence = rng.uniform(0.3, 0.6)
            response = f"Struggles to answer and mixes concepts around {skill}."

    return {
        "correct": correct,
        "confidence": round(_clamp(confidence), 2),
        "learner_response": response,
    }


def simulate_skill_quiz_trace(
    case: LearnerCase,
    rng: random.Random,
    max_questions: int = 5,
    include_prereq: bool = True,
) -> List[Dict[str, Any]]:
    true_knowledge = case.true_knowledge or case.ground_truth
    actual = true_knowledge.get("actual_skills", []) or case.resume.actual_skills
    claimed = true_knowledge.get("claimed_skills", []) or case.resume.claimed_skills
    actual_set = {str(item).strip().lower() for item in actual if str(item).strip()}
    claimed_set = {str(item).strip().lower() for item in claimed if str(item).strip()}

    skill_candidates = list(case.job.required_skills)
    if include_prereq:
        skill_candidates.extend(case.job.prerequisite_skills)
    skill_candidates = _dedupe(skill_candidates)
    if max_questions > 0 and len(skill_candidates) > max_questions:
        skill_candidates = rng.sample(skill_candidates, max_questions)

    trace: List[Dict[str, Any]] = []
    for index, skill in enumerate(skill_candidates, start=1):
        answer = _simulate_answer_for_skill(case.category, skill, actual_set, claimed_set, rng)
        trace.append(
            {
                "turn": index,
                "event": "skill_question",
                "skill": skill,
                "question": f"Explain or demonstrate your understanding of {skill}.",
                "correct": answer["correct"],
                "confidence": answer["confidence"],
                "learner_response": answer["learner_response"],
            }
        )
    return trace
