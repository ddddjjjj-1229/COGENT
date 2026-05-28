from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Dict, TypeAlias

from pydantic import BaseModel, Field
from base import BaseAgent
from ..prompts.skill_requirement_mapper import skill_requirement_mapper_system_prompt, skill_requirement_mapper_task_prompt
from ..schemas import SkillRequirements


JSONDict: TypeAlias = Dict[str, Any]

GENERIC_META_SKILLS = {
	"goal setting",
	"goal setting and planning",
	"planning",
	"learning planning",
	"self-directed learning",
	"autonomous learning",
	"self learning",
	"independent learning",
	"time management",
	"communication",
	"teamwork",
	"problem solving",
	"critical thinking",
	"learning motivation",
}


def _normalize_skill_name(name: str) -> str:
	return " ".join(str(name).strip().lower().replace("/", " ").replace("-", " ").split())


def _goal_explicitly_requests_meta_learning(learning_goal: str) -> bool:
	goal = _normalize_skill_name(learning_goal)
	meta_triggers = {
		"study skill",
		"learning strategy",
		"self regulated learning",
		"self directed learning",
		"autonomous learning",
		"time management",
		"goal setting",
	}
	return any(trigger in goal for trigger in meta_triggers)


def _filter_irrelevant_skill_requirements(skill_requirements: Dict[str, Any], learning_goal: str) -> Dict[str, Any]:
	items = skill_requirements.get("skill_requirements", [])
	if not isinstance(items, list):
		return skill_requirements
	if _goal_explicitly_requests_meta_learning(learning_goal):
		return skill_requirements

	filtered = []
	for item in items:
		if not isinstance(item, dict):
			continue
		name = str(item.get("name", "")).strip()
		if not name:
			continue
		if _normalize_skill_name(name) in GENERIC_META_SKILLS:
			continue
		filtered.append(item)

	if filtered:
		skill_requirements["skill_requirements"] = filtered
	return skill_requirements

class Goal2SkillPayload(BaseModel):
	"""Payload for mapping a learning goal to required skills (validated)."""

	learning_goal: str = Field(...)


class SkillRequirementMapper(BaseAgent):
	"""Agent wrapper for mapping a goal to required skills."""

	name: str = "SkillRequirementMapper"

	def __init__(self, model: Any) -> None:
		super().__init__(
			model=model,
			system_prompt=skill_requirement_mapper_system_prompt,
			jsonalize_output=True,
		)

	def map_goal_to_skill(self, input_dict: Mapping[str, Any]) -> JSONDict:
		payload_dict = Goal2SkillPayload(**input_dict).model_dump()
		task_prompt = skill_requirement_mapper_task_prompt
		raw_output = self.invoke(payload_dict, task_prompt=task_prompt)
		raw_output = _filter_irrelevant_skill_requirements(raw_output, payload_dict["learning_goal"])
		validated = SkillRequirements.model_validate(raw_output)
		return validated.model_dump()


def map_goal_to_skills_with_llm(llm: Any, learning_goal: str) -> JSONDict:
	mapper = SkillRequirementMapper(llm)
	return mapper.map_goal_to_skill({"learning_goal": learning_goal})
