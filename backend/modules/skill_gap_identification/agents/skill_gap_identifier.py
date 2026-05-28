from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Dict, Optional, Tuple, TypeAlias
from pydantic import BaseModel, Field
from base import BaseAgent
from ..prompts.skill_gap_identifier import skill_gap_identifier_system_prompt, skill_gap_identifier_task_prompt
from ..schemas import SkillGaps
from .skill_diagnostic_assessment_generator import generate_skill_diagnostic_assessment_with_llm
from .skill_requirement_mapper import SkillRequirementMapper

JSONDict: TypeAlias = Dict[str, Any]


def _limit_words(text: Any, max_words: int) -> str | None:
    if text is None:
        return None
    words = str(text).split()
    if not words:
        return None
    return " ".join(words[:max_words])


class SkillGapPayload(BaseModel):
    """Payload for identifying skill gaps (validated)."""

    learning_goal: str = Field(...)
    learner_information: str = Field(...)
    skill_requirements: Dict[str, Any] = Field(...)


class SkillGapIdentifier(BaseAgent):
    """Agent wrapper for skill requirement discovery and gap identification."""

    name: str = "SkillGapIdentifier"

    def __init__(self, model: Any, ) -> None:
        super().__init__(
            model=model,
            system_prompt=skill_gap_identifier_system_prompt,
            jsonalize_output=True,
        )

    def identify_skill_gap(
        self,
        input_dict: Mapping[str, Any],
    ) -> JSONDict:
        """Identify knowledge gaps using learner information and expected skills."""
        payload_dict = SkillGapPayload(**input_dict).model_dump()
        task_prompt = skill_gap_identifier_task_prompt
        raw_output = self.invoke(payload_dict, task_prompt=task_prompt)
        normalized_output = _normalize_diagnostic_flags(raw_output)
        validated = SkillGaps.model_validate(normalized_output)
        return validated.model_dump(mode="json")


def _normalize_diagnostic_flags(skill_gaps: JSONDict) -> JSONDict:
    """Ensure both claimed and context-inferred prior skills are verified."""
    for skill_gap in skill_gaps.get("skill_gaps", []):
        if not isinstance(skill_gap, dict):
            continue

        skill_gap.setdefault("inferred_from_learner_context", False)
        mentioned = bool(skill_gap.get("mentioned_in_learner_information", False))
        inferred = bool(skill_gap.get("inferred_from_learner_context", False))
        current_level = str(skill_gap.get("current_level", "unlearned"))
        has_prior_signal = current_level != "unlearned"

        if has_prior_signal and not (mentioned or inferred):
            skill_gap["inferred_from_learner_context"] = True
            inferred = True

        if skill_gap.get("requires_diagnostic_assessment") and not (mentioned or inferred):
            skill_gap["inferred_from_learner_context"] = True
            inferred = True

        if mentioned or inferred:
            skill_gap["requires_diagnostic_assessment"] = True
            if not skill_gap.get("learner_context_evidence"):
                skill_gap["learner_context_evidence"] = skill_gap.get("reason") or (
                    "Prior exposure is inferred from learner information."
                )
            skill_gap["learner_context_evidence"] = _limit_words(skill_gap.get("learner_context_evidence"), 25)
            if not skill_gap.get("assessment_reason"):
                source = "mentioned" if mentioned else "inferred from learner context"
                skill_gap["assessment_reason"] = f"Skill was {source}; actual mastery needs verification."
            skill_gap["assessment_reason"] = _limit_words(skill_gap.get("assessment_reason"), 25)
    return SkillGaps.model_validate(skill_gaps).model_dump(mode="json")


def identify_skill_gap_with_llm(
    llm: Any,
    learning_goal: str,
    learner_information: str,
    skill_requirements: Optional[Dict[str, Any]] = None,
) -> Tuple[JSONDict, JSONDict]:
    """Identify skill gaps and return both the gaps and the skill requirements used."""

    # Compute requirements if not provided
    if not skill_requirements:
        mapper = SkillRequirementMapper(llm)
        effective_requirements = mapper.map_goal_to_skill({"learning_goal": learning_goal})
    else:
        effective_requirements = skill_requirements

    skill_gap_identifier = SkillGapIdentifier(llm)
    skill_gaps = skill_gap_identifier.identify_skill_gap(
        {
            "learning_goal": learning_goal,
            "learner_information": learner_information,
            "skill_requirements": effective_requirements,
        },
    )
    skill_gaps = _normalize_diagnostic_flags(skill_gaps)
    for skill_gap in skill_gaps.get("skill_gaps", []):
        if not isinstance(skill_gap, dict):
            continue
        if not skill_gap.get("requires_diagnostic_assessment"):
            continue
        diagnostic_assessment = generate_skill_diagnostic_assessment_with_llm(
            llm,
            learning_goal,
            learner_information,
            skill_gap,
        )
        skill_gap["diagnostic_assessment"] = diagnostic_assessment
    validated_skill_gaps = SkillGaps.model_validate(skill_gaps).model_dump(mode="json")
    return validated_skill_gaps, effective_requirements

if __name__ == "__main__":
    # python -m modules.skill_gap_identification.agents.skill_gap_identifier
    from base.llm_factory import LLMFactory

    llm = LLMFactory.create(model="deepseek-chat", model_provider="deepseek")

    learning_goal = "Become proficient in data science."
    learner_information = "I have a background in statistics but limited programming experience."

    skill_gaps, skill_requirements = identify_skill_gap_with_llm(
        llm,
        learning_goal,
        learner_information,
    )

    print("Identified Skill Gap:", skill_gaps)
    print("Skill Requirements Used:", skill_requirements)
