from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, Optional, Protocol
from urllib import error, request

from .llm_client import OpenAICompatibleClient, extract_json_block
from .types import LearnerCase


def _to_api_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    # Original GenMentor parses payload strings with ast.literal_eval, so use Python literals.
    return repr(value)


class SystemAdapter(Protocol):
    def identify_skill_gap(self, case: LearnerCase) -> Dict[str, Any]:
        ...

    def model_learner(self, case: LearnerCase, skill_gap: Dict[str, Any]) -> Dict[str, Any]:
        ...

    def plan_learning_path(self, case: LearnerCase, learner_profile: Dict[str, Any], skill_gap: Dict[str, Any]) -> Dict[str, Any]:
        ...


def _skill_requirements(case: LearnerCase, max_skill_requirements: Optional[int] = None) -> Dict[str, Any]:
    required_skills = list(case.job.required_skills)
    prerequisite_skills = list(case.job.prerequisite_skills)
    if isinstance(max_skill_requirements, int) and max_skill_requirements > 0:
        combined = [*required_skills, *prerequisite_skills][:max_skill_requirements]
        required_count = min(len(required_skills), len(combined))
        required_skills = combined[:required_count]
        prerequisite_skills = combined[required_count:]
    return {
        "required_skills": required_skills,
        "prerequisite_skills": prerequisite_skills,
    }


def _common_request_body(case: LearnerCase, max_skill_requirements: Optional[int] = None) -> Dict[str, Any]:
    skill_requirements = {
        **_skill_requirements(case, max_skill_requirements),
    }
    return {
        "learning_goal": case.learning_goal,
        "learner_information": _to_api_text(case.learner_information),
        "skill_requirements": _to_api_text(skill_requirements),
        "behavior_trace": case.behavior_trace,
    }


def _required_only_request_body(case: LearnerCase) -> Dict[str, Any]:
    payload = _common_request_body(case)
    skill_requirements = {
        "required_skills": case.job.required_skills,
        "prerequisite_skills": [],
    }
    payload["skill_requirements"] = _to_api_text(skill_requirements)
    return payload


def _post_json(url: str, payload: Dict[str, Any], timeout_seconds: Optional[float] = None) -> Dict[str, Any]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    try:
        if timeout_seconds is None:
            response_handle = request.urlopen(req)
        else:
            response_handle = request.urlopen(req, timeout=timeout_seconds)
        with response_handle as response:
            raw = response.read().decode("utf-8")
    except error.HTTPError as exc:
        message = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"API request failed for {url}: {exc.code} {message}") from exc
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"raw": raw}


def _prompt_messages(
    case: LearnerCase,
    skill_gap: Dict[str, Any] | None = None,
    learner_profile: Dict[str, Any] | None = None,
    learning_path: Dict[str, Any] | None = None,
    use_cot: bool = False,
    context_mode: str = "structured",
) -> list[Dict[str, str]]:
    system = [
        "You are a strict evaluator for a tutoring benchmark.",
        "Return valid JSON only.",
        "Do not include markdown.",
    ]
    if use_cot:
        system.append("Think through the evidence internally before answering, but only output the final JSON.")
    if context_mode == "direct":
        user = {
            "case_id": case.case_id,
            "learning_goal": case.learning_goal,
            "learner_information": case.learner_information,
            "skill_gap_prediction": skill_gap or {},
            "learner_profile_prediction": learner_profile or {},
            "learning_path_prediction": learning_path or {},
        }
    else:
        user = {
            "case_id": case.case_id,
            "category": case.category,
            "learning_goal": case.learning_goal,
            "learner_information": case.learner_information,
            "job_required_skills": case.job.required_skills,
            "prerequisite_skills": case.job.prerequisite_skills,
            "behavior_trace": case.behavior_trace,
            "skill_gap_prediction": skill_gap or {},
            "learner_profile_prediction": learner_profile or {},
            "learning_path_prediction": learning_path or {},
        }
    return [
        {"role": "system", "content": "\n".join(system)},
        {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
    ]


@dataclass
class PromptSystemAdapter:
    llm: OpenAICompatibleClient
    use_cot: bool = False
    context_mode: str = "structured"

    def identify_skill_gap(self, case: LearnerCase) -> Dict[str, Any]:
        messages = _prompt_messages(case, use_cot=self.use_cot, context_mode=self.context_mode)
        messages[0]["content"] += "\nTask: identify the skill gap set Delta S as JSON with keys gap_skills, removed_skills, added_skills, explanation, confidence."
        messages[1]["content"] = messages[1]["content"][:-1] + ',"task":"skill_gap_identification"}'
        content = self.llm.chat(messages)
        return extract_json_block(content)

    def model_learner(self, case: LearnerCase, skill_gap: Dict[str, Any]) -> Dict[str, Any]:
        messages = _prompt_messages(case, skill_gap=skill_gap, use_cot=self.use_cot, context_mode=self.context_mode)
        messages[0]["content"] += "\nTask: infer the learner model as JSON with keys mastered_skills, in_progress_skills, behavioral_patterns, explanation, confidence."
        messages[1]["content"] = messages[1]["content"][:-1] + ',"task":"learner_modeling"}'
        content = self.llm.chat(messages)
        return extract_json_block(content)

    def plan_learning_path(self, case: LearnerCase, learner_profile: Dict[str, Any], skill_gap: Dict[str, Any]) -> Dict[str, Any]:
        messages = _prompt_messages(
            case,
            skill_gap=skill_gap,
            learner_profile=learner_profile,
            use_cot=self.use_cot,
            context_mode=self.context_mode,
        )
        messages[0]["content"] += "\nTask: plan a learning path as JSON with keys steps, progression, engagement, explanation, confidence."
        messages[1]["content"] = messages[1]["content"][:-1] + ',"task":"learning_path_planning"}'
        content = self.llm.chat(messages)
        return extract_json_block(content)

@dataclass
class GenMentorApiAdapter:
    base_url: str
    timeout_seconds: Optional[float] = None
    max_skill_requirements: Optional[int] = None

    def identify_skill_gap(self, case: LearnerCase) -> Dict[str, Any]:
        url = f"{self.base_url.rstrip('/')}/identify-skill-gap-with-info"
        try:
            return _post_json(url, _common_request_body(case, self.max_skill_requirements), self.timeout_seconds)
        except RuntimeError as exc:
            message = str(exc)
            if "Number of skill gaps must be within 1 to 10" not in message:
                raise
            return _post_json(url, _required_only_request_body(case), self.timeout_seconds)

    def model_learner(self, case: LearnerCase, skill_gap: Dict[str, Any]) -> Dict[str, Any]:
        payload = {
            "learning_goal": case.learning_goal,
            "learner_information": _to_api_text(case.learner_information),
            "skill_gaps": _to_api_text(skill_gap),
        }
        return _post_json(f"{self.base_url.rstrip('/')}/create-learner-profile-with-info", payload, self.timeout_seconds)

    def plan_learning_path(self, case: LearnerCase, learner_profile: Dict[str, Any], skill_gap: Dict[str, Any]) -> Dict[str, Any]:
        payload = {
            "learner_profile": _to_api_text(learner_profile),
            "session_count": 10,
        }
        return _post_json(f"{self.base_url.rstrip('/')}/schedule-learning-path", payload, self.timeout_seconds)

