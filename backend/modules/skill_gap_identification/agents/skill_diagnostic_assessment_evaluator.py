from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Dict, List

from pydantic import BaseModel, Field

from base import BaseAgent
from ..prompts import (
    skill_diagnostic_assessment_evaluator_system_prompt,
    skill_diagnostic_assessment_evaluator_task_prompt,
)
from ..schemas import (
    DiagnosticAssessmentEvaluation,
    SkillDiagnosticAssessmentSubmission,
    SkillGap,
    SkillGaps,
)


LEVEL_ORDER = {"unlearned": 0, "beginner": 1, "intermediate": 2, "advanced": 3}


def _normalize_level_value(value: Any) -> str:
    if hasattr(value, "value"):
        return str(value.value)
    return str(value)


class SkillDiagnosticAssessmentEvaluationPayload(BaseModel):
    learning_goal: str = Field(...)
    skill_gap: Dict[str, Any] = Field(...)
    submission: Dict[str, Any] = Field(...)


class SkillDiagnosticAssessmentEvaluator(BaseAgent):
    name: str = "SkillDiagnosticAssessmentEvaluator"

    def __init__(self, model: Any) -> None:
        super().__init__(
            model=model,
            system_prompt=skill_diagnostic_assessment_evaluator_system_prompt,
            jsonalize_output=True,
        )

    def evaluate(self, input_dict: Mapping[str, Any]) -> Dict[str, Any]:
        payload_dict = SkillDiagnosticAssessmentEvaluationPayload(**input_dict).model_dump()
        raw_output = self.invoke(payload_dict, task_prompt=skill_diagnostic_assessment_evaluator_task_prompt)
        validated = DiagnosticAssessmentEvaluation.model_validate(raw_output)
        return validated.model_dump()


def evaluate_skill_diagnostic_assessment_with_llm(
    llm: Any,
    learning_goal: str,
    skill_gap: Mapping[str, Any],
    submission: Mapping[str, Any],
) -> Dict[str, Any]:
    evaluator = SkillDiagnosticAssessmentEvaluator(llm)
    return evaluator.evaluate(
        {
            "learning_goal": learning_goal,
            "skill_gap": dict(skill_gap),
            "submission": dict(submission),
        }
    )


def apply_diagnostic_assessment_result_to_skill_gap(
    skill_gap: Mapping[str, Any],
    evaluation: Mapping[str, Any],
) -> Dict[str, Any]:
    updated = dict(skill_gap)
    recommended_current_level = evaluation.get("recommended_current_level", updated.get("current_level", "unlearned"))
    required_level = updated.get("required_level", "beginner")
    normalized_current_level = _normalize_level_value(recommended_current_level)
    normalized_required_level = _normalize_level_value(required_level)
    updated["current_level"] = normalized_current_level
    updated["diagnostic_assessment_result"] = DiagnosticAssessmentEvaluation.model_validate(evaluation).model_dump(mode="json")
    updated["requires_diagnostic_assessment"] = False
    updated["assessment_reason"] = None
    updated["level_confidence"] = "high"
    updated["reason"] = f"Diagnostic assessment indicates {normalized_current_level} mastery."
    updated["is_gap"] = LEVEL_ORDER[normalized_current_level] < LEVEL_ORDER[normalized_required_level]
    return SkillGap.model_validate(updated).model_dump()


def evaluate_and_apply_diagnostic_assessment_with_llm(
    llm: Any,
    learning_goal: str,
    skill_gaps: List[Mapping[str, Any]],
    submission: Mapping[str, Any],
) -> Dict[str, Any]:
    validated_submission = SkillDiagnosticAssessmentSubmission.model_validate(submission).model_dump()
    skill_name = str(validated_submission.get("skill_name", "")).strip().lower()
    updated_skill_gaps: List[Dict[str, Any]] = []
    evaluation_result: Dict[str, Any] | None = None

    for item in skill_gaps:
        item_dict = dict(item)
        if str(item_dict.get("name", "")).strip().lower() == skill_name:
            evaluation_result = evaluate_skill_diagnostic_assessment_with_llm(
                llm,
                learning_goal,
                item_dict,
                validated_submission,
            )
            updated_item = apply_diagnostic_assessment_result_to_skill_gap(item_dict, evaluation_result)
            updated_skill_gaps.append(updated_item)
        else:
            updated_skill_gaps.append(item_dict)

    if evaluation_result is None:
        raise ValueError(f'No skill gap found for submitted skill "{validated_submission.get("skill_name", "")}".')

    validated_skill_gaps = SkillGaps.model_validate({"skill_gaps": updated_skill_gaps}).model_dump()
    return {
        "evaluation": evaluation_result,
        "skill_gaps": validated_skill_gaps["skill_gaps"],
    }
