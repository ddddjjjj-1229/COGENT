from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Dict

from pydantic import BaseModel, Field

from base import BaseAgent
from ..prompts import (
    learning_approach_assessment_generator_system_prompt,
    learning_approach_assessment_generator_task_prompt,
)
from ..schemas import LearningApproachAssessment


class LearningApproachAssessmentPayload(BaseModel):
    learning_goal: str = Field(...)
    learner_information: str = Field("")


class LearningApproachAssessmentGenerator(BaseAgent):
    name: str = "LearningApproachAssessmentGenerator"

    def __init__(self, model: Any) -> None:
        super().__init__(
            model=model,
            system_prompt=learning_approach_assessment_generator_system_prompt,
            jsonalize_output=True,
        )

    def generate(self, input_dict: Mapping[str, Any]) -> Dict[str, Any]:
        payload_dict = LearningApproachAssessmentPayload(**input_dict).model_dump()
        raw_output = self.invoke(payload_dict, task_prompt=learning_approach_assessment_generator_task_prompt)
        validated = LearningApproachAssessment.model_validate(raw_output)
        return validated.model_dump()


def generate_learning_approach_assessment_with_llm(
    llm: Any,
    learning_goal: str,
    learner_information: str = "",
) -> Dict[str, Any]:
    generator = LearningApproachAssessmentGenerator(llm)
    return generator.generate(
        {
            "learning_goal": learning_goal,
            "learner_information": learner_information,
        }
    )
