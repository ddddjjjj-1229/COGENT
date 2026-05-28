"""Utilities for building and updating adaptive learner profiles via LLMs."""

from __future__ import annotations

import ast
import logging
from typing import Any, Dict, List, Mapping, Optional, Union

from base import BaseAgent
from ..schemas import LearnerProfile, LearningApproachState
from ..prompts import (
    adaptive_learner_profiler_system_prompt,
    adaptive_learner_profiler_task_prompt_initialization,
    adaptive_learner_profiler_task_prompt_update,
)
from .learning_approach_state_inference import infer_learning_approach_state_with_llm
from pydantic import BaseModel, Field


logger = logging.getLogger(__name__)
LEVEL_ORDER = {"unlearned": 0, "beginner": 1, "intermediate": 2, "advanced": 3}


def _normalize_level_value(value: Any) -> str:
    if hasattr(value, "value"):
        return str(value.value)
    text = str(value)
    if "." in text:
        maybe_enum_value = text.split(".")[-1]
        if maybe_enum_value in LEVEL_ORDER:
            return maybe_enum_value
        if maybe_enum_value in {"beginner", "intermediate", "advanced"}:
            return maybe_enum_value
    return text


def _normalize_learning_approach_distribution(state: Mapping[str, Any] | None) -> tuple[list[str], str, str]:
    """Return candidate variants, confidence, and summary hint based on distribution gaps."""

    if not isinstance(state, Mapping):
        return [], "medium", "Learning approach evidence is currently insufficient."
    distribution = state.get("distribution", {}) or {}
    if not isinstance(distribution, Mapping) or not distribution:
        return [], str(state.get("confidence", "medium")), str(state.get("evidence_summary", ""))

    ranked = sorted(
        ((str(k), float(v)) for k, v in distribution.items() if str(k).strip()),
        key=lambda item: item[1],
        reverse=True,
    )
    if not ranked:
        return [], str(state.get("confidence", "medium")), str(state.get("evidence_summary", ""))

    top_type, top_score = ranked[0]
    second_score = ranked[1][1] if len(ranked) > 1 else 0.0
    third_score = ranked[2][1] if len(ranked) > 2 else 0.0
    top_second_gap = top_score - second_score
    top_third_gap = top_score - third_score

    if top_second_gap >= 0.20:
        candidates = [top_type]
        confidence = "high" if top_second_gap >= 0.30 else "medium"
        summary = f"Dominant learning approach currently favors {top_type}."
    elif top_third_gap >= 0.20:
        candidates = [top_type, ranked[1][0]]
        confidence = "medium"
        summary = f"Current learning approach is somewhat mixed, with {top_type} slightly ahead."
    else:
        candidates = [item[0] for item in ranked[:3]]
        confidence = "low"
        summary = "Current learning approach is ambiguous across deep, surface, and achieving styles."

    return candidates, confidence, summary


def _renormalize_distribution(distribution: Mapping[str, Any]) -> Dict[str, float]:
    keys = ["deep", "surface", "achieving"]
    values = {key: max(0.0, float(distribution.get(key, 0.0) or 0.0)) for key in keys}
    total = sum(values.values())
    if total <= 0:
        return {"deep": 1 / 3, "surface": 1 / 3, "achieving": 1 / 3}
    return {key: round(values[key] / total, 4) for key in keys}


def _infer_level_from_quiz_performance(
    current_level: str,
    target_level: str,
    overall_score: float,
    mastery_threshold: float,
    mastery_achieved: bool,
) -> str:
    current_rank = LEVEL_ORDER.get(_normalize_level_value(current_level), 0)
    target_rank = LEVEL_ORDER.get(_normalize_level_value(target_level), 1)

    if mastery_achieved:
        final_rank = target_rank
    elif overall_score >= max(mastery_threshold - 10, 70):
        final_rank = max(current_rank, max(target_rank - 1, 1))
    elif overall_score >= 60:
        final_rank = max(current_rank, 1)
    elif overall_score >= 40:
        final_rank = max(current_rank, 1 if target_rank >= 1 else 0)
    else:
        final_rank = current_rank

    reverse = {v: k for k, v in LEVEL_ORDER.items()}
    return reverse.get(final_rank, "unlearned")


def _apply_strategy_effectiveness_feedback(
    inferred_state: Mapping[str, Any] | None,
    session_information: Mapping[str, Any] | None,
) -> Dict[str, Any]:
    if not isinstance(inferred_state, Mapping):
        return dict(inferred_state or {})
    if not isinstance(session_information, Mapping):
        return dict(inferred_state)

    selected_variant = str(
        session_information.get("selected_variant")
        or session_information.get("learning_approach_variant")
        or ""
    ).strip().lower()
    if selected_variant not in {"deep", "surface", "achieving"}:
        return dict(inferred_state)

    quiz_performance = session_information.get("quiz_performance", {}) or {}
    total_count = int(quiz_performance.get("total_count", 0) or 0)
    if total_count <= 0:
        return dict(inferred_state)

    score = float(quiz_performance.get("overall_score", 0) or 0)
    threshold = float(quiz_performance.get("mastery_threshold", 80) or 80)
    mastery_achieved = bool(quiz_performance.get("mastery_achieved", score >= threshold))

    adjusted_state = dict(inferred_state)
    distribution = _renormalize_distribution(adjusted_state.get("distribution", {}) or {})

    if mastery_achieved:
        boost = 0.12
        if score >= threshold + 10:
            boost = 0.18
        distribution[selected_variant] += boost
    else:
        penalty = 0.08
        if score < max(threshold - 20, 0):
            penalty = 0.12
        distribution[selected_variant] = max(0.0, distribution[selected_variant] - penalty)

    distribution = _renormalize_distribution(distribution)
    adjusted_state["distribution"] = distribution

    dominant_type = max(distribution.items(), key=lambda item: item[1])[0]
    adjusted_state["dominant_type"] = dominant_type
    candidates, confidence, summary = _normalize_learning_approach_distribution(adjusted_state)
    adjusted_state["candidate_types_for_next_session"] = candidates
    adjusted_state["confidence"] = confidence

    outcome_note = (
        f"The learner used a {selected_variant} strategy in this session and achieved strong quiz performance, so preference for {selected_variant} was increased."
        if mastery_achieved
        else f"The learner used a {selected_variant} strategy in this session but did not reach the mastery threshold, so preference for {selected_variant} was reduced."
    )
    existing_summary = str(adjusted_state.get("evidence_summary", "")).strip()
    adjusted_state["evidence_summary"] = f"{summary} {outcome_note}".strip() if summary else f"{existing_summary} {outcome_note}".strip()
    return adjusted_state


class LearnerProfileInitializationPayload(BaseModel):
    """Payload for initializing a learner profile (validated)."""

    learning_goal: str = Field(...)
    learner_information: Union[str, Dict[str, Any], Mapping[str, Any]]
    skill_gaps: Union[str, Dict[str, Any], Mapping[str, Any], List[Any]]

class LearnerProfileUpdatePayload(BaseModel):
    """Payload for updating an existing learner profile (validated)."""

    learner_profile: Union[str, Dict[str, Any], Mapping[str, Any]]
    learner_interactions: Union[str, Dict[str, Any], Mapping[str, Any]]
    learner_information: Union[str, Dict[str, Any], Mapping[str, Any]]
    session_information: Optional[Union[str, Dict[str, Any], Mapping[str, Any]]] = None


class AdaptiveLearnerProfiler(BaseAgent):
    """Agent wrapper that coordinates the prompts required for learner profiling."""

    name: str = "AdaptiveLearnerProfiler"

    def __init__(self, model: Any) -> None:
        super().__init__(
            model=model,
            system_prompt=adaptive_learner_profiler_system_prompt,
            jsonalize_output=True,
        )

    def initialize_profile(self, input_dict: Dict[str, Any]) -> Dict[str, Any]:
        """Generate an initial learner profile using the provided onboarding information."""
        task_prompt = adaptive_learner_profiler_task_prompt_initialization
        payload_dict = LearnerProfileInitializationPayload(**input_dict).model_dump()
        raw_output = self.invoke(payload_dict, task_prompt=task_prompt)
        validated_output = LearnerProfile.model_validate(raw_output)
        return validated_output.model_dump()

    def update_profile(self, input_dict: Dict[str, Any]) -> Dict[str, Any]:
        """Update an existing learner profile with fresh interaction data."""
        task_prompt = adaptive_learner_profiler_task_prompt_update
        payload_dict = LearnerProfileUpdatePayload(**input_dict).model_dump()
        raw_output = self.invoke(payload_dict, task_prompt=task_prompt)
        validated_output = LearnerProfile.model_validate(raw_output)
        return validated_output.model_dump()


def initialize_learner_profile_with_llm(
    llm: Any,
    learning_goal: str,
    learner_information: Union[str, Mapping[str, Any]],
    skill_gaps: Union[str, Mapping[str, Any], List[Any]],
) -> Dict[str, Any]:
    """Public helper for generating a learner profile with minimal boilerplate."""
    learner_profiler = AdaptiveLearnerProfiler(llm)
    payload_dict = {
        "learning_goal": learning_goal,
        "learner_information": learner_information,
        "skill_gaps": skill_gaps,
    }
    learner_profile = learner_profiler.initialize_profile(payload_dict)
    return learner_profile


def update_learner_profile_with_llm(
    llm: Any,
    learner_profile: Union[str, Mapping[str, Any]],
    learner_interactions: Union[str, Mapping[str, Any]],
    learner_information: Union[str, Mapping[str, Any]],
    session_information: Optional[Union[str, Mapping[str, Any]]] = None,
) -> Dict[str, Any]:
    """Public helper for updating an existing learner profile via the LLM backend."""

    try:
        normalized_learner_interactions = ast.literal_eval(learner_interactions) if isinstance(learner_interactions, str) else learner_interactions
    except Exception:
        normalized_learner_interactions = learner_interactions
    if session_information is not None:
        try:
            normalized_session_information = ast.literal_eval(session_information) if isinstance(session_information, str) else session_information
        except Exception:
            normalized_session_information = session_information
        if (
            isinstance(normalized_session_information, Mapping)
            and normalized_session_information.get("quiz_performance")
        ):
            learner_profile = apply_session_quiz_performance_to_profile(
                learner_profile,
                normalized_session_information,
            )
        if isinstance(normalized_session_information, Mapping) and normalized_session_information.get("if_learned"):
            learner_profile = normalize_learner_profile_levels(learner_profile)
            learner_profile = apply_session_behavior_to_profile(
                learner_profile,
                normalized_learner_interactions,
                normalized_session_information,
            )
            learner_profile = apply_learning_approach_state_to_profile(
                llm,
                learner_profile,
                normalized_learner_interactions,
                normalized_session_information,
            )
            return learner_profile

    learner_profiler = AdaptiveLearnerProfiler(llm)
    payload_dict = {
        "learner_profile": learner_profile,
        "learner_interactions": learner_interactions,
        "learner_information": learner_information,
        "session_information": session_information,
    }
    updated_profile = learner_profiler.update_profile(payload_dict)
    try:
        normalized_session_information = ast.literal_eval(session_information) if isinstance(session_information, str) else session_information
    except Exception:
        normalized_session_information = session_information
    if isinstance(normalized_session_information, Mapping) and normalized_session_information.get("if_learned"):
        updated_profile = apply_learning_approach_state_to_profile(
            llm,
            updated_profile,
            learner_interactions,
            normalized_session_information,
        )
    return updated_profile


def sync_learner_profile_with_skill_gaps(
    learner_profile: Union[str, Mapping[str, Any]],
    skill_gaps: Union[str, Mapping[str, Any], List[Any]],
) -> Dict[str, Any]:
    """Deterministically synchronize cognitive status from the latest skill-gap results."""

    if isinstance(learner_profile, str):
        learner_profile = ast.literal_eval(learner_profile)
    if not isinstance(learner_profile, Mapping):
        raise ValueError("learner_profile must be a dict-like object.")

    if isinstance(skill_gaps, str):
        skill_gaps = ast.literal_eval(skill_gaps)
    if isinstance(skill_gaps, Mapping):
        skill_gaps = skill_gaps.get("skill_gaps", [])
    if not isinstance(skill_gaps, list):
        raise ValueError("skill_gaps must be a list or a dict containing skill_gaps.")

    profile_dict = dict(learner_profile)
    cognitive_status = dict(profile_dict.get("cognitive_status", {}))
    mastered_skills: List[Dict[str, Any]] = []
    in_progress_skills: List[Dict[str, Any]] = []

    progress_units = 0
    for item in skill_gaps:
        if not isinstance(item, Mapping):
            continue
        skill_name = str(item.get("name", "")).strip()
        required_level = _normalize_level_value(item.get("required_level", "beginner"))
        current_level = _normalize_level_value(item.get("current_level", "unlearned"))
        if not skill_name:
            continue

        progress_units += min(LEVEL_ORDER.get(current_level, 0), LEVEL_ORDER.get(required_level, 1))

        if LEVEL_ORDER.get(current_level, 0) >= LEVEL_ORDER.get(required_level, 1):
            mastered_skills.append(
                {
                    "name": skill_name,
                    "proficiency_level": required_level,
                }
            )
        else:
            in_progress_skills.append(
                {
                    "name": skill_name,
                    "required_proficiency_level": required_level,
                    "current_proficiency_level": current_level,
                }
            )

    total_required_units = sum(
        max(LEVEL_ORDER.get(_normalize_level_value(item.get("required_level", "beginner")), 1), 1)
        for item in skill_gaps
        if isinstance(item, Mapping)
    )
    overall_progress = 0
    if total_required_units > 0:
        overall_progress = round(progress_units / total_required_units * 100)
    overall_progress = max(0, min(100, overall_progress))

    cognitive_status["mastered_skills"] = mastered_skills
    cognitive_status["in_progress_skills"] = in_progress_skills
    cognitive_status["overall_progress"] = overall_progress
    profile_dict["cognitive_status"] = cognitive_status

    validated_output = LearnerProfile.model_validate(profile_dict)
    return validated_output.model_dump()


def normalize_learner_profile_levels(
    learner_profile: Union[str, Mapping[str, Any]],
) -> Dict[str, Any]:
    """Normalize any enum-like string values inside learner profile cognitive-status levels."""

    if isinstance(learner_profile, str):
        learner_profile = ast.literal_eval(learner_profile)
    if not isinstance(learner_profile, Mapping):
        raise ValueError("learner_profile must be a dict-like object.")

    profile_dict = dict(learner_profile)
    cognitive_status = dict(profile_dict.get("cognitive_status", {}))
    mastered_skills = []
    for item in cognitive_status.get("mastered_skills", []):
        if not isinstance(item, Mapping):
            continue
        mastered_skills.append(
            {
                "name": str(item.get("name", "")),
                "proficiency_level": _normalize_level_value(item.get("proficiency_level", "beginner")),
            }
        )

    in_progress_skills = []
    for item in cognitive_status.get("in_progress_skills", []):
        if not isinstance(item, Mapping):
            continue
        in_progress_skills.append(
            {
                "name": str(item.get("name", "")),
                "required_proficiency_level": _normalize_level_value(item.get("required_proficiency_level", "beginner")),
                "current_proficiency_level": _normalize_level_value(item.get("current_proficiency_level", "unlearned")),
            }
        )

    cognitive_status["mastered_skills"] = mastered_skills
    cognitive_status["in_progress_skills"] = in_progress_skills
    profile_dict["cognitive_status"] = cognitive_status
    return LearnerProfile.model_validate(profile_dict).model_dump()


def apply_session_behavior_to_profile(
    learner_profile: Union[str, Mapping[str, Any]],
    learner_interactions: Union[str, Mapping[str, Any], None],
    session_information: Union[str, Mapping[str, Any], None],
) -> Dict[str, Any]:
    """Fast deterministic update for behavior/session-based fields on chapter completion."""

    if isinstance(learner_profile, str):
        learner_profile = ast.literal_eval(learner_profile)
    if not isinstance(learner_profile, Mapping):
        raise ValueError("learner_profile must be a dict-like object.")

    if isinstance(learner_interactions, str):
        try:
            learner_interactions = ast.literal_eval(learner_interactions)
        except Exception:
            learner_interactions = {"raw": learner_interactions}
    if isinstance(session_information, str):
        session_information = ast.literal_eval(session_information)

    profile_dict = dict(learner_profile)
    behavioral_patterns = dict(profile_dict.get("behavioral_patterns", {}))
    interactions_dict = learner_interactions if isinstance(learner_interactions, Mapping) else {}
    session_behavior = interactions_dict.get("session_behavior", {}) if isinstance(interactions_dict, Mapping) else {}
    quiz_performance = {}
    if isinstance(session_information, Mapping):
        quiz_performance = session_information.get("quiz_performance", {}) or {}
        session_behavior = session_information.get("session_behavior", session_behavior) or session_behavior

    session_duration_seconds = float(session_behavior.get("session_duration_seconds", 0) or 0)
    tutor_question_count = int(session_behavior.get("activity_participation", {}).get("tutor_question_count", 0) or 0)
    quiz_attempted_count = int(session_behavior.get("activity_participation", {}).get("quiz_attempted_count", 0) or 0)
    overall_score = quiz_performance.get("overall_score", 0)

    session_minutes = round(session_duration_seconds / 60, 1) if session_duration_seconds > 0 else 0
    behavioral_patterns["session_duration_engagement"] = (
        f"Recent completed session lasted about {session_minutes} minutes with "
        f"{quiz_attempted_count} quiz attempts and {tutor_question_count} tutor questions."
    )

    existing_usage = behavioral_patterns.get("system_usage_frequency", "") or ""
    if "completed session" not in existing_usage.lower():
        behavioral_patterns["system_usage_frequency"] = (
            f"{existing_usage}\nRecent usage shows at least one completed session in the current study cycle."
        ).strip()

    if quiz_attempted_count > 0 and float(overall_score) < float(quiz_performance.get("mastery_threshold", 80)):
        behavioral_patterns["motivational_triggers"] = "Learner may need reinforcement and encouragement after not reaching mastery threshold in the latest chapter quiz."

    additional_notes = behavioral_patterns.get("additional_notes", "") or ""
    notes_to_append = []
    if quiz_attempted_count:
        notes_to_append.append(f"Latest chapter quiz score: {overall_score}%.")
    if tutor_question_count:
        notes_to_append.append(f"Learner asked {tutor_question_count} tutor questions in the latest session.")
    if notes_to_append:
        behavioral_patterns["additional_notes"] = f"{additional_notes}\n" + " ".join(notes_to_append) if additional_notes else " ".join(notes_to_append)

    profile_dict["behavioral_patterns"] = behavioral_patterns
    return LearnerProfile.model_validate(profile_dict).model_dump()


def apply_session_quiz_performance_to_profile(
    learner_profile: Union[str, Mapping[str, Any]],
    session_information: Union[str, Mapping[str, Any], None],
) -> Dict[str, Any]:
    """
    Deterministically update cognitive status from a completed session plus its quiz performance.

    Expected session_information may include:
    - if_learned: bool
    - desired_outcome_when_completed: [{name, level}]
    - quiz_performance: {
        overall_score: float 0-100,
        correct_count: int,
        total_count: int,
        mastery_threshold: float 0-100,
        mastery_achieved: bool
      }
    """

    if isinstance(learner_profile, str):
        learner_profile = ast.literal_eval(learner_profile)
    if not isinstance(learner_profile, Mapping):
        raise ValueError("learner_profile must be a dict-like object.")

    if session_information is None:
        return LearnerProfile.model_validate(dict(learner_profile)).model_dump()
    if isinstance(session_information, str):
        session_information = ast.literal_eval(session_information)
    if not isinstance(session_information, Mapping):
        raise ValueError("session_information must be a dict-like object.")

    if not session_information.get("if_learned"):
        return LearnerProfile.model_validate(dict(learner_profile)).model_dump()

    profile_dict = dict(learner_profile)
    cognitive_status = dict(profile_dict.get("cognitive_status", {}))
    in_progress_skills = [dict(item) for item in cognitive_status.get("in_progress_skills", [])]
    mastered_skills = [dict(item) for item in cognitive_status.get("mastered_skills", [])]
    quiz_performance = session_information.get("quiz_performance", {}) or {}
    desired_outcomes = session_information.get("desired_outcome_when_completed", []) or []

    overall_score = float(quiz_performance.get("overall_score", 0))
    total_count = int(quiz_performance.get("total_count", 0))
    mastery_threshold = float(quiz_performance.get("mastery_threshold", 80))
    mastery_achieved = bool(
        quiz_performance.get("mastery_achieved", total_count > 0 and overall_score >= mastery_threshold)
    )

    mastery_records = list(cognitive_status.get("mastery_evidence", []))

    for outcome in desired_outcomes:
        if not isinstance(outcome, Mapping):
            continue
        skill_name = str(outcome.get("name", "")).strip()
        target_level = _normalize_level_value(outcome.get("level", "beginner"))
        if not skill_name:
            continue

        matched_idx = next(
            (idx for idx, item in enumerate(in_progress_skills) if str(item.get("name", "")).strip().lower() == skill_name.lower()),
            None,
        )
        if matched_idx is None:
            continue

        current_level = _normalize_level_value(in_progress_skills[matched_idx].get("current_proficiency_level", "unlearned"))
        inferred_level = _infer_level_from_quiz_performance(
            current_level,
            target_level,
            overall_score,
            mastery_threshold,
            mastery_achieved,
        )
        in_progress_skills[matched_idx]["current_proficiency_level"] = inferred_level

        mastery_gap = max(mastery_threshold - overall_score, 0.0)
        mastery_records.append(
            {
                "skill_name": skill_name,
                "target_level": target_level,
                "current_level_at_assessment": current_level,
                "updated_level_after_assessment": inferred_level,
                "overall_score": overall_score,
                "correct_count": total_count if total_count == 0 else int(quiz_performance.get("correct_count", 0)),
                "total_count": total_count,
                "mastery_threshold": mastery_threshold,
                "mastery_achieved": mastery_achieved,
                "mastery_gap": round(mastery_gap, 2),
                "recommended_action": (
                    "ready_for_next_stage" if mastery_achieved else "reinforce_this_knowledge_point"
                ),
            }
        )

        required_level = _normalize_level_value(in_progress_skills[matched_idx].get("required_proficiency_level", target_level))
        if LEVEL_ORDER.get(inferred_level, 0) >= LEVEL_ORDER.get(required_level, 1) and mastery_achieved:
            mastered_skills.append(
                {
                    "name": skill_name,
                    "proficiency_level": required_level,
                }
            )
            del in_progress_skills[matched_idx]

    dedup_mastered = []
    seen = set()
    for item in mastered_skills:
        key = str(item.get("name", "")).strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        dedup_mastered.append(item)

    cognitive_status["mastered_skills"] = dedup_mastered
    cognitive_status["in_progress_skills"] = in_progress_skills
    cognitive_status["mastery_evidence"] = mastery_records[-20:]
    profile_dict["cognitive_status"] = cognitive_status
    return sync_learner_profile_with_skill_gaps(profile_dict, _profile_to_skill_gaps(profile_dict))


def _profile_to_skill_gaps(learner_profile: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """Build a synthetic skill-gap list from learner profile cognitive status for deterministic resync."""

    cognitive_status = learner_profile.get("cognitive_status", {}) or {}
    skill_gaps: List[Dict[str, Any]] = []
    for item in cognitive_status.get("mastered_skills", []):
        if not isinstance(item, Mapping):
            continue
        level = _normalize_level_value(item.get("proficiency_level", "beginner"))
        skill_gaps.append(
            {
                "name": str(item.get("name", "")),
                "required_level": level,
                "current_level": level,
                "is_gap": False,
            }
        )
    for item in cognitive_status.get("in_progress_skills", []):
        if not isinstance(item, Mapping):
            continue
        required_level = _normalize_level_value(item.get("required_proficiency_level", "beginner"))
        current_level = _normalize_level_value(item.get("current_proficiency_level", "unlearned"))
        skill_gaps.append(
            {
                "name": str(item.get("name", "")),
                "required_level": required_level,
                "current_level": current_level,
                "is_gap": LEVEL_ORDER.get(current_level, 0) < LEVEL_ORDER.get(required_level, 1),
            }
        )
    return skill_gaps


def apply_learning_approach_state_to_profile(
    llm: Any,
    learner_profile: Union[str, Mapping[str, Any]],
    learner_interactions: Union[str, Mapping[str, Any]],
    session_information: Union[str, Mapping[str, Any]],
) -> Dict[str, Any]:
    """Infer the learner's current learning-approach state and write it into learning_preferences."""

    if isinstance(learner_profile, str):
        learner_profile = ast.literal_eval(learner_profile)
    if isinstance(learner_interactions, str):
        try:
            learner_interactions = ast.literal_eval(learner_interactions)
        except Exception:
            learner_interactions = {"raw": learner_interactions}
    if isinstance(session_information, str):
        session_information = ast.literal_eval(session_information)

    profile_dict = dict(learner_profile)
    learning_preferences = dict(profile_dict.get("learning_preferences", {}))

    inferred_state = infer_learning_approach_state_with_llm(
        llm,
        profile_dict,
        learner_interactions if isinstance(learner_interactions, Mapping) else {"raw": learner_interactions},
        session_information if isinstance(session_information, Mapping) else {"raw": session_information},
    )
    inferred_state = _apply_strategy_effectiveness_feedback(
        inferred_state,
        session_information if isinstance(session_information, Mapping) else None,
    )
    normalized_candidates, normalized_confidence, normalized_summary = _normalize_learning_approach_distribution(inferred_state)
    if normalized_candidates:
        inferred_state["candidate_types_for_next_session"] = normalized_candidates
        inferred_state["confidence"] = normalized_confidence
        inferred_state["evidence_summary"] = normalized_summary

    previous_state = learning_preferences.get("learning_approach_state", {}) or {}
    history = list(previous_state.get("history", [])) if isinstance(previous_state, Mapping) else []
    chapter_id = ""
    if isinstance(session_information, Mapping):
        chapter_id = str(session_information.get("id", "")).strip()
    history.append(
        {
            "chapter_id": chapter_id,
            "dominant_type": inferred_state.get("dominant_type", "deep"),
            "confidence": inferred_state.get("confidence", "medium"),
        }
    )
    inferred_state["history"] = history[-20:]

    dominant_type = inferred_state.get("dominant_type", "deep")
    candidate_types = inferred_state.get("candidate_types_for_next_session", [])
    learning_preferences["learning_approach_state"] = inferred_state

    if dominant_type == "deep":
        learning_preferences["content_style"] = "Detailed explanations with conceptual connections and reflection prompts"
        learning_preferences["activity_type"] = "Interactive inquiry, self-explanation, and comparison tasks"
    elif dominant_type == "surface":
        learning_preferences["content_style"] = "Concise summaries, key definitions, and stepwise recall supports"
        learning_preferences["activity_type"] = "Guided reading, repetition, and structured recall practice"
    else:
        learning_preferences["content_style"] = "Goal-focused summaries, high-yield explanations, and exam-oriented checkpoints"
        learning_preferences["activity_type"] = "Targeted practice, milestone tracking, and performance-optimized exercises"

    if len(candidate_types) > 1:
        candidate_labels = ", ".join(candidate_types)
        note = f"Current preference state is ambiguous; prepare multiple content variants aligned with: {candidate_labels}."
    else:
        note = f"Current dominant learning approach inferred as {dominant_type}."

    additional_notes = learning_preferences.get("additional_notes", "") or ""
    learning_preferences["additional_notes"] = f"{additional_notes}\n{note}".strip()
    profile_dict["learning_preferences"] = learning_preferences
    return LearnerProfile.model_validate(profile_dict).model_dump()


def update_learning_approach_state_with_llm(
    llm: Any,
    learner_profile: Union[str, Mapping[str, Any]],
    learner_interactions: Union[str, Mapping[str, Any]],
    session_information: Union[str, Mapping[str, Any]],
) -> Dict[str, Any]:
    """Public helper to update only the learning-approach state inside learner preferences."""

    return apply_learning_approach_state_to_profile(
        llm,
        learner_profile,
        learner_interactions,
        session_information,
    )


def apply_learning_approach_state_snapshot_to_profile(
    learner_profile: Union[str, Mapping[str, Any]],
    learning_approach_state: Union[str, Mapping[str, Any]],
) -> Dict[str, Any]:
    """Apply an externally produced learning-approach state snapshot to learner preferences."""

    if isinstance(learner_profile, str):
        learner_profile = ast.literal_eval(learner_profile)
    if isinstance(learning_approach_state, str):
        learning_approach_state = ast.literal_eval(learning_approach_state)
    if not isinstance(learner_profile, Mapping):
        raise ValueError("learner_profile must be a dict-like object.")
    if not isinstance(learning_approach_state, Mapping):
        raise ValueError("learning_approach_state must be a dict-like object.")

    profile_dict = dict(learner_profile)
    learning_preferences = dict(profile_dict.get("learning_preferences", {}))
    normalized_state = LearningApproachState.model_validate(learning_approach_state).model_dump(mode="json")
    normalized_candidates, normalized_confidence, normalized_summary = _normalize_learning_approach_distribution(normalized_state)
    if normalized_candidates:
        normalized_state["candidate_types_for_next_session"] = normalized_candidates
        normalized_state["confidence"] = normalized_confidence
        normalized_state["evidence_summary"] = normalized_summary
    dominant_type = normalized_state.get("dominant_type", "deep")
    candidate_types = normalized_state.get("candidate_types_for_next_session", [])
    learning_preferences["learning_approach_state"] = normalized_state

    if dominant_type == "deep":
        learning_preferences["content_style"] = "Detailed explanations with conceptual connections and reflection prompts"
        learning_preferences["activity_type"] = "Interactive inquiry, self-explanation, and comparison tasks"
    elif dominant_type == "surface":
        learning_preferences["content_style"] = "Concise summaries, key definitions, and stepwise recall supports"
        learning_preferences["activity_type"] = "Guided reading, repetition, and structured recall practice"
    else:
        learning_preferences["content_style"] = "Goal-focused summaries, high-yield explanations, and exam-oriented checkpoints"
        learning_preferences["activity_type"] = "Targeted practice, milestone tracking, and performance-optimized exercises"

    note = (
        f"Initial learning approach state is ambiguous; candidate variants: {', '.join(candidate_types)}."
        if len(candidate_types) > 1
        else f"Initial learning approach inferred as {dominant_type}."
    )
    existing_notes = learning_preferences.get("additional_notes", "") or ""
    learning_preferences["additional_notes"] = f"{existing_notes}\n{note}".strip()
    profile_dict["learning_preferences"] = learning_preferences
    return LearnerProfile.model_validate(profile_dict).model_dump()

if __name__ == "__main__":
    from base.llm_factory import LLMFactory

    llm = LLMFactory.create(model="deepseek-chat", model_provider="deepseek")

    learning_goal = "Become proficient in data science."
    learner_information = "I have a background in statistics but limited programming experience."
    skill_gaps = {"programming": "intermediate", "statistics": "advanced"}

    profile = initialize_learner_profile_with_llm(
        llm,
        learning_goal,
        learner_information,
        skill_gaps,
    )
    print("Initialized Learner Profile:")
    print(profile)
