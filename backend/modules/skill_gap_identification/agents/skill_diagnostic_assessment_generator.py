from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Dict

from pydantic import BaseModel, Field

from base import BaseAgent
from ..prompts import (
    skill_diagnostic_assessment_generator_system_prompt,
    skill_diagnostic_assessment_generator_task_prompt,
)
from ..schemas import SkillDiagnosticAssessment


class SkillDiagnosticAssessmentPayload(BaseModel):
    learning_goal: str = Field(...)
    learner_information: str = Field(...)
    skill_gap: Dict[str, Any] = Field(...)


class SkillDiagnosticAssessmentGenerator(BaseAgent):
    name: str = "SkillDiagnosticAssessmentGenerator"

    def __init__(self, model: Any) -> None:
        super().__init__(
            model=model,
            system_prompt=skill_diagnostic_assessment_generator_system_prompt,
            jsonalize_output=True,
        )

    def generate(self, input_dict: Mapping[str, Any]) -> Dict[str, Any]:
        payload_dict = SkillDiagnosticAssessmentPayload(**input_dict).model_dump()
        raw_output = self.invoke(payload_dict, task_prompt=skill_diagnostic_assessment_generator_task_prompt)
        validated = SkillDiagnosticAssessment.model_validate(raw_output)
        return validated.model_dump()


def generate_skill_diagnostic_assessment_with_llm(
    llm: Any,
    learning_goal: str,
    learner_information: str,
    skill_gap: Mapping[str, Any],
) -> Dict[str, Any]:
    generator = SkillDiagnosticAssessmentGenerator(llm)
    return generator.generate(
        {
            "learning_goal": learning_goal,
            "learner_information": learner_information,
            "skill_gap": dict(skill_gap),
        }
    )
