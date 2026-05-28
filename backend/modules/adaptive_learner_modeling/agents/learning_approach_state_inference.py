from __future__ import annotations

import ast
from collections.abc import Mapping
from typing import Any, Dict

from pydantic import BaseModel, Field, field_validator

from base import BaseAgent
from ..prompts import (
    learning_approach_hypothesis_generator_system_prompt,
    learning_approach_hypothesis_generator_task_prompt,
    learning_approach_state_evaluator_system_prompt,
    learning_approach_state_evaluator_task_prompt,
)
from ..schemas import (
    LearningApproachHypothesisSet,
    LearningApproachState,
)


class LearningApproachInferencePayload(BaseModel):
    learner_profile: Any
    learner_interactions: Any
    session_information: Any

    @field_validator("learner_profile", "learner_interactions", "session_information")
    @classmethod
    def coerce_jsonish(cls, v: Any) -> Any:
        if isinstance(v, Mapping):
            return dict(v)
        if isinstance(v, str):
            try:
                parsed = ast.literal_eval(v)
                if isinstance(parsed, Mapping):
                    return dict(parsed)
                return v
            except Exception:
                return v
        return v


class LearningApproachHypothesisGenerator(BaseAgent):
    name: str = "LearningApproachHypothesisGenerator"

    def __init__(self, model: Any) -> None:
        super().__init__(
            model=model,
            system_prompt=learning_approach_hypothesis_generator_system_prompt,
            jsonalize_output=True,
        )

    def generate(self, input_dict: Mapping[str, Any]) -> Dict[str, Any]:
        payload = LearningApproachInferencePayload(**input_dict).model_dump()
        raw_output = self.invoke(payload, task_prompt=learning_approach_hypothesis_generator_task_prompt)
        validated = LearningApproachHypothesisSet.model_validate(raw_output)
        return validated.model_dump(mode="json")


class LearningApproachStateEvaluator(BaseAgent):
    name: str = "LearningApproachStateEvaluator"

    def __init__(self, model: Any) -> None:
        super().__init__(
            model=model,
            system_prompt=learning_approach_state_evaluator_system_prompt,
            jsonalize_output=True,
        )

    def evaluate(self, input_dict: Mapping[str, Any]) -> Dict[str, Any]:
        payload = dict(input_dict)
        raw_output = self.invoke(payload, task_prompt=learning_approach_state_evaluator_task_prompt)
        validated = LearningApproachState.model_validate(raw_output)
        return validated.model_dump(mode="json")


def infer_learning_approach_state_with_llm(
    llm: Any,
    learner_profile: Mapping[str, Any] | str,
    learner_interactions: Mapping[str, Any] | str,
    session_information: Mapping[str, Any] | str,
) -> Dict[str, Any]:
    generator = LearningApproachHypothesisGenerator(llm)
    evaluator = LearningApproachStateEvaluator(llm)

    inference_payload = {
        "learner_profile": learner_profile,
        "learner_interactions": learner_interactions,
        "session_information": session_information,
    }
    hypotheses = generator.generate(inference_payload)
    evaluated_state = evaluator.evaluate(
        {
            **LearningApproachInferencePayload(**inference_payload).model_dump(),
            "hypotheses": hypotheses,
        }
    )
    return evaluated_state
